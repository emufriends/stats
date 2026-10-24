"""Build the authoritative artifact set for one inactive DuckDB generation.

The builder is deliberately file-oriented: it writes complete route snapshots,
player indexes, Home and Arena assets, and the default pack without mutating the
public bucket. Every full run emits a hashed release manifest. Bounded chunks
keep large combination views from requiring one giant query result in memory.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

from phase3_duckdb_service import (
    GenerationManager, PHASE4_NATIVE_ROUTES, PUBLIC_CONTRACT_SCHEMA_VERSION,
    _load_duckdb, _utc_now, create_private_adapter, Phase3ResponseCache, _project_arena_bundle,
    _json_safe, project_ordinary_ci_fields, Phase3RequestAdapter,
)
from phase2_local_vertical_slice import _merge_player_rows
from phase4_local_routes import _final_arena_sql, _final_records_sql
from phase5_component_ci import OfflineComponentCIs
from phase5_refresh_metrics import measure_resources
from phase5_refresh_dependencies import LOG_RELATIONS


ARTIFACT_MANIFEST_SCHEMA_VERSION = 1
DEFAULT_PACK_SCHEMA_VERSION = 23
APP_ROOT = Path(__file__).resolve().parent


class _ProfileSink(list):
    """Measurement records, also appended line-by-line so a killed run keeps them.

    Numbers and fixed labels only (page/view/season ids); never SQL, row values or
    player names. Written next to, never inside, the published artifacts.
    """
    def __init__(self, journal_path: Path):
        super().__init__()
        self.journal_path = journal_path

    def append(self, record):
        super().append(record)
        try:
            with self.journal_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
        except OSError:
            pass


_PROFILE = None  # active _ProfileSink while a build runs; None disables measuring


def _measure(label: str, **labels):
    """Resource window for one build step; a no-op context when not profiling."""
    if _PROFILE is None:
        return contextlib.nullcontext({})
    return measure_resources(_PROFILE, label, **labels)


class OfflineDiskResponseCache(Phase3ResponseCache):
    """Serial snapshot cache without retaining a second decoded response in RAM.

    Persistence returns a freshly decoded object on each read, preserving caller
    mutation isolation without deepcopy. Live serving keeps its ordinary cache.
    """
    def get(self, key):
        return self.persistent.get(key) if self.persistent is not None else None

    def put(self, key, value):
        if self.persistent is not None:
            self.persistent.put(key, value)


def _write_json(path: Path, payload: dict) -> None:
    """Stream canonical JSON; do not allocate a second full-size payload string."""
    with path.open('w', encoding='utf-8') as target:
        json.dump(payload, target, ensure_ascii=False, separators=(',', ':'))
        target.write('\n')


def _write_json_file_members(path: Path, payload: dict, field: str, members: dict[str, Path]) -> None:
    """Assemble Arena from canonical private spools without decoding histories.

    Each member is written by _write_json in this serial build, never supplied
    externally. Copy its exact UTF-8 bytes in bounded chunks, omitting only the
    writer's final line ending. Public numbers, escaping and insertion order are
    untouched; independent artifact/default-pack validation remains unchanged.
    """
    def encoded(value):
        return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')

    with path.open('wb') as target:
        target.write(b'{')
        for index, (key, value) in enumerate(payload.items()):
            if index:
                target.write(b',')
            target.write(encoded(key)+b':')
            if key != field:
                target.write(encoded(value))
                continue
            target.write(b'{')
            for member_index, (member_key, member_path) in enumerate(members.items()):
                if member_index:
                    target.write(b',')
                target.write(encoded(member_key)+b':')
                _copy_private_json_object(member_path, target)
            target.write(b'}')
        target.write(b'}'+os.linesep.encode('ascii'))


def _copy_private_json_object(path: Path, target) -> None:
    """Copy a completed internal object spool, excluding its LF/CRLF terminator.

    Boundary checks detect incomplete/non-object spools, not arbitrary JSON
    syntax: callers own canonical production, while release validators own full
    artifact validation. Do not reuse this helper for external-source JSON.
    """
    with path.open('rb') as source:
        size = source.seek(0, os.SEEK_END)
        if size < 3:
            raise ValueError('incomplete private JSON spool')
        source.seek(max(0, size-3))
        ending = source.read()
        newline = 2 if ending.endswith(b'}\r\n') else 1 if ending.endswith(b'}\n') else 0
        source.seek(0)
        if not newline or source.read(1) != b'{':
            raise ValueError('noncanonical private JSON spool')
        source.seek(0)
        remaining = size-newline
        while remaining:
            chunk = source.read(min(1024*1024, remaining))
            if not chunk:
                raise OSError('private JSON spool truncated during assembly')
            target.write(chunk)
            remaining -= len(chunk)


ROUTE_PATHS = {
    ("home", "default"): "card-stats/home",
    ("cards", "default"): "card-stats",
    ("opening_hand", "default"): "card-stats/opening-hand",
    ("maps", "metrics"): "card-stats/maps/metrics",
    ("maps", "tournament_h2h"): "card-stats/maps/tournament_h2h",
    ("endgames", "general"): "card-stats/endgames",
    ("endgames", "cp_distribution"): "card-stats/endgames/cp-distribution",
    ("endgames", "cp_by_map"): "card-stats/endgames/cp-by-map",
    ("sponsor_endgames", "cp"): "card-stats/sponsor-endgames/cp",
    ("sponsor_endgames", "appeal"): "card-stats/sponsor-endgames/appeal",
    ("predictors", "general"): "card-stats/predictors/general",
    ("predictors", "icon"): "card-stats/predictors/icon",
    ("predictors", "specific"): "card-stats/predictors/specific",
    ("actions", "starting_position"): "card-stats/actions/starting_position/delta",
    ("actions", "upgrades"): "card-stats/actions/upgrades/delta",
    ("actions", "upgrade_order"): ["card-stats/actions/upgrade_order/delta", "card-stats/actions/upgrade_order/frequency"],
    ("actions", "upgrades_by_map"): ["card-stats/actions/upgrades_by_map/delta", "card-stats/actions/upgrades_by_map/frequency"],
    ("build", "enclosures"): ["card-stats/build/enclosures/delta", "card-stats/build/enclosures/frequency"],
    ("build", "hexes"): ["card-stats/build/hexes/delta", "card-stats/build/hexes/frequency"],
    ("icons", "default"): "card-stats/icons",
    ("conservation", "projects"): "card-stats/conservation/projects",
    ("conservation", "project_rewards"): "card-stats/conservation/project-rewards",
    ("conservation", "cp_rewards"): "card-stats/conservation/cp-rewards",
    ("scoring", "final_score"): "card-stats/scoring/final-score",
    ("scoring", "appeal"): "card-stats/scoring/appeal",
    ("scoring", "conservation_points"): "card-stats/scoring/conservation-points",
    ("scoring", "reputation"): "card-stats/scoring/reputation",
    ("workers", "general"): "card-stats/workers/general",
    ("workers", "two_cp_worker"): "card-stats/workers/two-cp-worker",
    ("players", "general"): "card-stats/players/general",
    ("players", "comparison"): "card-stats/players/comparison",
    ("players", "performance_by_map"): "card-stats/players/performance-by-map",
    ("records", "elo_leaderboard"): "card-stats/records/elo-leaderboard",
    ("records", "fastest_games"): "card-stats/records/fastest-games",
    ("records", "highest_scores"): "card-stats/records/highest-scores",
    ("records", "biggest_turns"): "card-stats/records/biggest-turns",
    ("records", "most_icons"): "card-stats/records/most-icons",
    ("combinations", "card_card"): "card-stats/combinations/card-card",
    ("combinations", "card_map"): "card-stats/combinations/card-map",
    ("combinations", "card_round"): "card-stats/combinations/card-round",
    ("combinations", "card_endgame"): "card-stats/combinations/card-endgame",
    ("combinations", "card_action_card"): "card-stats/combinations/card-action-card",
    ("mw_action_cards", "general"): "card-stats/mw-action-cards/general",
    ("mw_action_cards", "draft"): "card-stats/mw-action-cards/draft",
    ("mw_action_cards", "by_map"): "card-stats/mw-action-cards/by-map",
    ("mw_action_cards", "synergies"): "card-stats/mw-action-cards/synergies",
}

DATASET_PAGES = {
    "home", "cards", "opening_hand", "maps", "endgames", "sponsor_endgames",
    "predictors", "actions", "conservation", "scoring", "workers", "players",
    "combinations", "build", "icons",
}
RECORDS_PAGES = {"records"}
MW_ONLY_PAGES = {"mw_action_cards"}
SPECIAL_BUNDLE = ("arena", "top_100")
STANDARD_MAPS = [
    "Map 1a: Observation Tower", "Map 2a: Outdoor Areas",
    "Map 3a: Silver Lake", "Map 4a: Commercial Harbor",
    "Map 5a: Park Restaurant", "Map 6a: Research Institute",
    "Map 7a: Ice Cream Parlors", "Map 8a: Hollywood Hills",
    "Map 9: Geographical Zoo", "Map 10: Rescue Station",
    "Map 11: Caves", "Map 12: Artificial Intelligence",
    "Map 13: Drawing Board", "Map 14: Lagoon", "Map T1: Tournament 1",
]
ALL_KNOWN_MAPS = STANDARD_MAPS + [
    "Map 1: Observation Tower", "Map 2: Outdoor Areas",
    "Map 3: Silver Lake", "Map 4: Commercial Harbor",
    "Map 5: Park Restaurant", "Map 6: Research Institute",
    "Map 7: Ice Cream Parlors", "Map 8: Hollywood Hills",
    "Map A", "Map 0",
]

# The default pack is a frontend bootstrap optimization, not the complete
# release inventory. Ancillary indexes, Home's parser-loaded bootstrap, Arena's
# all-season bundle, and non-default Players views are still mandatory release
# artifacts and are tracked by the authoritative artifact manifest below.
PACK_EXCLUDED_ROUTES = {
    ("home", "default"),
    ("players", "comparison"),
    ("players", "performance_by_map"),
    ("mw_action_cards", "draft"),
}


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_hash(value) -> str:
    return _sha256_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    )


def _object_key(output_root: Path, path: Path) -> str:
    return path.resolve().relative_to(output_root.resolve()).as_posix()


def _artifact(output_root: Path, path: Path, kind: str, **extra) -> dict:
    return {
        "object_key": _object_key(output_root, path),
        "path": str(path),
        "kind": kind,
        "bytes": path.stat().st_size,
        "sha256": _sha256_file(path),
        **extra,
    }


def _request(page: str, view: str, dataset: int | None, limit: int, offset: int) -> dict:
    if page == "combinations":
        # Every default combination population is comfortably below this
        # bound. One scan avoids page-boundary loss when Minimum hides rows.
        limit = 100000
    request = {"stats_page": page, "limit": limit, "offset": offset}
    if dataset is not None:
        request["is_mw"] = dataset
    fields = {
        "maps": "maps_view", "endgames": "endgames_view",
        "sponsor_endgames": "sponsor_endgames_view", "combinations": "combinations_view",
        "predictors": "predictors_view", "actions": "actions_view",
        "conservation": "conservation_view", "scoring": "scoring_view",
        "workers": "workers_view", "players": "players_view",
        "records": "records_view", "mw_action_cards": "mw_action_cards_view",
        "build": "build_view",
    }
    if page in fields:
        request[fields[page]] = view
    if page == "combinations":
        request["combination_min_plays"] = 1000
    # These values mirror the visible frontend defaults.  Default snapshots
    # must describe the same population as the controls that select them;
    # otherwise an initial page load either shows the wrong population or
    # falls through to an expensive live query.
    if page not in {"home", "arena", "records"} and not (
        page == "maps" and view == "tournament_h2h"
    ):
        request["maps"] = list(STANDARD_MAPS)
    if page == "players":
        request.update(
            opponent_elo_min=0,
            opponent_elo_max=None,
            date_from=None,
            date_to=None,
        )
    elif page not in {"home", "arena", "records"} and not (
        page == "maps" and view == "tournament_h2h"
    ):
        request.update(
            player_elo_min=300,
            player_elo_max=None,
            opponent_elo_min=300,
            opponent_elo_max=None,
            date_from="2025-01-01",
            date_to=None,
        )
    return request


def _component_descriptor(page: str, view: str, row: dict) -> dict:
    if page == "mw_action_cards":
        return {"card_1_key": row.get("card_1_key"), "card_2_key": row.get("card_2_key")}
    if view == "card_card":
        return {"card_1": row.get("card_1"), "card_2": row.get("card_2")}
    if view == "card_map":
        return {"card_name": row.get("card_name"), "map_name": row.get("map_name")}
    if view == "card_round":
        return {"card_name": row.get("card_name"), "round_name": row.get("round_name")}
    if view == "card_endgame":
        return {"card_name": row.get("card_name"), "endgame_name": row.get("endgame_name")}
    return {"card_name": row.get("card_name"), "action_card_key": row.get("action_card_key")}


def _component_key(page: str, view: str, row: dict) -> str:
    descriptor = _component_descriptor(page, view, row)
    if page == "mw_action_cards": values = [descriptor["card_1_key"], descriptor["card_2_key"]]
    elif view == "card_card": values = [descriptor["card_1"], descriptor["card_2"]]
    elif view == "card_map": values = [descriptor["card_name"], descriptor["map_name"]]
    elif view == "card_round": values = [descriptor["card_name"], descriptor["round_name"]]
    elif view == "card_endgame": values = [descriptor["card_name"], descriptor["endgame_name"]]
    else: values = [descriptor["card_name"], descriptor["action_card_key"]]
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


_COMPONENT_CI_SUFFIXES = (
    "mean", "ci95_low", "ci95_high", "ci95_se", "ci95_n", "ci95_cluster_n",
)


def _component_identities(page: str, view: str, row: dict) -> tuple[tuple[str, str] | None, tuple[str, str] | None]:
    """Return the displayed standalone means represented by one pair row."""
    if page == "mw_action_cards":
        return (("action_card", str(row.get("card_1_key"))),
                ("action_card", str(row.get("card_2_key"))))
    if view == "card_card":
        return (("card", str(row.get("card_1"))), ("card", str(row.get("card_2"))))
    if view in {"card_map", "card_round"}:
        # The context EV has its ordinary interval in delta_map/delta_round;
        # only the general card EV is rendered as a standalone component.
        return (("card", str(row.get("card_name"))), None)
    if view == "card_endgame":
        return (("card", str(row.get("card_name"))),
                ("endgame", str(row.get("endgame_name"))))
    return (("card", str(row.get("card_name"))),
            ("action_card", str(row.get("action_card_key"))))


def _attach_component_cis(adapter, page: str, view: str, dataset: int | None, rows: list[dict]) -> None:
    if not rows or not (page == "combinations" or (page == "mw_action_cards" and view == "synergies")):
        return
    offline = getattr(adapter, 'offline_component_cis', None)
    if offline is not None:
        identities = {identity for row in rows for identity in _component_identities(page, view, row)
                      if identity is not None}
        component_values = {}
        for kind in sorted({identity[0] for identity in identities}):
            names = {name for component_kind, name in identities if component_kind == kind}
            values = offline.values(_request(page, view, dataset, 100, 0),
                telemetry=(page == 'mw_action_cards' or view == 'card_action_card'), kind=kind, names=names)
            component_values.update({(kind, name): value for name, value in values.items()})
        for row in rows:
            for index, identity in enumerate(_component_identities(page, view, row), start=1):
                value = component_values.get(identity, {})
                for suffix in _COMPONENT_CI_SUFFIXES:
                    row[f'component_{index}_{suffix}'] = value.get(
                        suffix, 0 if suffix in {'ci95_n', 'ci95_cluster_n'} else None)
        return
    # A full pair snapshot may contain thousands of rows, but the standalone
    # means repeat (for example, one card across twenty action cards). Select a
    # minimal cover of component identities and calculate each interval once.
    selected: list[dict] = []
    covered: set[tuple[str, str]] = set()
    selected_by_key: dict[str, dict] = {}
    for row in rows:
        identities = tuple(value for value in _component_identities(page, view, row) if value)
        if not any(value not in covered for value in identities):
            continue
        selected.append(row)
        selected_by_key[_component_key(page, view, row)] = row
        covered.update(identities)

    base = _request(page, view, dataset, 100, 0)
    component_values: dict[tuple[str, str], dict[str, object]] = {}
    for start in range(0, len(selected), 100):
        descriptors = [_component_descriptor(page, view, row) for row in selected[start:start + 100]]
        response = adapter.execute({**base, "component_ci": True, "component_ci_rows": descriptors})
        for ci in response.get("data") or []:
            source = selected_by_key.get(str(ci.get("row_key") or ""))
            if source is None:
                continue
            for index, identity in enumerate(_component_identities(page, view, source), start=1):
                if identity is None:
                    continue
                component_values[identity] = {
                    suffix: ci.get(f"component_{index}_{suffix}")
                    for suffix in _COMPONENT_CI_SUFFIXES
                }

    for row in rows:
        for index, identity in enumerate(_component_identities(page, view, row), start=1):
            values = component_values.get(identity) if identity is not None else None
            for suffix in _COMPONENT_CI_SUFFIXES:
                row[f"component_{index}_{suffix}"] = (
                    values.get(suffix) if values is not None else
                    (0 if suffix in {"ci95_n", "ci95_cluster_n"} else None)
                )


def _datasets(page: str) -> list[int | None]:
    if page in DATASET_PAGES:
        return [1, 0]
    if page in RECORDS_PAGES:
        # MW and Base Records are DIFFERENT populations for most views (Oct 4 run:
        # most_icons 27,300 vs 15,336 rows; only elo_leaderboard is byte-identical,
        # 0.3 s). Build both; see reports/backend-efficiency-audit-20261005.md.
        return [1, 0]
    if page in MW_ONLY_PAGES:
        return [1]
    return [None]


def expected_snapshot_object_keys() -> tuple[str, ...]:
    """Return the complete publishable snapshot inventory for one full build.

    Keep this derived from the same route, dataset, and path catalogs used by
    the builder.  Validators must compare object identities rather than a
    literal file count: Card + Action Card is MW-only, while several routes
    deliberately emit multiple delta/frequency snapshots.
    """

    specs = sorted(PHASE4_NATIVE_ROUTES | {
        ("cards", "default"),
        ("combinations", "card_card"),
    })
    keys = {
        "card-stats/players/arena-top-100/all-seasons.json",
        "card-stats/players/arena/latest.json",
        "card-stats/players/arena/manifest.json",
    }
    for page, view in specs:
        if (page, view) in {SPECIAL_BUNDLE, ("players", "arena_top_100")}:
            continue
        bases = ROUTE_PATHS.get((page, view))
        if bases is None:
            raise RuntimeError(f"no snapshot path for {page}/{view}")
        if isinstance(bases, str):
            bases = [bases]
        datasets = [1] if (page, view) == ("combinations", "card_action_card") else _datasets(page)
        for dataset in datasets:
            suffix = "mw" if dataset in (None, 1) else "base"
            keys.update(f"{base}/default-{suffix}.json" for base in bases)
    return tuple(sorted(keys))


def _bundle_payload(response: dict) -> dict:
    data = response.get("data")
    seasons = []
    if isinstance(data, dict):
        for season, bucket in data.items():
            seasons.append({
                "season": season,
                "number": bucket.get("number"),
                "mode": bucket.get("mode"),
                "is_mw": bucket.get("is_mw"),
                "start_utc": bucket.get("start_utc"),
                "end_utc": bucket.get("end_utc"),
                "effective_end_utc": bucket.get("effective_end_utc") or bucket.get("end_utc"),
            })
    seasons.sort(key=lambda item: int(item.get("number") or 0), reverse=True)
    return {
        "status": response.get("status", "ok"),
        "source": response.get("source", "duckdb_private"),
        "generation": response.get("generation"),
        "data_version": response.get("data_version"),
        "seasons": seasons,
        "latest_season": seasons[0]["season"] if seasons else None,
        "data": data,
        "row_count": response.get("row_count"),
    }


def _player_filter_seasons(adapter, roster_seasons: list[dict]) -> list[dict]:
    """Return every configured Arena season for Players filters.

    Arena's table/graph bundle remains roster-driven because it can only show
    seasons with an Elite League sheet. Players filtering is metadata-driven:
    an ongoing season is valid as soon as it appears in arena_settings.csv,
    even when no Arena roster has been published yet.
    """
    try:
        with adapter.store.connection() as (_generation, connection):
            rows = connection.execute(
                "SELECT season, CAST(start_utc AS VARCHAR), "
                "CAST(end_utc AS VARCHAR), mode "
                "FROM arena_seasons_metadata"
            ).fetchall()
    except (AttributeError, RuntimeError):
        return list(roster_seasons)

    seasons = []
    for season, start_utc, end_utc, mode in rows:
        season_text = str(season)
        match = re.search(r"(\d+)$", season_text)
        mode_text = str(mode or "").lower()
        seasons.append({
            "season": season_text,
            "number": int(match.group(1)) if match else 0,
            "mode": mode_text,
            "is_mw": mode_text == "mw",
            "start_utc": start_utc.isoformat() if hasattr(start_utc, "isoformat") else str(start_utc),
            "end_utc": end_utc.isoformat() if hasattr(end_utc, "isoformat") else str(end_utc),
            "effective_end_utc": end_utc.isoformat() if hasattr(end_utc, "isoformat") else str(end_utc),
        })
    seasons.sort(key=lambda item: int(item.get("number") or 0), reverse=True)
    return seasons or list(roster_seasons)


def _arena_season_response(adapter, base_request, season, player_ids, chunk=None):
    """Bound ordered history aggregates; preserve full roster/series ordering."""
    chunk = int(os.environ.get('DUCKDB_ARENA_SERIES_BATCH', '512')) if chunk is None else int(chunk)
    if not 1 <= chunk <= 50000:
        raise ValueError('Arena series batch must be between 1 and 50000')
    combined = None
    for start in range(0, max(1, len(player_ids)), chunk):
        selected = player_ids[start:start+chunk]
        response = adapter.execute({**base_request, 'arena_season': season,
            'arena_seasons': [season], 'arena_series_player_ids': selected})
        if combined is None:
            combined = response
            continue
        if response.get('data_version') != combined.get('data_version'):
            raise RuntimeError('Arena history chunks span data versions')
        if set(response.get('data') or {}) != set(combined.get('data') or {}):
            raise RuntimeError('Arena history chunks span different seasons')
        for key, bucket in response['data'].items():
            previous = combined['data'][key]
            identity = lambda row: (row.get('rank'), row.get('player_id'), row.get('player'))
            if ([identity(row) for row in previous['rows']] != [identity(row) for row in bucket['rows']]
                    or [identity(row) for row in previous['series']] != [identity(row) for row in bucket['series']]):
                raise RuntimeError('Arena roster changed between history chunks')
            selected_ids = set(selected)
            for index, series in enumerate(bucket['series']):
                if series.get('player_id') in selected_ids:
                    previous['series'][index] = series
        del response
    return combined


def _arena_offline_histories(adapter, roster_response, season, player_ids):
    """Fill bounded history batches without recomputing full-roster metrics."""
    chunk = int(os.environ.get('DUCKDB_ARENA_SERIES_BATCH', '512'))
    if not 1 <= chunk <= 50000:
        raise ValueError('Arena series batch must be between 1 and 50000')
    buckets = {key: {**bucket, 'series': list(bucket['series'])}
               for key, bucket in roster_response['data'].items()
               if str(bucket.get('season')) == season}
    combined = {**roster_response, 'data': buckets,
                'row_count': sum(len(bucket['rows']) for bucket in buckets.values())}
    identity = lambda row: (row.get('rank'), row.get('player_id'), row.get('player'))
    positions = {key: {identity(row): index for index, row in enumerate(bucket['series'])}
                 for key, bucket in buckets.items()}
    for start in range(0, len(player_ids), chunk):
        selected = player_ids[start:start+chunk]
        sql, parameters = _final_arena_sql({'arena_season': season,
            'arena_series_player_ids': selected}, histories_only=True)
        result = adapter.store.query(sql, parameters)
        for key, bucket in _project_arena_bundle(result['rows']).items():
            if key not in buckets:
                raise RuntimeError('Arena history batch returned another season')
            for series in bucket['series']:
                index = positions[key].get(identity(series))
                if index is None or series.get('player_id') not in selected:
                    raise RuntimeError('Arena history batch returned another roster')
                buckets[key]['series'][index] = series
        del result
    return combined


def build_arena_bundle(adapter, output_root: Path) -> list[dict]:
    """Build the Arena all-season bundle and the two compatibility aliases."""
    base_request = {
        "stats_page": "arena", "arena_view": "top_100", "limit": 1, "offset": 0,
        "arena_seasons": [],
    }
    roster_response = adapter.execute(base_request)
    roster_data = roster_response.get("data") or {}
    season_rows = {
        str(season): bucket.get("rows", [])
        for bucket in roster_data.values() if isinstance(bucket, dict)
        for season in [bucket.get("season")]
        if season and isinstance(bucket.get("rows"), list)
    }
    all_path = output_root / "card-stats/players/arena-top-100/all-seasons.json"
    latest_path = output_root / "card-stats/players/arena/latest.json"
    manifest_path = output_root / "card-stats/players/arena/manifest.json"
    all_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    # History arrays dominate the Arena bundle. Preserve every season and the
    # existing JSON schema, but spool seasons instead of retaining all histories
    # in one Python dictionary alongside DuckDB buffers and serialization copies.
    with tempfile.TemporaryDirectory(prefix='arena-spool-', dir=output_root) as folder:
        metadata = {}
        spools = {}
        counts = {}
        response_template = dict(roster_response)
        for season, rows in season_rows.items():
            player_ids = sorted({int(row['player_id']) for row in rows if row.get('player_id') is not None})
            with _measure('arena_season', season=str(season), players=len(player_ids)):
                response = (_arena_offline_histories(adapter, roster_response, season, player_ids)
                            if hasattr(adapter, 'store') else
                            _arena_season_response(adapter, base_request, season, player_ids))
            for key, bucket in (response.get('data') or {}).items():
                path = Path(folder)/(hashlib.sha256(str(key).encode()).hexdigest()+'.json')
                _write_json(path, bucket)
                spools[key] = path
                counts[key] = len(bucket.get('rows') or [])
                metadata[key] = {name: bucket.get(name) for name in (
                    'number', 'mode', 'is_mw', 'start_utc', 'end_utc', 'effective_end_utc',
                )}
            response_template['data_version'] = response.get('data_version')
            response_template['generated_at'] = response.get('generated_at')
            bucket = None
            del response
        response_template['data'] = metadata
        response_template['row_count'] = sum(counts.values())
        payload = _bundle_payload(response_template)
        if not spools:
            raise RuntimeError('Arena bundle contains no season data')
        payload['generated_at'] = response_template.get('generated_at')
        _write_json_file_members(all_path, payload, 'data', spools)
        latest_season = payload.get('latest_season')
        latest = dict(payload)
        latest['row_count'] = counts.get(latest_season, 0)
        latest_spools = {latest_season: spools[latest_season]} if latest_season else {}
        _write_json_file_members(latest_path, latest, 'data', latest_spools)
    manifest_seasons = _player_filter_seasons(adapter, payload.get("seasons", []))
    manifest = {
        "status": "ok",
        "data_version": payload.get("data_version"),
        "generated_at": payload.get("generated_at"),
        "seasons": manifest_seasons,
        "latest_top_100": latest_season,
    }
    _write_json(manifest_path, manifest)
    common = {"page": "arena", "view": "top_100", "dataset": None, "data_version": payload.get("data_version")}
    return [
        {**common, "path": str(all_path), "row_count": payload.get("row_count"), "bytes": all_path.stat().st_size},
        {**common, "path": str(latest_path), "row_count": latest.get("row_count"), "bytes": latest_path.stat().st_size},
        {**common, "path": str(manifest_path), "row_count": len(manifest["seasons"]), "bytes": manifest_path.stat().st_size},
    ]


def _build_most_icons_stream(adapter, dataset, output, profile):
    """Write the full ordered Records result with one scan and bounded row batches."""
    started = time.perf_counter()
    normalized = adapter.normalize_request(_request('records', 'most_icons', dataset, 10000, 0))
    sql, parameters = _final_records_sql(normalized, 'most_icons', paginate=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='records-icons-', dir=output.parent) as folder:
        spool = Path(folder) / 'rows.json'
        count = 0
        with adapter.store.query_batches(sql, parameters, batch_size=1024) as (generation, batches):
            with spool.open('w', encoding='utf-8') as target:
                target.write('[')
                for batch in batches:
                    for row in batch:
                        if count:
                            target.write(',')
                        json.dump(_json_safe(project_ordinary_ci_fields(row)), target,
                                  ensure_ascii=False, separators=(',', ':'))
                        count += 1
                target.write(']')
            payload = {'status': 'ok', 'source': 'duckdb_private',
                       'generation': generation.generation_id,
                       'data_version': generation.data_version,
                       'view': normalized['view'], 'data': None, 'row_count': count,
                       'cache_status': 'private_miss',
                       'contract_schema_version': PUBLIC_CONTRACT_SCHEMA_VERSION}
        query_seconds = time.perf_counter() - started
        write_started = time.perf_counter()
        with output.open('w', encoding='utf-8') as target:
            target.write('{')
            for index, (key, value) in enumerate(payload.items()):
                if index:
                    target.write(',')
                target.write(json.dumps(key) + ':')
                if key == 'data':
                    with spool.open(encoding='utf-8') as source:
                        shutil.copyfileobj(source, target, length=64 * 1024)
                else:
                    json.dump(value, target, ensure_ascii=False, separators=(',', ':'))
            target.write('}\n')
        if profile is not None:
            profile.update({'query_seconds': round(query_seconds, 6),
                            'component_ci_seconds': 0.0,
                            'write_seconds': round(time.perf_counter() - write_started, 6),
                            'rows': count, 'bytes': output.stat().st_size,
                            'query_count': 1, 'stream_batch_rows': 1024})
    return {'path': str(output), 'page': 'records', 'view': 'most_icons',
            'dataset': dataset, 'data_version': payload['data_version'],
            'row_count': count, 'bytes': output.stat().st_size,
            'build_seconds': round(time.perf_counter() - started, 6),
            'component_ci_seconds': 0.0}


def build_one(adapter, page: str, view: str, dataset: int | None, output: Path, chunk: int,
              profile: dict | None = None) -> dict:
    # `profile` (optional) receives a time split for measurement only; it is
    # never written into the published snapshot or manifest.
    started = time.perf_counter()
    if page == 'records' and view == 'most_icons' and isinstance(adapter, Phase3RequestAdapter):
        return _build_most_icons_stream(adapter, dataset, output, profile)
    # Records' ordered icon/score populations are substantially larger than
    # metric catalogues. Use bounded 10k batches so snapshot pagination does not
    # repeat the same broad scan/sort dozens of times. Live pagination is local
    # and unchanged; every row is still included, including future overflow.
    if page == 'records':
        chunk = max(chunk, 10000)
    first_request = _request(page, view, dataset, chunk, 0)
    first = adapter.execute(first_request)
    effective_limit = first_request['limit']
    data = first.get("data")
    if page == "arena":
        payload = _bundle_payload(first)
    elif not isinstance(data, list):
        payload = first
    else:
        rows = list(data)
        offset = len(rows)
        # Some routes intentionally request a larger one-scan catalogue. Test
        # the actual request limit, not the caller's diagnostic chunk size.
        while len(data) == effective_limit:
            next_response = adapter.execute(_request(page, view, dataset, chunk, offset))
            data = next_response.get("data") or []
            rows.extend(data)
            offset += len(data)
        payload = dict(first)
        payload["data"] = rows
        payload["row_count"] = len(rows)
    query_seconds = time.perf_counter() - started
    if isinstance(payload.get("data"), list):
        ci_started = time.perf_counter()
        _attach_component_cis(adapter, page, view, dataset, payload["data"])
        ci_seconds = time.perf_counter() - ci_started
    else:
        ci_seconds = 0.0
    output.parent.mkdir(parents=True, exist_ok=True)
    write_started = time.perf_counter()
    _write_json(output, payload)
    if profile is not None:
        profile.update({
            "query_seconds": round(query_seconds, 6),
            "component_ci_seconds": round(ci_seconds, 6),
            "write_seconds": round(time.perf_counter() - write_started, 6),
            "rows": payload.get("row_count"), "bytes": output.stat().st_size,
        })
    return {"path": str(output), "page": page, "view": view, "dataset": dataset,
            "data_version": payload.get("data_version"), "row_count": payload.get("row_count"),
            "bytes": output.stat().st_size,
            "build_seconds": round(time.perf_counter()-started, 6),
            "component_ci_seconds": round(ci_seconds, 6)}


def _build_player_indexes(
    manager: GenerationManager,
    generation_id: str,
    output_root: Path,
    merge_players_path: Path,
) -> list[dict]:
    """Build both autocomplete indexes from the inactive candidate database."""
    generation = manager.inspect(generation_id)
    duckdb = _load_duckdb()
    connection = duckdb.connect(str(generation.database_path), read_only=True)
    try:
        # This ancillary query is outside the adapter, so it must receive the
        # same offline budget rather than DuckDB's machine-wide default.
        connection.execute('SET threads=1')
        connection.execute('SET memory_limit=?', [os.environ.get('DUCKDB_SNAPSHOT_MEMORY_LIMIT', '2000MB')])
        connection.execute('SET preserve_insertion_order=false')
        groups: dict[str, list[str]] = {}
        for player, _casefold, identity in _merge_player_rows(merge_players_path):
            groups.setdefault(identity, []).append(player)
        results = []
        placeholders = ",".join("?" for _ in ALL_KNOWN_MAPS)
        for dataset, suffix in ((1, "mw"), (0, "base")):
            rows = connection.execute(
                f"""
                SELECT DISTINCT TRIM(CAST(player AS VARCHAR)) AS player
                FROM game_player_narrow
                WHERE is_mw = ?
                  AND COALESCE(is_corrupted_game, FALSE) = FALSE
                  AND COALESCE(is_completed_game, FALSE) = TRUE
                  AND map_name IN ({placeholders})
                  AND player IS NOT NULL
                  AND TRIM(CAST(player AS VARCHAR)) <> ''
                ORDER BY player
                """,
                [dataset, *ALL_KNOWN_MAPS],
            ).fetchall()
            players = {str(row[0]) for row in rows if row[0]}
            for members in groups.values():
                if any(member in players for member in members):
                    players.update(members)
            ordered = sorted(players, key=lambda value: (value.casefold(), value))
            path = output_root / f"card-stats/players/index/default-{suffix}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            _write_json(path, {"status": "ok", "players": ordered, "dataset": suffix})
            results.append(_artifact(
                output_root, path, "player_index", dataset=dataset,
                data_version=generation.data_version, row_count=len(ordered),
            ))
        return results
    finally:
        connection.close()


def _build_home_bootstrap(output_root: Path, data_version: str) -> dict:
    mw_path = output_root / "card-stats/home/default-mw.json"
    base_path = output_root / "card-stats/home/default-base.json"
    mw = json.loads(mw_path.read_text(encoding="utf-8"))
    base = json.loads(base_path.read_text(encoding="utf-8"))
    if mw.get("data_version") != data_version or base.get("data_version") != data_version:
        raise RuntimeError("Home bootstrap inputs do not match the candidate data version")
    source = "window.__ARK_NOVA_DATA_VERSION__=" + json.dumps(data_version) + ";"
    source += "window.__ARK_NOVA_HOME_DEFAULTS__=" + json.dumps(
        {"1": mw, "0": base}, ensure_ascii=False, separators=(",", ":")
    ) + ";"
    path = output_root / "card-stats/home/defaults.js"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return _artifact(output_root, path, "home_bootstrap", data_version=data_version)


def _is_pack_member(item: dict) -> bool:
    page_view = (item.get("page"), item.get("view"))
    key = str(item.get("object_key") or "")
    if page_view in PACK_EXCLUDED_ROUTES:
        return False
    if page_view == ("arena", "top_100"):
        return key == "card-stats/players/arena/latest.json"
    return key.endswith(".json")


def _release_versions(root: Path, generation) -> dict:
    # The persistent data root is deliberately separate from the immutable
    # executable bundle. Hash the producer that actually built these payloads,
    # not obsolete scripts that happen to remain beside the databases.
    code_paths = [
        APP_ROOT / "phase2_local_vertical_slice.py",
        APP_ROOT / "phase3_duckdb_service.py",
        APP_ROOT / "phase3_cards_pair_contracts.py",
        APP_ROOT / "phase4_combo_mw_contracts.py",
        APP_ROOT / "phase4_local_scope.py",
        APP_ROOT / "phase4_local_routes.py",
        APP_ROOT / "phase5_snapshot_builder.py",
        APP_ROOT / "phase5_component_ci.py",
    ]
    code = {path.name: _sha256_file(path) for path in code_paths}
    contract_path = APP_ROOT / "contracts" / "dashboard-routes.v1.json"
    contract = _sha256_file(contract_path) if contract_path.is_file() else None
    source = {
        "source_generation": generation.manifest.get("source_generation"),
        "source_materialization": generation.manifest.get("source_materialization"),
    }
    moving = {
        "moving_sources": generation.manifest.get("moving_sources") or {},
        "metadata_sources": generation.manifest.get("metadata_sources") or {},
    }
    return {
        "code_sha256": _canonical_hash(code),
        "code_files": code,
        "contract_sha256": contract,
        "public_contract_schema_version": PUBLIC_CONTRACT_SCHEMA_VERSION,
        "source_sha256": _canonical_hash(source),
        "moving_sources_sha256": _canonical_hash(moving),
    }


def _reusable_snapshot_paths(output_root: Path, generation) -> set[Path]:
    """Reuse only artifacts proven to come from this exact producer/input set."""
    try:
        previous = json.loads((output_root / 'release-manifest.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return set()
    if (previous.get('status') != 'ok'
            or previous.get('generation') != generation.generation_id
            or previous.get('data_version') != generation.data_version
            or previous.get('versions') != _release_versions(output_root, generation)):
        return set()
    paths = set()
    for artifact in previous.get('artifacts') or []:
        if artifact.get('kind') != 'snapshot':
            continue
        path = Path(artifact['path']).resolve()
        if (path.is_relative_to(output_root.resolve()) and path.is_file()
                and path.stat().st_size == artifact.get('bytes')
                and _sha256_file(path) == artifact.get('sha256')):
            paths.add(path)
    return paths


def _qualified_log_snapshot(root, candidate, object_key):
    """Cards/Opening Hand reuse after exact log-fact, code and artifact proof.

    Other routes may have broad Full Sample/context components and are not
    admitted by this proof. The current-version envelope is written only after
    all required facts, producer versions, artifact hash and schema match.
    """
    allowed = {f'{base}/default-{suffix}.json' for base in ('card-stats','card-stats/opening-hand')
               for suffix in ('mw','base')}
    if object_key not in allowed:
        return None
    builder = candidate.manifest.get('builder') or {}
    signature = builder.get('log_dependency')
    if (not isinstance(signature,dict) or signature.get('schema_version') != 2 or not signature.get('engine_version')
        or not set(LOG_RELATIONS).issubset(set(builder.get('reused_relations') or []))):
        return None
    parent = candidate.manifest.get('parent_generation')
    if not isinstance(parent,str) or not parent or any(value in parent for value in ('/','\\','..',':')):
        return None
    parent_root = Path(root)/'phase2_private_data/snapshots'/parent
    try:
        release = json.loads((parent_root/'release-manifest.json').read_text(encoding='utf-8'))
        parent_manifest = json.loads((Path(root)/'phase2_private_data/generations'/(parent+'.manifest.json')).read_text(encoding='utf-8'))
        if (release.get('status') != 'ok' or release.get('generation') != parent
            or (parent_manifest.get('builder') or {}).get('log_dependency') != signature):
            return None
        versions = _release_versions(root,candidate)
        if any((release.get('versions') or {}).get(key) != versions.get(key) for key in (
            'code_files','contract_sha256','public_contract_schema_version')):
            return None
        artifact = next(item for item in release['artifacts'] if item.get('object_key') == object_key)
        path = parent_root/object_key
        if path.stat().st_size != artifact['bytes'] or _sha256_file(path) != artifact['sha256']:
            return None
        payload = json.loads(path.read_text(encoding='utf-8'))
        if (payload.get('generation') != parent or payload.get('data_version') != release.get('data_version')
            or payload.get('contract_schema_version') != PUBLIC_CONTRACT_SCHEMA_VERSION):
            return None
        payload.update(generation=candidate.generation_id,data_version=candidate.data_version)
        return payload
    except (OSError,ValueError,KeyError,StopIteration,TypeError):
        return None


def _build_pack(
    output_root: Path,
    snapshot_entries: list[dict],
    data_version: str,
    release_version: str,
) -> dict:
    # Keep only one decoded snapshot in memory. The pack can be much larger
    # than any single view; retaining every payload and a second giant JSON
    # string unnecessarily competes with the live API during a refresh.
    members = []
    for item in snapshot_entries:
        if not _is_pack_member(item):
            continue
        path = Path(item["path"])
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("data_version") != data_version:
            raise RuntimeError(f"pack member has stale data version: {item['object_key']}")
        members.append((item["object_key"], path))
        item["pack_member"] = True
        del payload
    payload = {
        "status": "ok",
        "schema_version": DEFAULT_PACK_SCHEMA_VERSION,
        "data_version": data_version,
        "release_version": release_version,
    }
    path = output_root / "card-stats/bootstrap/default-pack.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.json.tmp')
    try:
        with temporary.open('w', encoding='utf-8') as target:
            target.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))[:-1])
            target.write(',"snapshots":{')
            for index, (key, member_path) in enumerate(members):
                if index:
                    target.write(',')
                target.write(json.dumps(key, ensure_ascii=False)+':')
                with member_path.open(encoding='utf-8') as source:
                    member = json.load(source)
                # Recheck after opening the member rather than relying on the
                # earlier pass; a failed build must never leave a partial pack.
                if member.get('data_version') != data_version:
                    raise RuntimeError(f'pack member has stale data version: {key}')
                json.dump(member, target, ensure_ascii=False, separators=(',', ':'))
                del member
            target.write('}}\n')
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return _artifact(
        output_root, path, "default_pack", data_version=data_version,
        snapshot_count=len(members), release_version=release_version,
    )


def build(
    root: Path, output_root: Path, generation_id: str, chunk: int = 1000,
    only_page: str | None = None, only_view: str | None = None,
) -> dict:
    resources = []
    try:
        return _build(root, output_root, generation_id, chunk, only_page, only_view, resources)
    finally:
        global _PROFILE
        _PROFILE = None
        for resource in reversed(resources):
            resource.close()


def _build(root, output_root, generation_id, chunk, only_page, only_view, resources):
    manager = GenerationManager(root / "phase2_private_data" / "generations", root / "phase3_private_serving" / "current.json")
    candidate = manager.inspect(generation_id)
    output_root.mkdir(parents=True, exist_ok=True)
    # Measurement only (see _ProfileSink). A fresh journal per attempt.
    global _PROFILE
    journal = output_root / "resource-profile.jsonl"
    try:
        journal.unlink(missing_ok=True)
    except OSError:
        pass  # A private diagnostic file cannot make the snapshot fail.
    _PROFILE = _ProfileSink(journal)
    adapter = create_private_adapter(
        manager,
        persistent_cache_path=(
            root / "phase2_private_data" / "staging"
            / f"{generation_id}.snapshot-response-cache.sqlite3"
        ),
        # Replaced below by a disk-only offline cache. Keep shared factory/live
        # defaults untouched; generation keys and persistence remain identical.
        memory_items=1,
        persistent_items=32,
        generation_id=generation_id,
        # A candidate must always be evaluated from its own database. A partial
        # snapshot directory left by a killed attempt must never validate itself.
        allow_default_snapshots=False,
        # Snapshot construction is trusted, serial offline work.  Keep the
        # 90-second deadline for interactive requests, but allow complex full-
        # population snapshots to spill and finish within the refresh window.
        query_timeout_seconds=600.0,
        memory_limit=os.environ.get('DUCKDB_SNAPSHOT_MEMORY_LIMIT', '2000MB'),
    )
    adapter.cache = OfflineDiskResponseCache(max_items=1, persistent=adapter.cache.persistent)
    adapter.offline_component_cis = OfflineComponentCIs(
        adapter.store, output_root / '.ordinary-component-cache.sqlite3')
    resources.append(adapter.offline_component_cis)
    # Card + Card is a production snapshot route implemented in the Phase 3
    # native service. The other Phase 3-only routes (component CI and player
    # history) are interactive endpoints and intentionally remain uncached.
    specs = sorted(PHASE4_NATIVE_ROUTES | {("cards", "default"), ("combinations", "card_card")})
    if only_page:
        specs = [spec for spec in specs if spec[0] == only_page]
    if only_view:
        specs = [spec for spec in specs if spec[1] == only_view]
    results = []
    reusable_paths = _reusable_snapshot_paths(output_root, candidate)
    if ("arena", "top_100") in specs:
        print(json.dumps({"event": "snapshot_start", "page": "arena", "view": "top_100"}), flush=True)
        arena_started = time.perf_counter()
        with _measure('arena_bundle'):
            arena_results = build_arena_bundle(adapter, output_root)
        arena_results[0]['build_seconds'] = round(time.perf_counter()-arena_started, 6)
        results.extend(arena_results)
        for item in arena_results:
            print(json.dumps({"event": "snapshot_done", **item}), flush=True)
    for page, view in specs:
        if (page, view) in {SPECIAL_BUNDLE, ("players", "arena_top_100")}:
            continue
        bases = ROUTE_PATHS.get((page, view))
        if bases is None:
            raise RuntimeError(f"no snapshot path for {page}/{view}")
        if isinstance(bases, str):
            bases = [bases]
        datasets = [1] if (page, view) == ("combinations", "card_action_card") else _datasets(page)
        for dataset in datasets:
            suffix = "mw" if dataset in (None, 1) else "base"
            for base in bases:
                path = output_root / f"{base}/default-{suffix}.json"
                if path.resolve() in reusable_paths:
                    try:
                        existing = json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        existing = None
                    if (
                        isinstance(existing, dict)
                        and existing.get("data_version") == candidate.data_version
                        and existing.get("contract_schema_version") == PUBLIC_CONTRACT_SCHEMA_VERSION
                    ):
                        reused = {"path": str(path), "page": page, "view": view, "dataset": dataset,
                                  "data_version": existing.get("data_version"), "row_count": existing.get("row_count"),
                                  "bytes": path.stat().st_size, "reused": True}
                        results.append(reused)
                        print(json.dumps({"event": "snapshot_reuse", **reused}), flush=True)
                        continue
                exact_prior = _qualified_log_snapshot(root,candidate,_object_key(output_root,path))
                if exact_prior is not None:
                    _write_json(path,exact_prior)
                    reused = {'path':str(path),'page':page,'view':view,'dataset':dataset,
                        'data_version':candidate.data_version,'row_count':exact_prior.get('row_count'),
                        'bytes':path.stat().st_size,'reused':True,'reuse_reason':'exact_logged_population'}
                    results.append(reused)
                    print(json.dumps({'event':'snapshot_reuse',**reused}),flush=True)
                    continue
                print(json.dumps({"event": "snapshot_start", "page": page, "view": view, "dataset": dataset, "path": str(path)}), flush=True)
                ci = adapter.offline_component_cis
                ci_before = (ci.population_queries, ci.population_seconds, ci.lookups)
                with _measure('snapshot', page=page, view=view, dataset=dataset) as record:
                    split = {}
                    results.append(build_one(adapter, page, view, dataset, path, chunk, profile=split))
                    record.update(split)
                    record.update({
                        "population_queries": ci.population_queries - ci_before[0],
                        "population_seconds": round(ci.population_seconds - ci_before[1], 6),
                        "component_lookups": ci.lookups - ci_before[2],
                    })
                print(json.dumps({"event": "snapshot_done", **results[-1]}), flush=True)
    for item in results:
        path = Path(item["path"])
        item.update(_artifact(
            output_root, path, "snapshot",
            page=item.get("page"), view=item.get("view"), dataset=item.get("dataset"),
            data_version=item.get("data_version"), row_count=item.get("row_count"),
        ))
        item.setdefault("pack_member", False)

    # Targeted builder invocations remain useful for diagnostics, but only a
    # full run is a publishable release and therefore receives the mandatory
    # ancillary artifacts and authoritative manifest.
    if only_page or only_view:
        return {
            "status": "partial",
            "generation": generation_id,
            "data_version": candidate.data_version,
            "snapshot_count": len(results),
            "snapshots": results,
        }

    with _measure('player_indexes'):
        indexes = _build_player_indexes(
            manager, generation_id, output_root, APP_ROOT / "merge_players.csv"
        )
    with _measure('home_bootstrap'):
        home_bootstrap = _build_home_bootstrap(output_root, candidate.data_version)
    versions = _release_versions(root, candidate)
    release_version = _canonical_hash({
        "generation": generation_id,
        "data_version": candidate.data_version,
        **versions,
    })
    with _measure('default_pack'):
        pack = _build_pack(output_root, results, candidate.data_version, release_version)
    artifacts = [*results, *indexes, home_bootstrap, pack]
    required_keys = sorted(item["object_key"] for item in artifacts)
    manifest = {
        "status": "ok",
        "schema_version": ARTIFACT_MANIFEST_SCHEMA_VERSION,
        "generation": generation_id,
        "data_version": candidate.data_version,
        "release_version": release_version,
        "generated_at": _utc_now(),
        "versions": versions,
        "snapshot_count": len(results),
        "pack_snapshot_count": pack["snapshot_count"],
        "artifact_count": len(artifacts),
        "required_object_keys": required_keys,
        "snapshots": results,
        "artifacts": artifacts,
        "ordinary_component_population_queries": adapter.offline_component_cis.population_queries,
        "ordinary_component_population_seconds": round(adapter.offline_component_cis.population_seconds, 6),
    }
    release_manifest_path = output_root / "release-manifest.json"
    release_manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest["release_manifest"] = str(release_manifest_path)
    _write_resource_profile(output_root, adapter)
    return manifest


def _write_resource_profile(output_root: Path, adapter) -> None:
    """Consolidate the measurement records. Best effort; never affects the build."""
    try:
        profile = {
            "schema": 1,
            "note": "Measurement only. Numbers and fixed labels; never SQL or row values.",
            "records": list(_PROFILE or []),
            "component_ci_populations": list(adapter.offline_component_cis.population_log),
            "component_ci_lookups": adapter.offline_component_cis.lookups,
            "component_ci_population_queries": adapter.offline_component_cis.population_queries,
        }
        (output_root / "resource-profile.json").write_text(
            json.dumps(profile, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("generation")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output", type=Path, default=Path("phase2_private_data/snapshots"))
    parser.add_argument("--chunk", type=int, default=1000)
    parser.add_argument("--only-page")
    parser.add_argument("--only-view")
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output / args.generation
    result = build(
        root, output, args.generation, args.chunk,
        only_page=args.only_page, only_view=args.only_view,
    )
    (output / "manifest.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
