"""Validated metadata imports used when staging a private DuckDB generation.

The public dashboard must not query Google Sheets on demand.  These helpers
fetch the current metadata once during generation construction, normalize it,
and materialize it into the generation before activation.  A caller can keep a
last-known-good normalized payload if a later fetch is temporarily unavailable.
"""

from __future__ import annotations

import csv
import hashlib
import io
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping


TOURNAMENT_SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1wJnQFXgaWa3rCUTOZpNwVETCn5fMtGo6IhjzUKlOWCs/export"
    "?format=csv&gid=1099485726"
)
TOURNAMENT_REQUIRED_COLUMNS = ("table_id", "tournament_name", "season")
ARENA_REQUIRED_COLUMNS = ("Season", "Start (UTC)", "End (UTC)", "Mode")


class MetadataValidationError(ValueError):
    """Raised when external metadata cannot be safely imported."""


def _source_info(raw: bytes, row_count: int) -> dict[str, Any]:
    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "row_count": row_count,
    }


def _read_csv(raw: bytes, required: Iterable[str], source: str) -> list[dict[str, str]]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise MetadataValidationError(f"{source} is not UTF-8 CSV") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    fields = tuple(reader.fieldnames or ())
    missing = [name for name in required if name not in fields]
    if missing:
        raise MetadataValidationError(
            f"{source} is missing required columns: {', '.join(missing)}"
        )
    return [
        {str(key): str(value or "").strip() for key, value in row.items() if key}
        for row in reader
    ]


def _positive_table_id(value: str, source: str, row_number: int) -> int:
    try:
        table_id = int(value)
    except (TypeError, ValueError) as exc:
        raise MetadataValidationError(
            f"{source} row {row_number}: table_id must be an integer"
        ) from exc
    if table_id <= 0:
        raise MetadataValidationError(f"{source} row {row_number}: table_id must be positive")
    return table_id


def parse_tournament_csv(raw: bytes, source: str = "tournament sheet") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Normalize the live tournament sheet and return rows plus provenance."""

    rows = _read_csv(raw, TOURNAMENT_REQUIRED_COLUMNS, source)
    normalized: list[dict[str, Any]] = []
    by_id: dict[int, tuple[str, str]] = {}
    for row_number, row in enumerate(rows, 2):
        if not row["table_id"] and not row["tournament_name"] and not row["season"]:
            continue
        table_id = _positive_table_id(row["table_id"], source, row_number)
        name = row["tournament_name"]
        season = row["season"]
        if not name or not season:
            raise MetadataValidationError(
                f"{source} row {row_number}: tournament_name and season are required"
            )
        identity = (name, season)
        prior = by_id.get(table_id)
        if prior is not None and prior != identity:
            raise MetadataValidationError(
                f"{source} row {row_number}: table_id {table_id} has conflicting metadata"
            )
        if prior is None:
            by_id[table_id] = identity
            normalized.append({
                "table_id": table_id,
                "tournament_name": name,
                "season": season,
            })
    return normalized, _source_info(raw, len(normalized))


def fetch_tournament_metadata(
    fetch: Callable[[str], bytes] | None = None,
    url: str = TOURNAMENT_SHEET_CSV_URL,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch and normalize the current tournament sheet."""

    if fetch is None:
        def fetch_url(source_url: str) -> bytes:
            with urllib.request.urlopen(source_url, timeout=30) as response:
                return response.read()
        fetch = fetch_url
    raw = fetch(url)
    return parse_tournament_csv(raw, url)


def _parse_utc(value: str, source: str, row_number: int) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MetadataValidationError(
            f"{source} row {row_number}: invalid UTC timestamp {value!r}"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def parse_arena_settings_csv(raw: bytes, source: str = "arena settings") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Normalize Arena season windows and modes from the local CSV."""

    rows = _read_csv(raw, ARENA_REQUIRED_COLUMNS, source)
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row_number, row in enumerate(rows, 2):
        if not any(row.values()):
            continue
        season = row["Season"]
        mode = row["Mode"].strip().lower()
        if not season or mode not in {"mw", "base"}:
            raise MetadataValidationError(
                f"{source} row {row_number}: Season and Mode (Base or MW) are required"
            )
        if season in seen:
            raise MetadataValidationError(f"{source} row {row_number}: duplicate season {season}")
        start = _parse_utc(row["Start (UTC)"], source, row_number)
        end = _parse_utc(row["End (UTC)"], source, row_number)
        if start >= end:
            raise MetadataValidationError(f"{source} row {row_number}: start must precede end")
        seen.add(season)
        normalized.append({
            "season": season,
            "start_utc": start,
            "end_utc": end,
            "mode": mode,
        })
    return normalized, _source_info(raw, len(normalized))


def load_arena_settings(path: str | Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read and normalize the repository's current Arena settings CSV."""

    path = Path(path)
    raw = path.read_bytes()
    return parse_arena_settings_csv(raw, str(path))


def materialize_metadata_tables(
    connection,
    tournament_rows: Iterable[Mapping[str, Any]],
    arena_rows: Iterable[Mapping[str, Any]],
) -> None:
    """Create and populate metadata relations in a writable staging database."""

    connection.execute("DROP TABLE IF EXISTS tournament_tables_metadata")
    connection.execute("DROP TABLE IF EXISTS arena_seasons_metadata")
    connection.execute(
        "CREATE TABLE tournament_tables_metadata("
        "table_id BIGINT PRIMARY KEY, tournament_name VARCHAR NOT NULL, season VARCHAR NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE arena_seasons_metadata("
        "season VARCHAR PRIMARY KEY, start_utc TIMESTAMPTZ NOT NULL, "
        "end_utc TIMESTAMPTZ NOT NULL, mode VARCHAR NOT NULL)"
    )
    tournament_values = [
        (int(row["table_id"]), str(row["tournament_name"]), str(row["season"]))
        for row in tournament_rows
    ]
    arena_values = [
        (str(row["season"]), row["start_utc"], row["end_utc"], str(row["mode"]))
        for row in arena_rows
    ]
    if tournament_values:
        connection.executemany(
            "INSERT INTO tournament_tables_metadata VALUES (?, ?, ?)",
            tournament_values,
        )
    if arena_values:
        connection.executemany(
            "INSERT INTO arena_seasons_metadata VALUES (?, ?, ?, ?)",
            arena_values,
        )
