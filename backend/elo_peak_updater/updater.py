"""Daily Elo and Arena peak synchronizer.

The module is deliberately independent from the dashboard function.  The HTTP
entry point lives in ``main.py`` so this directory can be deployed on its own.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Callable, Iterable, Mapping, MutableMapping, Protocol


LOGGER = logging.getLogger(__name__)

SHEET_ID = os.environ.get(
    "PEAKS_SPREADSHEET_ID",
    "1NG3FPP70riMzhHPJ6Suz30bhJxUocFd_rKDKxn0kZbM",
)
SHEET_TABS = ("Masters", "Experts", "Candidates", "Ineligible")
SOURCE_TABLE = os.environ.get(
    "PEAKS_SOURCE_TABLE",
    "freestyle-190711.ark_nova.all_games_stat",
)
STATE_BUCKET = os.environ.get("PEAKS_STATE_BUCKET", "ark-nova-stats-dashboard-cache")
STATE_PREFIX = os.environ.get("PEAKS_STATE_PREFIX", "elo-peak-updater/runs")
DISCORD_WEBHOOK_ENV = "DISCORD_WEBHOOK_URL"
RATING_QUANTUM = Decimal("0.01")
ZERO_RATING = Decimal("0.00")
SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
MAX_DISCORD_CONTENT = 1900

COL_ELO = 5  # zero-based sheet column F
COL_ELO_DATE = 6  # G
COL_ARENA = 7  # H
COL_ELO_TABLE = 12  # M
COL_ARENA_TABLE = 13  # N


class BigQueryClientLike(Protocol):
    def query(self, query: str, job_config: Any = None) -> Any: ...


class SheetsServiceLike(Protocol):
    def spreadsheets(self) -> Any: ...


class StateStoreLike(Protocol):
    def load(self, run_id: str) -> MutableMapping[str, Any] | None: ...

    def create(self, run_id: str, payload: Mapping[str, Any]) -> MutableMapping[str, Any]: ...

    def save(self, run_id: str, payload: Mapping[str, Any]) -> MutableMapping[str, Any]: ...


@dataclass(frozen=True)
class PeakRecord:
    rating: Decimal
    table_id: str
    url: str | None
    date_text: str | None = None


@dataclass(frozen=True)
class SheetRow:
    sheet_title: str
    sheet_id: int
    row_number: int
    name: str
    player_id: str
    elo_rating: Decimal | None
    elo_date: str | None
    elo_table_id: str | None
    elo_url: str | None
    arena_rating: Decimal | None
    arena_table_id: str | None
    arena_url: str | None
    elo_date_is_date: bool = False


@dataclass
class PlannedUpdate:
    requests: list[dict[str, Any]] = field(default_factory=list)
    elo_increases: list[dict[str, str]] = field(default_factory=list)
    elo_peak_updates: int = 0
    arena_peak_updates: int = 0
    metadata_corrections: int = 0


def quantize_rating(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).strip()).quantize(RATING_QUANTUM, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return None


def format_rating(value: Decimal | None) -> str:
    return "n/a" if value is None else f"{value.quantize(RATING_QUANTUM):.2f}"


def comparison_rating(value: Decimal | None) -> Decimal:
    """Treat a blank or n/a spreadsheet rating as zero for peak comparisons."""
    return value if value is not None else ZERO_RATING


def _cell(row_values: list[Mapping[str, Any]], index: int) -> Mapping[str, Any]:
    return row_values[index] if index < len(row_values) else {}


def _cell_text(cell: Mapping[str, Any]) -> str:
    value = cell.get("formattedValue")
    if value is not None:
        return str(value).strip()
    effective = cell.get("effectiveValue") or cell.get("userEnteredValue") or {}
    for key in ("stringValue", "numberValue", "boolValue", "formulaValue"):
        if key in effective:
            return str(effective[key]).strip()
    return ""


def _cell_number(cell: Mapping[str, Any]) -> Decimal | None:
    effective = cell.get("effectiveValue") or {}
    for key in ("numberValue", "stringValue"):
        if key in effective:
            result = quantize_rating(effective[key])
            if result is not None:
                return result
    text = _cell_text(cell).replace(",", "")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    return quantize_rating(match.group(0)) if match else None


def _cell_formula(cell: Mapping[str, Any]) -> str:
    entered = cell.get("userEnteredValue") or {}
    return str(entered.get("formulaValue") or "")


def _extract_formula_url(formula: str) -> str | None:
    if not formula:
        return None
    match = re.search(r"HYPERLINK\(\s*[\"']([^\"']+)[\"']", formula, re.IGNORECASE)
    return match.group(1).strip() if match else None


def cell_url(cell: Mapping[str, Any]) -> str | None:
    value = cell.get("hyperlink")
    if value:
        return str(value).strip()
    return _extract_formula_url(_cell_formula(cell))


def normalize_table_id(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_date_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%y-%m-%d", "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date().strftime("%Y-%m-%d")
        except ValueError:
            pass
    return text


def _row_to_sheet_row(
    title: str,
    sheet_id: int,
    row_number: int,
    values: list[Mapping[str, Any]],
) -> SheetRow | None:
    # The requested range starts at C, so these indexes are C, F, G, H, K, M, N.
    name = _cell_text(_cell(values, 0))
    elo_cell = _cell(values, 3)
    date_cell = _cell(values, 4)
    arena_cell = _cell(values, 5)
    player_id = _cell_text(_cell(values, 8))
    elo_table = normalize_table_id(_cell_text(_cell(values, 10)))
    arena_table = normalize_table_id(_cell_text(_cell(values, 11)))
    if not player_id:
        return None
    return SheetRow(
        sheet_title=title,
        sheet_id=int(sheet_id),
        row_number=int(row_number),
        name=name,
        player_id=player_id,
        elo_rating=_cell_number(elo_cell),
        # Keep the displayed text so legacy YY-MM-DD values are corrected.
        elo_date=_cell_text(date_cell),
        elo_table_id=elo_table,
        elo_url=cell_url(elo_cell),
        arena_rating=_cell_number(arena_cell),
        arena_table_id=arena_table,
        arena_url=cell_url(arena_cell),
        elo_date_is_date="numberValue" in (date_cell.get("userEnteredValue") or {}),
    )


def parse_sheet_rows(payload: Mapping[str, Any]) -> list[SheetRow]:
    sheets_by_title = {
        str(item.get("properties", {}).get("title")): item
        for item in payload.get("sheets", [])
    }
    rows: list[SheetRow] = []
    for title in SHEET_TABS:
        sheet = sheets_by_title.get(title)
        if not sheet:
            raise ValueError(f"Required spreadsheet tab is missing: {title}")
        sheet_id = sheet.get("properties", {}).get("sheetId")
        for grid in sheet.get("data", []):
            start_row = int(grid.get("startRow", 0))
            for offset, row_data in enumerate(grid.get("rowData", [])):
                row = _row_to_sheet_row(
                    title,
                    int(sheet_id),
                    start_row + offset + 1,
                    list(row_data.get("values", [])),
                )
                if row:
                    rows.append(row)
    return rows


def build_peak_query(source_table: str = SOURCE_TABLE) -> str:
    return f"""
WITH source AS (
  SELECT
    CAST(player_id AS STRING) AS player_id,
    SAFE_CAST(post_match_elo AS FLOAT64) AS elo_rating,
    SAFE_CAST(post_match_arena_rating AS FLOAT64) AS arena_rating,
    CAST(table_id AS STRING) AS table_id,
    CAST(url AS STRING) AS url,
    SAFE_CAST(game_ended_at AS TIMESTAMP) AS game_ended_at
  FROM `{source_table}`
  WHERE CAST(player_id AS STRING) IN UNNEST(@player_ids)
),
elo_peak AS (
  SELECT
    player_id,
    elo_rating,
    table_id AS elo_table_id,
    url AS elo_url,
    FORMAT_DATE('%Y-%m-%d', DATE(game_ended_at)) AS elo_date
  FROM source
  WHERE elo_rating IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY player_id
    ORDER BY elo_rating DESC, game_ended_at DESC, table_id DESC, url DESC
  ) = 1
),
arena_peak AS (
  SELECT
    player_id,
    arena_rating,
    table_id AS arena_table_id,
    url AS arena_url
  FROM source
  WHERE arena_rating IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY player_id
    ORDER BY arena_rating DESC, game_ended_at DESC, table_id DESC, url DESC
  ) = 1
)
SELECT
  COALESCE(e.player_id, a.player_id) AS player_id,
  e.elo_rating,
  e.elo_table_id,
  e.elo_url,
  e.elo_date,
  a.arena_rating,
  a.arena_table_id,
  a.arena_url
FROM elo_peak e
FULL OUTER JOIN arena_peak a USING (player_id)
"""


def _row_value(row: Any, name: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(name)
    return getattr(row, name, None)


def query_peaks(
    client: BigQueryClientLike,
    player_ids: Iterable[str],
    source_table: str = SOURCE_TABLE,
) -> dict[str, dict[str, PeakRecord | None]]:
    ids = list(dict.fromkeys(str(value).strip() for value in player_ids if str(value).strip()))
    if not ids:
        return {}
    try:
        from google.cloud import bigquery
    except ImportError as exc:  # pragma: no cover - only relevant to broken deployment
        raise RuntimeError("google-cloud-bigquery is required") from exc
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ArrayQueryParameter("player_ids", "STRING", ids)]
    )
    result = client.query(build_peak_query(source_table), job_config=job_config).result()
    peaks: dict[str, dict[str, PeakRecord | None]] = {}
    for row in result:
        player_id = normalize_table_id(_row_value(row, "player_id"))
        if not player_id:
            continue
        elo_value = quantize_rating(_row_value(row, "elo_rating"))
        arena_value = quantize_rating(_row_value(row, "arena_rating"))
        peaks[player_id] = {
            "elo": (
                PeakRecord(
                    elo_value,
                    normalize_table_id(_row_value(row, "elo_table_id")) or "",
                    normalize_table_id(_row_value(row, "elo_url")),
                    _parse_date_text(_row_value(row, "elo_date")),
                )
                if elo_value is not None
                else None
            ),
            "arena": (
                PeakRecord(
                    arena_value,
                    normalize_table_id(_row_value(row, "arena_table_id")) or "",
                    normalize_table_id(_row_value(row, "arena_url")),
                )
                if arena_value is not None
                else None
            ),
        }
    return peaks


def _update_cell_request(
    sheet_id: int,
    row_number: int,
    column: int,
    cell_data: Mapping[str, Any],
    fields: str,
) -> dict[str, Any]:
    return {
        "updateCells": {
            "start": {
                "sheetId": int(sheet_id),
                "rowIndex": int(row_number) - 1,
                "columnIndex": int(column),
            },
            "rows": [{"values": [dict(cell_data)]}],
            "fields": fields,
        }
    }


def _linked_number_request(
    row: SheetRow,
    column: int,
    value: Decimal,
    url: str | None,
    force_two_decimals: bool = False,
) -> dict[str, Any]:
    text_format = {"link": {"uri": url} if url else {}}
    user_format: dict[str, Any] = {"textFormat": text_format}
    fields = "userEnteredValue,userEnteredFormat.textFormat.link"
    if force_two_decimals:
        user_format["numberFormat"] = {"type": "NUMBER", "pattern": "0.00"}
        fields += ",userEnteredFormat.numberFormat"
    return _update_cell_request(
        row.sheet_id,
        row.row_number,
        column,
        {"userEnteredValue": {"numberValue": float(value)}, "userEnteredFormat": user_format},
        fields,
    )


def _link_only_request(row: SheetRow, column: int, url: str | None) -> dict[str, Any]:
    return _update_cell_request(
        row.sheet_id,
        row.row_number,
        column,
        {"userEnteredFormat": {"textFormat": {"link": {"uri": url} if url else {}}}},
        "userEnteredFormat.textFormat.link",
    )


def _string_request(row: SheetRow, column: int, value: str | None) -> dict[str, Any]:
    return _update_cell_request(
        row.sheet_id,
        row.row_number,
        column,
        {"userEnteredValue": {"stringValue": value or ""}},
        "userEnteredValue",
    )


def _date_request(row: SheetRow, column: int, value: str | None) -> dict[str, Any]:
    if not value:
        return _string_request(row, column, value)
    parsed = date.fromisoformat(value)
    serial = (parsed - date(1899, 12, 30)).days
    return _update_cell_request(
        row.sheet_id,
        row.row_number,
        column,
        {
            "userEnteredValue": {"numberValue": serial},
            "userEnteredFormat": {
                "numberFormat": {"type": "DATE", "pattern": "yyyy-mm-dd"}
            },
        },
        "userEnteredValue,userEnteredFormat.numberFormat",
    )


def _same_text(left: str | None, right: str | None) -> bool:
    return (left or "").strip() == (right or "").strip()


def _record_request(
    update: PlannedUpdate,
    request: dict[str, Any],
    key: tuple[int, int, int],
) -> None:
    # A row/category should never generate two writes to the same cell.  This
    # guard makes the invariant explicit if future rules add another branch.
    existing = getattr(update, "_cell_keys", None)
    if existing is None:
        existing = set()
        setattr(update, "_cell_keys", existing)
    if key not in existing:
        existing.add(key)
        update.requests.append(request)


def plan_row_update(row: SheetRow, peaks: Mapping[str, PeakRecord | None]) -> PlannedUpdate:
    update = PlannedUpdate()
    elo_peak = peaks.get("elo")
    if elo_peak is not None:
        if row.elo_rating is None or elo_peak.rating > row.elo_rating:
            _record_request(
                update,
                _linked_number_request(row, COL_ELO, elo_peak.rating, elo_peak.url, True),
                (row.sheet_id, row.row_number, COL_ELO),
            )
            _record_request(
                update,
                _date_request(row, COL_ELO_DATE, elo_peak.date_text),
                (row.sheet_id, row.row_number, COL_ELO_DATE),
            )
            _record_request(
                update,
                _string_request(row, COL_ELO_TABLE, elo_peak.table_id),
                (row.sheet_id, row.row_number, COL_ELO_TABLE),
            )
            update.elo_peak_updates += 1
            if row.sheet_title in {"Masters", "Experts"}:
                update.elo_increases.append(
                    {
                        "name": row.name,
                        "old": format_rating(row.elo_rating),
                        "new": format_rating(elo_peak.rating),
                    }
                )
        elif elo_peak.rating == row.elo_rating:
            if not _same_text(row.elo_date, elo_peak.date_text) or not row.elo_date_is_date:
                _record_request(
                    update,
                    _date_request(row, COL_ELO_DATE, elo_peak.date_text),
                    (row.sheet_id, row.row_number, COL_ELO_DATE),
                )
                update.metadata_corrections += 1
            if not _same_text(row.elo_table_id, elo_peak.table_id):
                _record_request(
                    update,
                    _string_request(row, COL_ELO_TABLE, elo_peak.table_id),
                    (row.sheet_id, row.row_number, COL_ELO_TABLE),
                )
                update.metadata_corrections += 1
            if not _same_text(row.elo_url, elo_peak.url):
                _record_request(
                    update,
                    _link_only_request(row, COL_ELO, elo_peak.url),
                    (row.sheet_id, row.row_number, COL_ELO),
                )
                update.metadata_corrections += 1

    arena_peak = peaks.get("arena")
    if arena_peak is not None:
        if arena_peak.rating > comparison_rating(row.arena_rating):
            _record_request(
                update,
                _linked_number_request(row, COL_ARENA, arena_peak.rating, arena_peak.url),
                (row.sheet_id, row.row_number, COL_ARENA),
            )
            _record_request(
                update,
                _string_request(row, COL_ARENA_TABLE, arena_peak.table_id),
                (row.sheet_id, row.row_number, COL_ARENA_TABLE),
            )
            update.arena_peak_updates += 1
        elif arena_peak.rating == row.arena_rating:
            if not _same_text(row.arena_table_id, arena_peak.table_id):
                _record_request(
                    update,
                    _string_request(row, COL_ARENA_TABLE, arena_peak.table_id),
                    (row.sheet_id, row.row_number, COL_ARENA_TABLE),
                )
                update.metadata_corrections += 1
            if not _same_text(row.arena_url, arena_peak.url):
                _record_request(
                    update,
                    _link_only_request(row, COL_ARENA, arena_peak.url),
                    (row.sheet_id, row.row_number, COL_ARENA),
                )
                update.metadata_corrections += 1
    return update


def build_discord_messages(
    elo_increases: Iterable[Mapping[str, str]],
    today: date,
) -> list[str]:
    increases = list(elo_increases)
    increases.sort(
        key=lambda item: quantize_rating(item.get("new")) or ZERO_RATING,
        reverse=True,
    )
    header = f"__**New elo peaks: {today.isoformat()}**__"
    lines = [
        f"- __{item.get('name', '')}:__ {item.get('old', 'n/a')} → **{item.get('new', 'n/a')}**"
        for item in increases
    ] or ["- None"]
    chunks: list[str] = []
    current = header
    for line in lines:
        candidate = f"{current}\n{line}"
        if len(candidate) > MAX_DISCORD_CONTENT and current != header:
            chunks.append(current)
            current = f"__**New elo peaks: {today.isoformat()} (continued)**__\n{line}"
        else:
            current = candidate
    chunks.append(current)
    return chunks


class MemoryStateStore:
    """Small in-memory state store used by tests and local dry runs."""

    def __init__(self) -> None:
        self.values: dict[str, MutableMapping[str, Any]] = {}

    def load(self, run_id: str) -> MutableMapping[str, Any] | None:
        value = self.values.get(run_id)
        return json.loads(json.dumps(value)) if value is not None else None

    def create(self, run_id: str, payload: Mapping[str, Any]) -> MutableMapping[str, Any]:
        if run_id in self.values:
            return self.load(run_id) or {}
        self.values[run_id] = json.loads(json.dumps(payload))
        return self.load(run_id) or {}

    def save(self, run_id: str, payload: Mapping[str, Any]) -> MutableMapping[str, Any]:
        self.values[run_id] = json.loads(json.dumps(payload))
        return self.load(run_id) or {}


class GcsStateStore:
    def __init__(self, bucket_name: str = STATE_BUCKET, prefix: str = STATE_PREFIX) -> None:
        try:
            from google.cloud import storage
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("google-cloud-storage is required") from exc
        self.client = storage.Client()
        self.bucket = self.client.bucket(bucket_name)
        self.prefix = prefix.strip("/")

    def _blob(self, run_id: str) -> Any:
        safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", run_id)
        return self.bucket.blob(f"{self.prefix}/{safe_id}.json")

    @staticmethod
    def _decode(blob: Any) -> MutableMapping[str, Any]:
        return json.loads(blob.download_as_text())

    def load(self, run_id: str) -> MutableMapping[str, Any] | None:
        blob = self._blob(run_id)
        try:
            blob.reload()
        except Exception as exc:
            if exc.__class__.__name__ in {"NotFound", "NotFoundError"}:
                return None
            raise
        return self._decode(blob)

    def create(self, run_id: str, payload: Mapping[str, Any]) -> MutableMapping[str, Any]:
        blob = self._blob(run_id)
        data = json.dumps(payload, sort_keys=True)
        try:
            blob.upload_from_string(data, content_type="application/json", if_generation_match=0)
        except Exception as exc:
            if exc.__class__.__name__ not in {"PreconditionFailed", "PreconditionFailedError"}:
                raise
            existing = self.load(run_id)
            if existing is None:
                raise
            return existing
        return dict(payload)

    def save(self, run_id: str, payload: Mapping[str, Any]) -> MutableMapping[str, Any]:
        blob = self._blob(run_id)
        blob.upload_from_string(json.dumps(payload, sort_keys=True), content_type="application/json")
        return dict(payload)


def _make_sheets_service() -> Any:
    try:
        import google.auth
        from googleapiclient.discovery import build
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Google Sheets dependencies are required") from exc
    credentials, _ = google.auth.default(scopes=[SHEETS_SCOPE])
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def _make_bigquery_client() -> Any:
    from google.cloud import bigquery

    return bigquery.Client()


def read_sheet_rows(service: SheetsServiceLike, spreadsheet_id: str = SHEET_ID) -> list[SheetRow]:
    ranges = [f"'{title}'!C:N" for title in SHEET_TABS]
    payload = (
        service.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            ranges=ranges,
            includeGridData=True,
            fields=(
                "sheets(properties(sheetId,title),"
                "data(startRow,rowData(values(effectiveValue,formattedValue,"
                "hyperlink,userEnteredValue))))"
            ),
        )
        .execute()
    )
    return parse_sheet_rows(payload)


def apply_sheet_requests(
    service: SheetsServiceLike,
    requests: list[dict[str, Any]],
    spreadsheet_id: str = SHEET_ID,
) -> None:
    if not requests:
        return
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": requests},
    ).execute()


def post_discord(webhook_url: str, content: str) -> None:
    request = urllib.request.Request(
        webhook_url,
        data=json.dumps({"content": content}).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "ark-nova-elo-peak-updater/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if not 200 <= int(response.status) < 300:
                raise RuntimeError(f"Discord webhook returned HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Discord webhook returned HTTP {exc.code}") from exc


def _scheduled_run_id(headers: Mapping[str, str] | None, now: datetime) -> str:
    headers = headers or {}
    schedule_time = headers.get("X-CloudScheduler-ScheduleTime")
    if schedule_time:
        try:
            parsed_schedule_time = datetime.fromisoformat(schedule_time.replace("Z", "+00:00"))
            if parsed_schedule_time.tzinfo is None:
                parsed_schedule_time = parsed_schedule_time.replace(tzinfo=timezone.utc)
            current_time = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
            schedule_time_utc = parsed_schedule_time.astimezone(timezone.utc)
            current_time_utc = current_time.astimezone(timezone.utc)
            if schedule_time_utc <= current_time_utc + timedelta(minutes=5):
                return "scheduled-" + re.sub(r"[^0-9A-Za-z_.-]", "_", schedule_time)
            LOGGER.warning(
                "Ignoring future Cloud Scheduler schedule time %s for manual invocation",
                schedule_time,
            )
        except ValueError:
            LOGGER.warning("Ignoring invalid Cloud Scheduler schedule time %s", schedule_time)
    return "manual-" + now.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]


def execute_update(
    *,
    sheets_service: SheetsServiceLike,
    bigquery_client: BigQueryClientLike,
    state_store: StateStoreLike,
    webhook_sender: Callable[[str, str], None],
    webhook_url: str,
    run_id: str,
    now: datetime | None = None,
    spreadsheet_id: str = SHEET_ID,
    source_table: str = SOURCE_TABLE,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    state = state_store.load(run_id)
    if state is None:
        rows = read_sheet_rows(sheets_service, spreadsheet_id)
        peaks = query_peaks(bigquery_client, (row.player_id for row in rows), source_table)
        combined = PlannedUpdate()
        for row in rows:
            row_update = plan_row_update(row, peaks.get(row.player_id, {}))
            combined.requests.extend(row_update.requests)
            combined.elo_increases.extend(row_update.elo_increases)
            combined.elo_peak_updates += row_update.elo_peak_updates
            combined.arena_peak_updates += row_update.arena_peak_updates
            combined.metadata_corrections += row_update.metadata_corrections
        discord_messages = build_discord_messages(combined.elo_increases, now.date())
        state = {
            "run_id": run_id,
            "created_at": now.isoformat(),
            "requests": combined.requests,
            "discord_messages": discord_messages,
            "rows_seen": len(rows),
            "rows_with_ids": len(rows),
            "database_players_found": len(peaks),
            "elo_peak_updates": combined.elo_peak_updates,
            "arena_peak_updates": combined.arena_peak_updates,
            "metadata_corrections": combined.metadata_corrections,
            "sheet_update_applied": False,
            "notification_sent": False,
        }
        state = state_store.create(run_id, state)

    if not state.get("sheet_update_applied", False):
        apply_sheet_requests(sheets_service, state.get("requests", []), spreadsheet_id)
        state["sheet_update_applied"] = True
        state_store.save(run_id, state)

    if not state.get("notification_sent", False):
        for content in state.get("discord_messages", []):
            webhook_sender(webhook_url, content)
        state["notification_sent"] = True
        state_store.save(run_id, state)

    state["status"] = "ok"
    state["discord_messages_sent"] = len(state.get("discord_messages", []))
    return dict(state)


def handle_http_request(request: Any) -> tuple[str, int, dict[str, str]]:
    if getattr(request, "method", "POST") != "POST":
        return json.dumps({"status": "error", "message": "POST required"}), 405, {
            "Content-Type": "application/json"
        }
    webhook_url = os.environ.get(DISCORD_WEBHOOK_ENV)
    if not webhook_url:
        LOGGER.error("Missing %s secret", DISCORD_WEBHOOK_ENV)
        return json.dumps({"status": "error", "message": "Webhook secret is not configured"}), 500, {
            "Content-Type": "application/json"
        }
    now = datetime.now(timezone.utc)
    try:
        result = execute_update(
            sheets_service=_make_sheets_service(),
            bigquery_client=_make_bigquery_client(),
            state_store=GcsStateStore(),
            webhook_sender=post_discord,
            webhook_url=webhook_url,
            run_id=_scheduled_run_id(getattr(request, "headers", {}), now),
            now=now,
        )
        safe_result = {key: value for key, value in result.items() if key != "requests"}
        return json.dumps(safe_result, sort_keys=True), 200, {"Content-Type": "application/json"}
    except Exception:
        LOGGER.exception("Elo peak update failed")
        return json.dumps({"status": "error", "message": "Elo peak update failed"}), 500, {
            "Content-Type": "application/json"
        }
