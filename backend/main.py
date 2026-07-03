import functions_framework
import gzip
import hashlib
import hmac
import json
import logging
import os
import time
from datetime import date, datetime, timedelta, timezone

from google.cloud import bigquery
from google.cloud import storage


# Constants

DEFAULT_DATE_FROM = date(2025, 1, 1)
MAPS_METRICS_DEFAULT_DATE_FROM = date(2026, 1, 13)
DEFAULT_CARD_TYPES = ["animal", "sponsor", "project"]
VALID_CARD_TYPES = set(DEFAULT_CARD_TYPES)

EXCLUDED_PROJECTS = {
    "reptiles", "europe", "predators", "americas", "australia",
    "birds", "sea animals", "africa", "herbivores", "asia",
    "primates", "habitat diversity", "species diversity",
}

INVALID_MAPS = [
    "Map 0", "Map A",
    "Map 1: Observation Tower", "Map 2: Outdoor Areas",
    "Map 3: Silver Lake", "Map 4: Commercial Harbor",
    "Map 5: Park Restaurant", "Map 6: Research Institute",
    "Map 7: Ice Cream Parlors", "Map 8: Hollywood Hills",
]

VALID_MAPS = [
    "Map 1a: Observation Tower", "Map 2a: Outdoor Areas",
    "Map 3a: Silver Lake", "Map 4a: Commercial Harbor",
    "Map 5a: Park Restaurant", "Map 6a: Research Institute",
    "Map 7a: Ice Cream Parlors", "Map 8a: Hollywood Hills",
    "Map 9: Geographical Zoo", "Map 10: Rescue Station",
    "Map 11: Caves", "Map 12: Artificial Intelligence",
    "Map 13: Drawing Board", "Map 14: Lagoon",
    "Map T1: Tournament 1",
]

VALID_ROUNDS = {"1", "2", "3", "4", "5", "6+"}

CACHE_BUCKET = os.environ.get("CACHE_BUCKET")
CACHE_PREFIX = os.environ.get("CACHE_PREFIX", "card-stats")
FILTER_CACHE_VERSION = "v3"
STATS_PAGE_CARDS = "cards"
STATS_PAGE_HOME = "home"
STATS_PAGE_OPENING_HAND = "opening_hand"
STATS_PAGE_ENDGAMES = "endgames"
STATS_PAGE_MAPS = "maps"
STATS_PAGE_SPONSOR_ENDGAMES = "sponsor_endgames"
STATS_PAGE_COMBINATIONS = "combinations"
VALID_STATS_PAGES = {
    STATS_PAGE_CARDS,
    STATS_PAGE_HOME,
    STATS_PAGE_OPENING_HAND,
    STATS_PAGE_ENDGAMES,
    STATS_PAGE_MAPS,
    STATS_PAGE_SPONSOR_ENDGAMES,
    STATS_PAGE_COMBINATIONS,
}
ENDGAMES_VIEW_GENERAL = "general"
ENDGAMES_VIEW_CP_DISTRIBUTION = "cp_distribution"
ENDGAMES_VIEW_CP_BY_MAP = "cp_by_map"
MAPS_VIEW_METRICS = "metrics"
MAPS_VIEW_TOURNAMENT_H2H = "tournament_h2h"
SPONSOR_ENDGAMES_VIEW_CP = "cp"
SPONSOR_ENDGAMES_VIEW_APPEAL = "appeal"
VALID_ENDGAMES_VIEWS = {
    ENDGAMES_VIEW_GENERAL,
    ENDGAMES_VIEW_CP_DISTRIBUTION,
    ENDGAMES_VIEW_CP_BY_MAP,
}
VALID_MAPS_VIEWS = {MAPS_VIEW_METRICS, MAPS_VIEW_TOURNAMENT_H2H}
VALID_SPONSOR_ENDGAMES_VIEWS = {SPONSOR_ENDGAMES_VIEW_CP, SPONSOR_ENDGAMES_VIEW_APPEAL}
COMBINATIONS_VIEW_CARD_CARD = "card_card"
COMBINATIONS_VIEW_CARD_MAP = "card_map"
COMBINATIONS_VIEW_CARD_ROUND = "card_round"
VALID_COMBINATIONS_VIEWS = {
    COMBINATIONS_VIEW_CARD_CARD,
    COMBINATIONS_VIEW_CARD_MAP,
    COMBINATIONS_VIEW_CARD_ROUND,
}

ALL_MAPS_FOR_METRICS = [
    {"code": "1a", "key": "map_1a", "full": "Map 1a: Observation Tower", "visible_default": True},
    {"code": "2a", "key": "map_2a", "full": "Map 2a: Outdoor Areas", "visible_default": True},
    {"code": "3a", "key": "map_3a", "full": "Map 3a: Silver Lake", "visible_default": True},
    {"code": "4a", "key": "map_4a", "full": "Map 4a: Commercial Harbor", "visible_default": True},
    {"code": "5a", "key": "map_5a", "full": "Map 5a: Park Restaurant", "visible_default": True},
    {"code": "6a", "key": "map_6a", "full": "Map 6a: Research Institute", "visible_default": True},
    {"code": "7a", "key": "map_7a", "full": "Map 7a: Ice Cream Parlors", "visible_default": True},
    {"code": "8a", "key": "map_8a", "full": "Map 8a: Hollywood Hills", "visible_default": True},
    {"code": "9", "key": "map_9", "full": "Map 9: Geographical Zoo", "visible_default": True},
    {"code": "10", "key": "map_10", "full": "Map 10: Rescue Station", "visible_default": True},
    {"code": "11", "key": "map_11", "full": "Map 11: Caves", "visible_default": True},
    {"code": "12", "key": "map_12", "full": "Map 12: Artificial Intelligence", "visible_default": True},
    {"code": "13", "key": "map_13", "full": "Map 13: Drawing Board", "visible_default": True},
    {"code": "14", "key": "map_14", "full": "Map 14: Lagoon", "visible_default": True},
    {"code": "T1", "key": "map_t1", "full": "Map T1: Tournament 1", "visible_default": True},
    {"code": "1", "key": "map_1", "full": "Map 1: Observation Tower", "visible_default": False},
    {"code": "2", "key": "map_2", "full": "Map 2: Outdoor Areas", "visible_default": False},
    {"code": "3", "key": "map_3", "full": "Map 3: Silver Lake", "visible_default": False},
    {"code": "4", "key": "map_4", "full": "Map 4: Commercial Harbor", "visible_default": False},
    {"code": "5", "key": "map_5", "full": "Map 5: Park Restaurant", "visible_default": False},
    {"code": "6", "key": "map_6", "full": "Map 6: Research Institute", "visible_default": False},
    {"code": "7", "key": "map_7", "full": "Map 7: Ice Cream Parlors", "visible_default": False},
    {"code": "8", "key": "map_8", "full": "Map 8: Hollywood Hills", "visible_default": False},
    {"code": "A", "key": "map_a", "full": "Map A", "visible_default": False},
    {"code": "0", "key": "map_0", "full": "Map 0", "visible_default": False},
]
ALL_KNOWN_MAPS = [item["full"] for item in ALL_MAPS_FOR_METRICS]

SPONSOR_CP_CARDS = [
    "Science Lab", "Federal Grants", "Talented Communicator", "Native Farm Animals",
    "Geologist", "Hydrologist", "Guided School Tours", "Science Library",
    "Excavation Site", "Veterinarian", "Technology Institute", "Franchise Business",
    "Expert On The Americas", "Quarantine Lab", "Foreign Institute", "Aquarium",
    "Conference On Europe", "Cable Car", "Breeding Cooperation", "Breeding Program",
    "Archaeologist", "Polar Bear Exhibit", "Expansion Area", "Baboon Rock",
    "Free-range New World Monkeys", "Penguin Pool", "Farm Cat", "Meerkat Den",
    "Native Lizards", "Native Seabirds", "Expert On Europe",
]
SPONSOR_CP_0_1_2_3PLUS = {
    "Farm Cat", "Free-range New World Monkeys", "Native Farm Animals",
    "Native Lizards", "Native Seabirds",
}
SPONSOR_CP_0_1_2 = {"Polar Bear Exhibit", "Science Lab"}
SPONSOR_APPEAL_VALUES = {
    "Arcade": [0, 2],
    "Conference On Australia": [0, 1, 2, 3, 4, 5],
    "Diversity Researcher": [0, 2, 4, 6],
    "Engineer": [0, 5],
    "Expert On Africa": [0, 1, 2, 3, 4, 5],
    "Reconstruction": [0, 5],
    "Side Entrance": [0, 5],
    "Underwater Tunnel": [0, 3, 5],
    "Victory Column": [0, 2],
}
SPONSOR_APPEAL_CARDS = list(SPONSOR_APPEAL_VALUES.keys())
BIGQUERY_JOB_PROJECT = os.environ.get("BIGQUERY_JOB_PROJECT", "ark-nova-stats-dashboard")
BIGQUERY_LOCATION = os.environ.get("BIGQUERY_LOCATION", "US")
MAINTENANCE_TOKEN = os.environ.get("MAINTENANCE_TOKEN")
PREPARED_LOGS_TABLE = os.environ.get(
    "PREPARED_LOGS_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.card_logs_prepared",
)
PREPARED_FULL_STATS_TABLE = os.environ.get(
    "PREPARED_FULL_STATS_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.full_stats_prepared",
)
PREPARED_CARD_PLAYS_TABLE = os.environ.get(
    "PREPARED_CARD_PLAYS_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.card_plays_prepared",
)
PREPARED_CARD_PAIRS_TABLE = os.environ.get(
    "PREPARED_CARD_PAIRS_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.card_pairs_prepared",
)
TOURNAMENT_TABLES_CACHE_TABLE = os.environ.get(
    "TOURNAMENT_TABLES_CACHE_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.tournament_tables",
)


# Generic helpers

def _dt_iso(value):
    return value.isoformat() if value else None


def _ms_since(start):
    return round((time.perf_counter() - start) * 1000, 1)


def _json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _sql_string(value):
    return "'" + str(value).replace("'", "''") + "'"


def _parse_int_param(raw_value, field_name, default=None, allow_none=True):
    if raw_value in (None, ""):
        if raw_value is None and not allow_none:
            raise ValueError(f"{field_name} is required")
        return default
    try:
        return int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc


def _parse_is_mw(raw_value):
    value = _parse_int_param(raw_value, "is_mw", 1, allow_none=False)
    if value not in (0, 1):
        raise ValueError("is_mw must be 0 or 1")
    return value


def _parse_iso_date(raw_value, field_name, default=None):
    if raw_value in (None, ""):
        return default
    if not isinstance(raw_value, str):
        raise ValueError(f"{field_name} must be a YYYY-MM-DD string")
    try:
        return date.fromisoformat(raw_value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid YYYY-MM-DD date") from exc


def _parse_optional_bool(raw_value, field_name):
    if raw_value is None:
        return None
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, str):
        value = raw_value.strip().lower()
        if value in ("true", "1", "yes"):
            return True
        if value in ("false", "0", "no"):
            return False
        if value in ("", "all", "none", "null"):
            return None
    raise ValueError(f"{field_name} must be true, false, or null")


def _parse_card_types(raw_value):
    if not isinstance(raw_value, list):
        return list(DEFAULT_CARD_TYPES)
    return [card_type for card_type in raw_value if card_type in VALID_CARD_TYPES]


def _parse_stats_page(raw_value):
    if raw_value in (None, ""):
        return STATS_PAGE_CARDS
    value = str(raw_value).strip().lower().replace("-", "_")
    if value not in VALID_STATS_PAGES:
        raise ValueError(
            "stats_page must be cards, home, opening_hand, endgames, maps, "
            "sponsor_endgames, or combinations"
        )
    return value


def _parse_endgames_view(raw_value):
    if raw_value in (None, ""):
        return ENDGAMES_VIEW_GENERAL
    value = str(raw_value).strip().lower().replace("-", "_")
    if value not in VALID_ENDGAMES_VIEWS:
        raise ValueError("endgames_view must be general, cp_distribution, or cp_by_map")
    return value


def _parse_maps_view(raw_value):
    if raw_value in (None, ""):
        return MAPS_VIEW_METRICS
    value = str(raw_value).strip().lower().replace("-", "_")
    if value not in VALID_MAPS_VIEWS:
        raise ValueError("maps_view must be metrics or tournament_h2h")
    return value


def _parse_sponsor_endgames_view(raw_value):
    if raw_value in (None, ""):
        return SPONSOR_ENDGAMES_VIEW_CP
    value = str(raw_value).strip().lower().replace("-", "_")
    if value not in VALID_SPONSOR_ENDGAMES_VIEWS:
        raise ValueError("sponsor_endgames_view must be cp or appeal")
    return value


def _parse_combinations_view(raw_value):
    if raw_value in (None, ""):
        return COMBINATIONS_VIEW_CARD_CARD
    value = str(raw_value).strip().lower().replace("-", "_")
    if value not in VALID_COMBINATIONS_VIEWS:
        raise ValueError("combinations_view must be card_card, card_map, or card_round")
    return value


def _parse_round_filter(raw_rounds):
    if not isinstance(raw_rounds, list):
        return [], False

    selected = []
    for value in raw_rounds:
        token = str(value).strip()
        if token in VALID_ROUNDS and token not in selected:
            selected.append(token)

    if not selected or set(selected) == VALID_ROUNDS:
        return [], False

    return selected, True


def _round_condition(alias, selected_rounds):
    exact_rounds = sorted(int(r) for r in selected_rounds if r != "6+")
    conditions = []

    if exact_rounds:
        conditions.append(f"{alias}.round IN ({', '.join(str(r) for r in exact_rounds)})")
    if "6+" in selected_rounds:
        conditions.append(f"{alias}.round >= 6")

    return "(" + " OR ".join(conditions) + ")"


def _has_maintenance_auth(request):
    if not MAINTENANCE_TOKEN:
        return False
    provided = request.headers.get("X-Ark-Nova-Maintenance-Token", "")
    return hmac.compare_digest(provided, MAINTENANCE_TOKEN)


def _maintenance_auth_error(headers):
    if not MAINTENANCE_TOKEN:
        return (
            json.dumps({
                "status": "error",
                "message": "MAINTENANCE_TOKEN is not configured",
            }),
            500,
            headers,
        )
    return (
        json.dumps({
            "status": "error",
            "message": "Maintenance authorization required",
        }),
        403,
        headers,
    )


# Cache helpers

def _cache_blob_name(
    is_mw,
    stats_page=STATS_PAGE_CARDS,
    endgames_view=ENDGAMES_VIEW_GENERAL,
    maps_view=MAPS_VIEW_METRICS,
    sponsor_endgames_view=SPONSOR_ENDGAMES_VIEW_CP,
    combinations_view=COMBINATIONS_VIEW_CARD_CARD,
):
    dataset = "mw" if int(is_mw) == 1 else "base"
    if stats_page == STATS_PAGE_HOME:
        return f"{CACHE_PREFIX}/home/default-{dataset}.json"
    if stats_page == STATS_PAGE_OPENING_HAND:
        return f"{CACHE_PREFIX}/opening-hand/default-{dataset}.json"
    if stats_page == STATS_PAGE_MAPS:
        return f"{CACHE_PREFIX}/maps/{maps_view}/default-{dataset}.json"
    if stats_page == STATS_PAGE_SPONSOR_ENDGAMES:
        return f"{CACHE_PREFIX}/sponsor-endgames/{sponsor_endgames_view}/default-{dataset}.json"
    if stats_page == STATS_PAGE_COMBINATIONS:
        view_slug = combinations_view.replace("_", "-")
        return f"{CACHE_PREFIX}/combinations/{view_slug}/default-{dataset}.json"
    if stats_page == STATS_PAGE_ENDGAMES:
        if endgames_view == ENDGAMES_VIEW_CP_DISTRIBUTION:
            return f"{CACHE_PREFIX}/endgames/cp-distribution/default-{dataset}.json"
        if endgames_view == ENDGAMES_VIEW_CP_BY_MAP:
            return f"{CACHE_PREFIX}/endgames/cp-by-map/default-{dataset}.json"
        return f"{CACHE_PREFIX}/endgames/default-{dataset}.json"
    return f"{CACHE_PREFIX}/default-{dataset}.json"


def _data_version_blob_name():
    return f"{CACHE_PREFIX}/data-version.json"


def _filter_cache_day():
    # Fallback only: normal filter cache keys use the explicit data-version marker.
    return (datetime.now(timezone.utc) - timedelta(hours=1)).date().isoformat()


def _read_cache_blob(blob_name, cache_status):
    if not CACHE_BUCKET:
        return None
    try:
        bucket = storage.Client().bucket(CACHE_BUCKET)
        blob = bucket.blob(blob_name)
        if not blob.exists():
            return None
        raw = blob.download_as_bytes(raw_download=True)
        if raw.startswith(b"\x1f\x8b"):
            raw = gzip.decompress(raw)
        payload = json.loads(raw.decode("utf-8"))
        payload["cache_status"] = cache_status
        return payload
    except Exception:
        logging.exception("Failed to read cache blob %s", blob_name)
        return None


def _write_cache_blob(blob_name, payload, cache_status):
    if not CACHE_BUCKET:
        logging.warning("CACHE_BUCKET is not set; skipping cache write for %s", blob_name)
        return False
    try:
        snapshot = dict(payload)
        snapshot["cache_status"] = cache_status
        snapshot["cache_updated_at"] = datetime.now(timezone.utc).isoformat()
        bucket = storage.Client().bucket(CACHE_BUCKET)
        blob = bucket.blob(blob_name)
        blob.cache_control = "public, max-age=3600"
        blob.content_encoding = "gzip"
        encoded = json.dumps(
            snapshot,
            default=_json_default,
            separators=(",", ":"),
        ).encode("utf-8")
        blob.upload_from_string(
            gzip.compress(encoded, compresslevel=6, mtime=0),
            content_type="application/json",
        )
        return True
    except Exception:
        logging.exception("Failed to write cache blob %s", blob_name)
        return False


def _read_data_version():
    if not CACHE_BUCKET:
        return _filter_cache_day()
    try:
        bucket = storage.Client().bucket(CACHE_BUCKET)
        blob = bucket.blob(_data_version_blob_name())
        if not blob.exists():
            return _filter_cache_day()
        payload = json.loads(blob.download_as_text(encoding="utf-8"))
        return str(payload.get("version") or _filter_cache_day())
    except Exception:
        logging.exception("Failed to read data-version marker")
        return _filter_cache_day()


def _write_data_version(prepared_payload):
    if not CACHE_BUCKET:
        return None

    version = datetime.now(timezone.utc).isoformat()
    payload = {
        "version": version,
        "updated_at": version,
        "prepared_table": PREPARED_LOGS_TABLE,
        "prepared_job_id": prepared_payload.get("job_id"),
    }
    try:
        bucket = storage.Client().bucket(CACHE_BUCKET)
        blob = bucket.blob(_data_version_blob_name())
        blob.upload_from_string(
            json.dumps(payload, default=_json_default),
            content_type="application/json",
        )
        return version
    except Exception:
        logging.exception("Failed to write data-version marker")
        return None


def _read_cached_snapshot(
    is_mw,
    stats_page=STATS_PAGE_CARDS,
    endgames_view=ENDGAMES_VIEW_GENERAL,
    maps_view=MAPS_VIEW_METRICS,
    sponsor_endgames_view=SPONSOR_ENDGAMES_VIEW_CP,
    combinations_view=COMBINATIONS_VIEW_CARD_CARD,
):
    return _read_cache_blob(
        _cache_blob_name(
            is_mw, stats_page, endgames_view, maps_view,
            sponsor_endgames_view, combinations_view
        ),
        "hit",
    )


def _write_cached_snapshot(
    is_mw,
    payload,
    stats_page=STATS_PAGE_CARDS,
    endgames_view=ENDGAMES_VIEW_GENERAL,
    maps_view=MAPS_VIEW_METRICS,
    sponsor_endgames_view=SPONSOR_ENDGAMES_VIEW_CP,
    combinations_view=COMBINATIONS_VIEW_CARD_CARD,
):
    return _write_cache_blob(
        _cache_blob_name(
            is_mw, stats_page, endgames_view, maps_view,
            sponsor_endgames_view, combinations_view
        ),
        payload,
        "refreshed",
    )


def _write_home_bootstrap_asset():
    """Publish both Home defaults as parser-loaded JavaScript for instant first paint."""
    if not CACHE_BUCKET:
        return False
    mw = _read_cached_snapshot(1, STATS_PAGE_HOME)
    base = _read_cached_snapshot(0, STATS_PAGE_HOME)
    if not mw or not base:
        logging.error("Cannot publish Home bootstrap asset without both snapshots")
        return False
    payload = {"1": mw, "0": base}
    source = "window.__ARK_NOVA_HOME_DEFAULTS__=" + json.dumps(
        payload, default=_json_default, separators=(",", ":")
    ) + ";"
    try:
        bucket = storage.Client().bucket(CACHE_BUCKET)
        blob = bucket.blob(f"{CACHE_PREFIX}/home/defaults.js")
        blob.cache_control = "public, max-age=300"
        blob.upload_from_string(source, content_type="application/javascript; charset=utf-8")
        return True
    except Exception:
        logging.exception("Failed to publish Home bootstrap asset")
        return False


def _filter_cache_blob_name(
    stats_page,
    is_mw,
    selected_maps,
    card_types,
    selected_rounds,
    round_filter_active,
    player_elo_min,
    player_elo_max,
    opponent_elo_min,
    opponent_elo_max,
    date_from,
    date_to,
    end_game_triggered,
    data_version,
    subview=None,
):
    cache_key = {
        "version": FILTER_CACHE_VERSION,
        "stats_page": stats_page,
        "subview": subview,
        "data_version": data_version,
        "is_mw": int(is_mw),
        "maps": sorted(selected_maps),
        "card_types": sorted(card_types),
        "rounds": sorted(selected_rounds) if round_filter_active else [],
        "player_elo_min": player_elo_min,
        "player_elo_max": player_elo_max,
        "opponent_elo_min": opponent_elo_min,
        "opponent_elo_max": opponent_elo_max,
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "end_game_triggered": end_game_triggered,
    }
    key_json = json.dumps(cache_key, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(key_json.encode("utf-8")).hexdigest()[:32]
    return f"{CACHE_PREFIX}/filters/{digest}.json"


def _is_default_cache_request(
    stats_page,
    maps_view,
    is_mw,
    selected_maps,
    player_elo_min,
    player_elo_max,
    opponent_elo_min,
    opponent_elo_max,
    date_from,
    date_to,
    end_game_triggered,
    round_filter_active,
):
    if stats_page == STATS_PAGE_MAPS and maps_view == MAPS_VIEW_TOURNAMENT_H2H:
        return int(is_mw) in (0, 1)
    if stats_page == STATS_PAGE_HOME:
        return (
            int(is_mw) in (0, 1)
            and set(selected_maps) == set(ALL_KNOWN_MAPS)
            and player_elo_min is None
            and player_elo_max is None
            and opponent_elo_min is None
            and opponent_elo_max is None
            and date_from is None
            and date_to is None
            and end_game_triggered is None
            and not round_filter_active
        )
    default_date_from = (
        MAPS_METRICS_DEFAULT_DATE_FROM
        if stats_page == STATS_PAGE_MAPS and maps_view == MAPS_VIEW_METRICS
        else DEFAULT_DATE_FROM
    )
    default_date_to_ok = date_to is None
    if stats_page == STATS_PAGE_MAPS and maps_view == MAPS_VIEW_METRICS:
        default_date_to_ok = date_to is None or date_to == date.today()
    return (
        int(is_mw) in (0, 1)
        and set(selected_maps) == set(VALID_MAPS)
        and player_elo_min == 300
        and player_elo_max is None
        and opponent_elo_min == 300
        and opponent_elo_max is None
        and date_from == default_date_from
        and default_date_to_ok
        and end_game_triggered is None
        and not round_filter_active
    )


# BigQuery helpers

def _refresh_prepared_logs_table():
    query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_LOGS_TABLE}`
    PARTITION BY game_date
    CLUSTER BY is_mw, Map, end_game_triggered
    AS
    WITH valid_log_ids AS (
      SELECT table_id
      FROM `freestyle-190711.ark_nova.game_log_stat_v2`
      GROUP BY table_id
      HAVING COUNT(*) = 2
    )
    SELECT
      f.table_id,
      f.player,
      CAST(f.is_mw AS INT64) AS is_mw,
      f.Map,
      CAST(f.game_ended_at AS DATE) AS game_date,
      f.end_game_triggered,
      f.concede,
      f.elo,
      f.opponent_elo,
      f.elo_delta,
      l.played_animals,
      l.played_sponsors,
      l.played_projects,
      l.cards_drawn,
      l.display_cards,
      l.opening_cards,
      l.opening_keep,
      l.endgame,
      l.endgame_scores,
      l.`2cp_worker` AS two_cp_worker,
      l.petting_zoo_built,
      l.chosen_5cp_bonus,
      l.chosen_8cp_bonus,
      l.endgame_from_sponsors
    FROM `freestyle-190711.ark_nova.all_games_stat` f
    JOIN valid_log_ids v ON f.table_id = v.table_id
    JOIN `freestyle-190711.ark_nova.game_log_stat_v2` l
      ON f.table_id = l.table_id AND f.player = l.player
    """

    started_at = time.perf_counter()
    client = bigquery.Client(project=BIGQUERY_JOB_PROJECT)
    job_config = bigquery.QueryJobConfig()
    job = client.query(query, job_config=job_config, location=BIGQUERY_LOCATION)
    job.result()
    return {
        "status": "ok",
        "prepared_table": PREPARED_LOGS_TABLE,
        "total_ms": _ms_since(started_at),
        "job_id": job.job_id,
        "job_created": _dt_iso(job.created),
        "job_started": _dt_iso(job.started),
        "job_ended": _dt_iso(job.ended),
        "job_total_bytes_processed": job.total_bytes_processed,
        "job_total_slot_ms": job.slot_millis,
    }


def _refresh_prepared_full_stats_table():
    query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_FULL_STATS_TABLE}`
    PARTITION BY game_date
    CLUSTER BY is_mw, Map
    AS
    SELECT
      f.*,
      CAST(f.game_ended_at AS DATE) AS game_date,
      MAX(IF(COALESCE(f.concede, 0) != 0, 1, 0))
        OVER (PARTITION BY f.table_id) AS table_conceded
    FROM `freestyle-190711.ark_nova.all_games_stat` f
    """

    started_at = time.perf_counter()
    client = bigquery.Client(project=BIGQUERY_JOB_PROJECT)
    job = client.query(query, location=BIGQUERY_LOCATION)
    job.result()
    return {
        "status": "ok",
        "prepared_table": PREPARED_FULL_STATS_TABLE,
        "total_ms": _ms_since(started_at),
        "job_id": job.job_id,
        "job_created": _dt_iso(job.created),
        "job_started": _dt_iso(job.started),
        "job_ended": _dt_iso(job.ended),
        "job_total_bytes_processed": job.total_bytes_processed,
        "job_total_slot_ms": job.slot_millis,
    }


def _refresh_prepared_card_plays_table():
    excluded_projects_sql = ", ".join(_sql_string(value) for value in sorted(EXCLUDED_PROJECTS))
    query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_CARD_PLAYS_TABLE}`
    PARTITION BY game_date
    CLUSTER BY is_mw, Map, card_type, card_name
    AS
    WITH raw_plays AS (
      SELECT
        table_id, player, is_mw, Map, game_date, end_game_triggered,
        elo, opponent_elo, elo_delta,
        pa.animal AS card_name,
        'animal' AS card_type,
        SAFE_CAST(pa.round AS INT64) AS played_round
      FROM `{PREPARED_LOGS_TABLE}`
      CROSS JOIN UNNEST(IFNULL(played_animals, [])) AS pa
      WHERE pa.animal IS NOT NULL

      UNION ALL

      SELECT
        table_id, player, is_mw, Map, game_date, end_game_triggered,
        elo, opponent_elo, elo_delta,
        ps.sponsor AS card_name,
        'sponsor' AS card_type,
        SAFE_CAST(ps.round AS INT64) AS played_round
      FROM `{PREPARED_LOGS_TABLE}`
      CROSS JOIN UNNEST(IFNULL(played_sponsors, [])) AS ps
      WHERE ps.sponsor IS NOT NULL

      UNION ALL

      SELECT
        table_id, player, is_mw, Map, game_date, end_game_triggered,
        elo, opponent_elo, elo_delta,
        pp.project AS card_name,
        'project' AS card_type,
        SAFE_CAST(pp.round AS INT64) AS played_round
      FROM `{PREPARED_LOGS_TABLE}`
      CROSS JOIN UNNEST(IFNULL(played_projects, [])) AS pp
      WHERE pp.project IS NOT NULL
        AND LOWER(pp.project) NOT IN ({excluded_projects_sql})
    )
    SELECT DISTINCT *
    FROM raw_plays
    """

    started_at = time.perf_counter()
    client = bigquery.Client(project=BIGQUERY_JOB_PROJECT)
    job = client.query(query, location=BIGQUERY_LOCATION)
    job.result()
    return {
        "status": "ok",
        "prepared_table": PREPARED_CARD_PLAYS_TABLE,
        "total_ms": _ms_since(started_at),
        "job_id": job.job_id,
        "job_created": _dt_iso(job.created),
        "job_started": _dt_iso(job.started),
        "job_ended": _dt_iso(job.ended),
        "job_total_bytes_processed": job.total_bytes_processed,
        "job_total_slot_ms": job.slot_millis,
    }


def _refresh_prepared_card_pairs_table():
    query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_CARD_PAIRS_TABLE}`
    PARTITION BY game_date
    CLUSTER BY is_mw, Map, card_1, card_2
    AS
    WITH per_card AS (
      SELECT
        table_id, player, is_mw, Map, game_date, end_game_triggered,
        elo, opponent_elo, elo_delta, card_name, ANY_VALUE(card_type) AS card_type,
        ARRAY_AGG(DISTINCT played_round IGNORE NULLS) AS played_rounds
      FROM `{PREPARED_CARD_PLAYS_TABLE}`
      GROUP BY
        table_id, player, is_mw, Map, game_date, end_game_triggered,
        elo, opponent_elo, elo_delta, card_name
    )
    SELECT
      a.table_id,
      a.player,
      a.is_mw,
      a.Map,
      a.game_date,
      a.end_game_triggered,
      a.elo,
      a.opponent_elo,
      a.elo_delta,
      a.card_name AS card_1,
      a.card_type AS type_1,
      a.played_rounds AS played_rounds_1,
      b.card_name AS card_2,
      b.card_type AS type_2,
      b.played_rounds AS played_rounds_2
    FROM per_card a
    JOIN per_card b
      ON a.table_id = b.table_id
     AND a.player = b.player
     AND (
       LOWER(a.card_name) < LOWER(b.card_name)
       OR (LOWER(a.card_name) = LOWER(b.card_name) AND a.card_name < b.card_name)
     )
    """

    started_at = time.perf_counter()
    client = bigquery.Client(project=BIGQUERY_JOB_PROJECT)
    job = client.query(query, location=BIGQUERY_LOCATION)
    job.result()
    return {
        "status": "ok",
        "prepared_table": PREPARED_CARD_PAIRS_TABLE,
        "total_ms": _ms_since(started_at),
        "job_id": job.job_id,
        "job_created": _dt_iso(job.created),
        "job_started": _dt_iso(job.started),
        "job_ended": _dt_iso(job.ended),
        "job_total_bytes_processed": job.total_bytes_processed,
        "job_total_slot_ms": job.slot_millis,
    }


def _refresh_prepared_tables():
    logs = _refresh_prepared_logs_table()
    full_stats = _refresh_prepared_full_stats_table()
    card_plays = _refresh_prepared_card_plays_table()
    card_pairs = _refresh_prepared_card_pairs_table()
    return {
        "status": "ok",
        "prepared_table": PREPARED_LOGS_TABLE,
        "job_id": full_stats["job_id"],
        "logs": logs,
        "full_stats": full_stats,
        "card_plays": card_plays,
        "card_pairs": card_pairs,
    }


def _build_where_sql(
    is_mw,
    selected_maps,
    player_elo_min,
    player_elo_max,
    opponent_elo_min,
    opponent_elo_max,
    date_from,
    date_to,
    end_game_triggered,
):
    where_clauses = [
        "is_mw = @is_mw",
        "Map NOT IN UNNEST(@invalid_maps)",
        "Map IN UNNEST(@selected_maps)",
    ]
    query_parameters = [
        bigquery.ScalarQueryParameter("is_mw", "INT64", is_mw),
        bigquery.ArrayQueryParameter("invalid_maps", "STRING", INVALID_MAPS),
        bigquery.ArrayQueryParameter("selected_maps", "STRING", selected_maps),
    ]

    if player_elo_min is not None:
        where_clauses.append("elo >= @player_elo_min")
        query_parameters.append(bigquery.ScalarQueryParameter("player_elo_min", "INT64", player_elo_min))
    if player_elo_max is not None:
        where_clauses.append("elo <= @player_elo_max")
        query_parameters.append(bigquery.ScalarQueryParameter("player_elo_max", "INT64", player_elo_max))
    if opponent_elo_min is not None:
        where_clauses.append("opponent_elo >= @opponent_elo_min")
        query_parameters.append(bigquery.ScalarQueryParameter("opponent_elo_min", "INT64", opponent_elo_min))
    if opponent_elo_max is not None:
        where_clauses.append("opponent_elo <= @opponent_elo_max")
        query_parameters.append(bigquery.ScalarQueryParameter("opponent_elo_max", "INT64", opponent_elo_max))
    if date_from:
        where_clauses.append("game_date >= @date_from")
        query_parameters.append(bigquery.ScalarQueryParameter("date_from", "DATE", date_from))
    if date_to:
        where_clauses.append("game_date <= @date_to")
        query_parameters.append(bigquery.ScalarQueryParameter("date_to", "DATE", date_to))
    if end_game_triggered is not None:
        where_clauses.append("end_game_triggered = @end_game_triggered")
        query_parameters.append(bigquery.ScalarQueryParameter("end_game_triggered", "BOOL", end_game_triggered))

    return " AND ".join(where_clauses), query_parameters


def _build_card_stats_query(where_sql, round_filter_active, selected_rounds):
    if round_filter_active:
        animal_round_sql = f" AND {_round_condition('pa', selected_rounds)}"
        sponsor_round_sql = f" AND {_round_condition('ps', selected_rounds)}"
        project_round_sql = f" AND {_round_condition('pp', selected_rounds)}"
        return f"""
        WITH log_filtered AS (
          SELECT table_id, player, played_animals, played_sponsors, played_projects, elo_delta, elo
          FROM `{PREPARED_LOGS_TABLE}`
          WHERE {where_sql}
        ),
        played_animals AS (
          SELECT l.table_id, l.player, pa.animal AS card_name, 'animal' AS card_type, l.elo_delta, l.elo
          FROM log_filtered l
          CROSS JOIN UNNEST(l.played_animals) AS pa
          WHERE pa.animal IS NOT NULL
            {animal_round_sql}
        ),
        played_sponsors AS (
          SELECT l.table_id, l.player, ps.sponsor AS card_name, 'sponsor' AS card_type, l.elo_delta, l.elo
          FROM log_filtered l
          CROSS JOIN UNNEST(l.played_sponsors) AS ps
          WHERE ps.sponsor IS NOT NULL
            {sponsor_round_sql}
        ),
        played_projects AS (
          SELECT l.table_id, l.player, pp.project AS card_name, 'project' AS card_type, l.elo_delta, l.elo
          FROM log_filtered l
          CROSS JOIN UNNEST(l.played_projects) AS pp
          WHERE pp.project IS NOT NULL
            AND LOWER(pp.project) NOT IN UNNEST(@excluded_projects)
            {project_round_sql}
        ),
        all_played AS (
          SELECT table_id, player, card_name, card_type, elo_delta, elo FROM played_animals
          UNION ALL
          SELECT table_id, player, card_name, card_type, elo_delta, elo FROM played_sponsors
          UNION ALL
          SELECT table_id, player, card_name, card_type, elo_delta, elo FROM played_projects
        ),
        played_agg AS (
          SELECT
            card_name,
            card_type,
            COUNT(DISTINCT table_id) AS n_played,
            ROUND(AVG(elo_delta), 3) AS delta_played,
            ROUND(AVG(elo), 0) AS avg_elo
          FROM all_played
          GROUP BY card_name, card_type
        )
        SELECT
          card_type,
          card_name,
          delta_played,
          CAST(NULL AS FLOAT64) AS delta_in_hand,
          avg_elo,
          n_played,
          CAST(NULL AS INT64) AS n_seen,
          CAST(NULL AS FLOAT64) AS playrate_pct
        FROM played_agg
        ORDER BY card_type, n_played DESC, delta_played DESC NULLS LAST
        """

    return f"""
    WITH log_filtered AS (
      SELECT
        table_id,
        player,
        played_animals,
        played_sponsors,
        played_projects,
        cards_drawn,
        display_cards,
        elo_delta,
        elo
      FROM `{PREPARED_LOGS_TABLE}`
      WHERE {where_sql}
    ),
    played_animals AS (
      SELECT l.table_id, l.player, pa.animal AS card_name, 'animal' AS card_type, l.elo_delta, l.elo
      FROM log_filtered l
      CROSS JOIN UNNEST(l.played_animals) AS pa
      WHERE pa.animal IS NOT NULL
    ),
    played_sponsors AS (
      SELECT l.table_id, l.player, ps.sponsor AS card_name, 'sponsor' AS card_type, l.elo_delta, l.elo
      FROM log_filtered l
      CROSS JOIN UNNEST(l.played_sponsors) AS ps
      WHERE ps.sponsor IS NOT NULL
    ),
    played_projects AS (
      SELECT l.table_id, l.player, pp.project AS card_name, 'project' AS card_type, l.elo_delta, l.elo
      FROM log_filtered l
      CROSS JOIN UNNEST(l.played_projects) AS pp
      WHERE pp.project IS NOT NULL
        AND LOWER(pp.project) NOT IN UNNEST(@excluded_projects)
    ),
    all_played AS (
      SELECT table_id, player, card_name, card_type, elo_delta, elo FROM played_animals
      UNION ALL
      SELECT table_id, player, card_name, card_type, elo_delta, elo FROM played_sponsors
      UNION ALL
      SELECT table_id, player, card_name, card_type, elo_delta, elo FROM played_projects
    ),
    in_hand AS (
      SELECT DISTINCT
        l.table_id,
        l.player,
        TRIM(cd) AS card_name,
        l.elo_delta
      FROM log_filtered l
      CROSS JOIN UNNEST(IFNULL(l.cards_drawn, [])) AS cd
      WHERE TRIM(cd) != ''
        AND LOWER(TRIM(cd)) NOT IN UNNEST(@excluded_projects)
    ),
    all_seen AS (
      SELECT DISTINCT
        l.table_id,
        TRIM(c) AS card_name
      FROM log_filtered l
      CROSS JOIN UNNEST(ARRAY_CONCAT(IFNULL(l.cards_drawn, []), IFNULL(l.display_cards, []))) AS c
      WHERE TRIM(c) != ''
        AND LOWER(TRIM(c)) NOT IN UNNEST(@excluded_projects)
    ),
    played_agg AS (
      SELECT
        card_name,
        card_type,
        COUNT(DISTINCT table_id) AS n_played,
        ROUND(AVG(elo_delta), 3) AS delta_played,
        ROUND(AVG(elo), 0) AS avg_elo
      FROM all_played
      GROUP BY card_name, card_type
    ),
    in_hand_agg AS (
      SELECT
        card_name,
        ROUND(AVG(elo_delta), 3) AS delta_in_hand
      FROM in_hand
      GROUP BY card_name
    ),
    seen_agg AS (
      SELECT
        card_name,
        COUNT(*) AS n_seen
      FROM all_seen
      GROUP BY card_name
    )
    SELECT
      p.card_type,
      p.card_name,
      p.delta_played,
      h.delta_in_hand,
      p.avg_elo,
      p.n_played,
      s.n_seen,
      CASE
        WHEN s.n_seen IS NULL OR s.n_seen = 0 THEN NULL
        ELSE ROUND(100.0 * p.n_played / s.n_seen, 2)
      END AS playrate_pct
    FROM played_agg p
    LEFT JOIN in_hand_agg h USING(card_name)
    LEFT JOIN seen_agg s USING(card_name)
    ORDER BY p.card_type, playrate_pct DESC NULLS LAST
    """


def _build_opening_hand_stats_query(where_sql):
    return f"""
    WITH log_filtered AS (
      SELECT
        table_id,
        player,
        opening_cards,
        opening_keep,
        elo_delta,
        elo
      FROM `{PREPARED_LOGS_TABLE}`
      WHERE {where_sql}
    ),
    card_universe AS (
      SELECT DISTINCT TRIM(pa.animal) AS card_name, 'animal' AS card_type
      FROM `{PREPARED_LOGS_TABLE}` l
      CROSS JOIN UNNEST(l.played_animals) AS pa
      WHERE pa.animal IS NOT NULL AND TRIM(pa.animal) != ''

      UNION DISTINCT

      SELECT DISTINCT TRIM(ps.sponsor) AS card_name, 'sponsor' AS card_type
      FROM `{PREPARED_LOGS_TABLE}` l
      CROSS JOIN UNNEST(l.played_sponsors) AS ps
      WHERE ps.sponsor IS NOT NULL AND TRIM(ps.sponsor) != ''

      UNION DISTINCT

      SELECT DISTINCT TRIM(pp.project) AS card_name, 'project' AS card_type
      FROM `{PREPARED_LOGS_TABLE}` l
      CROSS JOIN UNNEST(l.played_projects) AS pp
      WHERE pp.project IS NOT NULL
        AND TRIM(pp.project) != ''
        AND LOWER(TRIM(pp.project)) NOT IN UNNEST(@excluded_projects)
    ),
    dealt AS (
      SELECT
        TRIM(card) AS card_name,
        COUNT(*) AS n_dealt,
        ROUND(AVG(elo_delta), 3) AS delta_dealt
      FROM log_filtered
      CROSS JOIN UNNEST(IFNULL(opening_cards, [])) AS card
      WHERE TRIM(card) != ''
        AND LOWER(TRIM(card)) NOT IN UNNEST(@excluded_projects)
      GROUP BY card_name
    ),
    kept AS (
      SELECT
        TRIM(card) AS card_name,
        COUNT(*) AS n_kept,
        ROUND(AVG(elo_delta), 3) AS delta_kept,
        ROUND(AVG(elo), 0) AS avg_elo
      FROM log_filtered
      CROSS JOIN UNNEST(IFNULL(opening_keep, [])) AS card
      WHERE TRIM(card) != ''
        AND LOWER(TRIM(card)) NOT IN UNNEST(@excluded_projects)
      GROUP BY card_name
    )
    SELECT
      u.card_type,
      u.card_name,
      COALESCE(d.delta_dealt, 0) AS delta_played,
      COALESCE(k.delta_kept, 0) AS delta_in_hand,
      COALESCE(k.avg_elo, 0) AS avg_elo,
      COALESCE(k.n_kept, 0) AS n_played,
      COALESCE(d.n_dealt, 0) AS n_seen,
      CASE
        WHEN COALESCE(d.n_dealt, 0) = 0 THEN 0
        ELSE ROUND(100.0 * COALESCE(k.n_kept, 0) / d.n_dealt, 2)
      END AS playrate_pct
    FROM card_universe u
    LEFT JOIN dealt d USING(card_name)
    LEFT JOIN kept k USING(card_name)
    ORDER BY u.card_type, playrate_pct DESC, n_seen DESC, u.card_name
    """


def _build_endgames_stats_query(where_sql, endgames_view=ENDGAMES_VIEW_GENERAL):
    if endgames_view == ENDGAMES_VIEW_CP_DISTRIBUTION:
        return _build_endgames_cp_distribution_query(where_sql)
    if endgames_view == ENDGAMES_VIEW_CP_BY_MAP:
        return _build_endgames_cp_by_map_query(where_sql)
    return _build_endgames_general_query(where_sql)


def _build_endgames_general_query(where_sql):
    return f"""
    WITH log_filtered AS (
      SELECT
        table_id,
        player,
        endgame,
        endgame_scores,
        elo_delta,
        elo
      FROM `{PREPARED_LOGS_TABLE}`
      WHERE {where_sql}
    ),
    table_scope AS (
      SELECT table_id
      FROM `{PREPARED_LOGS_TABLE}`
      WHERE {where_sql}
      GROUP BY table_id
    ),
    non_conceded_tables AS (
      SELECT p.table_id
      FROM `{PREPARED_LOGS_TABLE}` p
      JOIN table_scope s USING(table_id)
      GROUP BY p.table_id
      HAVING COUNTIF(COALESCE(p.concede, 0) != 0) = 0
    ),
    scored_filtered AS (
      SELECT lf.*
      FROM log_filtered lf
      JOIN non_conceded_tables n USING(table_id)
    ),
    dealt_counts AS (
      SELECT
        TRIM(card) AS card_name,
        COUNT(*) AS n_dealt
      FROM log_filtered
      CROSS JOIN UNNEST(IFNULL(endgame, [])) AS card
      WHERE TRIM(card) != ''
      GROUP BY card_name
    ),
    non_adapt_rows AS (
      SELECT DISTINCT
        sf.table_id,
        sf.player
      FROM scored_filtered sf
      CROSS JOIN UNNEST(IFNULL(sf.endgame, [])) AS dealt_card
      CROSS JOIN UNNEST(IFNULL(sf.endgame_scores, [])) AS score
      WHERE TRIM(dealt_card) != ''
        AND TRIM(score.endgame) = TRIM(dealt_card)
    ),
    dealt_delta AS (
      SELECT
        TRIM(card) AS card_name,
        ROUND(AVG(sf.elo_delta), 3) AS delta_dealt
      FROM scored_filtered sf
      LEFT JOIN non_adapt_rows nr
        ON sf.table_id = nr.table_id AND sf.player = nr.player
      CROSS JOIN UNNEST(IFNULL(sf.endgame, [])) AS card
      WHERE TRIM(card) != ''
        AND (@is_mw = 0 OR nr.table_id IS NOT NULL)
      GROUP BY card_name
    ),
    scored AS (
      SELECT
        TRIM(score.endgame) AS card_name,
        COUNT(*) AS n_scored,
        ROUND(AVG(elo_delta), 3) AS delta_scored,
        ROUND(AVG(elo), 0) AS avg_elo,
        ROUND(AVG(SAFE_CAST(score.cp AS FLOAT64)), 2) AS avg_cp
      FROM scored_filtered
      CROSS JOIN UNNEST(IFNULL(endgame_scores, [])) AS score
      WHERE TRIM(score.endgame) != ''
      GROUP BY card_name
    ),
    endgame_universe AS (
      SELECT card_name FROM dealt_counts
      UNION DISTINCT
      SELECT card_name FROM scored
    )
    SELECT
      'endgame' AS card_type,
      u.card_name,
      dd.delta_dealt AS delta_played,
      s.delta_scored AS delta_in_hand,
      s.avg_elo,
      COALESCE(s.n_scored, 0) AS n_played,
      COALESCE(dc.n_dealt, 0) AS n_seen,
      CASE
        WHEN COALESCE(dc.n_dealt, 0) = 0 THEN NULL
        ELSE ROUND(100.0 * COALESCE(s.n_scored, 0) / dc.n_dealt, 2)
      END AS playrate_pct,
      s.avg_cp
    FROM endgame_universe u
    LEFT JOIN dealt_counts dc USING(card_name)
    LEFT JOIN dealt_delta dd USING(card_name)
    LEFT JOIN scored s USING(card_name)
    ORDER BY playrate_pct DESC NULLS LAST, n_played DESC, u.card_name
    """


def _build_endgames_cp_distribution_query(where_sql):
    return f"""
    WITH log_filtered AS (
      SELECT
        table_id,
        player,
        endgame_scores
      FROM `{PREPARED_LOGS_TABLE}`
      WHERE {where_sql}
    ),
    table_scope AS (
      SELECT table_id
      FROM `{PREPARED_LOGS_TABLE}`
      WHERE {where_sql}
      GROUP BY table_id
    ),
    non_conceded_tables AS (
      SELECT p.table_id
      FROM `{PREPARED_LOGS_TABLE}` p
      JOIN table_scope s USING(table_id)
      GROUP BY p.table_id
      HAVING COUNTIF(COALESCE(p.concede, 0) != 0) = 0
    ),
    scored_events AS (
      SELECT
        TRIM(score.endgame) AS card_name,
        SAFE_CAST(score.cp AS INT64) AS cp
      FROM log_filtered lf
      JOIN non_conceded_tables n USING(table_id)
      CROSS JOIN UNNEST(IFNULL(lf.endgame_scores, [])) AS score
      WHERE TRIM(score.endgame) != ''
        AND SAFE_CAST(score.cp AS INT64) BETWEEN 0 AND 4
    )
    SELECT
      'endgame' AS card_type,
      card_name,
      NULL AS delta_played,
      NULL AS delta_in_hand,
      NULL AS avg_elo,
      COUNT(*) AS n_played,
      NULL AS n_seen,
      NULL AS playrate_pct,
      ROUND(AVG(CAST(cp AS FLOAT64)), 2) AS avg_cp,
      ROUND(100.0 * COUNTIF(cp = 0) / COUNT(*), 2) AS cp_0_pct,
      ROUND(100.0 * COUNTIF(cp = 1) / COUNT(*), 2) AS cp_1_pct,
      ROUND(100.0 * COUNTIF(cp = 2) / COUNT(*), 2) AS cp_2_pct,
      ROUND(100.0 * COUNTIF(cp = 3) / COUNT(*), 2) AS cp_3_pct,
      ROUND(100.0 * COUNTIF(cp = 4) / COUNT(*), 2) AS cp_4_pct
    FROM scored_events
    GROUP BY card_name
    ORDER BY avg_cp DESC NULLS LAST, n_played DESC, card_name
    """


def _build_endgames_cp_by_map_query(where_sql):
    return f"""
    WITH log_filtered AS (
      SELECT
        table_id,
        player,
        Map,
        endgame_scores
      FROM `{PREPARED_LOGS_TABLE}`
      WHERE {where_sql}
    ),
    table_scope AS (
      SELECT table_id
      FROM `{PREPARED_LOGS_TABLE}`
      WHERE {where_sql}
      GROUP BY table_id
    ),
    non_conceded_tables AS (
      SELECT p.table_id
      FROM `{PREPARED_LOGS_TABLE}` p
      JOIN table_scope s USING(table_id)
      GROUP BY p.table_id
      HAVING COUNTIF(COALESCE(p.concede, 0) != 0) = 0
    ),
    scored_events AS (
      SELECT
        TRIM(score.endgame) AS card_name,
        lf.Map AS map_name,
        SAFE_CAST(score.cp AS FLOAT64) AS cp
      FROM log_filtered lf
      JOIN non_conceded_tables n USING(table_id)
      CROSS JOIN UNNEST(IFNULL(lf.endgame_scores, [])) AS score
      WHERE TRIM(score.endgame) != ''
        AND SAFE_CAST(score.cp AS INT64) BETWEEN 0 AND 4
    )
    SELECT
      'endgame' AS card_type,
      card_name,
      NULL AS delta_played,
      NULL AS delta_in_hand,
      NULL AS avg_elo,
      COUNT(*) AS n_played,
      NULL AS n_seen,
      NULL AS playrate_pct,
      ROUND(AVG(cp), 2) AS avg_cp,
      ROUND(AVG(IF(map_name = 'Map 1a: Observation Tower', cp, NULL)), 2) AS map_1a,
      ROUND(AVG(IF(map_name = 'Map 2a: Outdoor Areas', cp, NULL)), 2) AS map_2a,
      ROUND(AVG(IF(map_name = 'Map 3a: Silver Lake', cp, NULL)), 2) AS map_3a,
      ROUND(AVG(IF(map_name = 'Map 4a: Commercial Harbor', cp, NULL)), 2) AS map_4a,
      ROUND(AVG(IF(map_name = 'Map 5a: Park Restaurant', cp, NULL)), 2) AS map_5a,
      ROUND(AVG(IF(map_name = 'Map 6a: Research Institute', cp, NULL)), 2) AS map_6a,
      ROUND(AVG(IF(map_name = 'Map 7a: Ice Cream Parlors', cp, NULL)), 2) AS map_7a,
      ROUND(AVG(IF(map_name = 'Map 8a: Hollywood Hills', cp, NULL)), 2) AS map_8a,
      ROUND(AVG(IF(map_name = 'Map 9: Geographical Zoo', cp, NULL)), 2) AS map_9,
      ROUND(AVG(IF(map_name = 'Map 10: Rescue Station', cp, NULL)), 2) AS map_10,
      ROUND(AVG(IF(map_name = 'Map 11: Caves', cp, NULL)), 2) AS map_11,
      ROUND(AVG(IF(map_name = 'Map 12: Artificial Intelligence', cp, NULL)), 2) AS map_12,
      ROUND(AVG(IF(map_name = 'Map 13: Drawing Board', cp, NULL)), 2) AS map_13,
      ROUND(AVG(IF(map_name = 'Map 14: Lagoon', cp, NULL)), 2) AS map_14,
      ROUND(AVG(IF(map_name = 'Map T1: Tournament 1', cp, NULL)), 2) AS map_t1
    FROM scored_events
    GROUP BY card_name
    ORDER BY avg_cp DESC NULLS LAST, n_played DESC, card_name
    """


def _build_maps_metrics_where_sql(
    is_mw,
    player_elo_min,
    player_elo_max,
    opponent_elo_min,
    opponent_elo_max,
    date_from,
    date_to,
):
    where_clauses = ["CAST(is_mw AS INT64) = @is_mw", "table_conceded = 0"]
    query_parameters = [bigquery.ScalarQueryParameter("is_mw", "INT64", is_mw)]

    if player_elo_min is not None:
        where_clauses.append("elo >= @player_elo_min")
        query_parameters.append(bigquery.ScalarQueryParameter("player_elo_min", "INT64", player_elo_min))
    if player_elo_max is not None:
        where_clauses.append("elo <= @player_elo_max")
        query_parameters.append(bigquery.ScalarQueryParameter("player_elo_max", "INT64", player_elo_max))
    if opponent_elo_min is not None:
        where_clauses.append("opponent_elo >= @opponent_elo_min")
        query_parameters.append(bigquery.ScalarQueryParameter("opponent_elo_min", "INT64", opponent_elo_min))
    if opponent_elo_max is not None:
        where_clauses.append("opponent_elo <= @opponent_elo_max")
        query_parameters.append(bigquery.ScalarQueryParameter("opponent_elo_max", "INT64", opponent_elo_max))
    if date_from:
        where_clauses.append("game_date >= @date_from")
        query_parameters.append(bigquery.ScalarQueryParameter("date_from", "DATE", date_from))
    if date_to:
        where_clauses.append("game_date <= @date_to")
        query_parameters.append(bigquery.ScalarQueryParameter("date_to", "DATE", date_to))

    return " AND ".join(where_clauses), query_parameters


def _build_full_sample_where_sql(
    is_mw,
    selected_maps,
    player_elo_min,
    player_elo_max,
    opponent_elo_min,
    opponent_elo_max,
    date_from,
    date_to,
    end_game_triggered,
    exclude_invalid_maps=True,
):
    where_clauses = [
        "CAST(f.is_mw AS INT64) = @is_mw",
        "f.Map IN UNNEST(@selected_maps)",
    ]
    query_parameters = [
        bigquery.ScalarQueryParameter("is_mw", "INT64", is_mw),
        bigquery.ArrayQueryParameter("selected_maps", "STRING", selected_maps),
    ]
    if exclude_invalid_maps:
        where_clauses.append("f.Map NOT IN UNNEST(@invalid_maps)")
        query_parameters.append(bigquery.ArrayQueryParameter("invalid_maps", "STRING", INVALID_MAPS))

    if player_elo_min is not None:
        where_clauses.append("f.elo >= @player_elo_min")
        query_parameters.append(bigquery.ScalarQueryParameter("player_elo_min", "INT64", player_elo_min))
    if player_elo_max is not None:
        where_clauses.append("f.elo <= @player_elo_max")
        query_parameters.append(bigquery.ScalarQueryParameter("player_elo_max", "INT64", player_elo_max))
    if opponent_elo_min is not None:
        where_clauses.append("f.opponent_elo >= @opponent_elo_min")
        query_parameters.append(bigquery.ScalarQueryParameter("opponent_elo_min", "INT64", opponent_elo_min))
    if opponent_elo_max is not None:
        where_clauses.append("f.opponent_elo <= @opponent_elo_max")
        query_parameters.append(bigquery.ScalarQueryParameter("opponent_elo_max", "INT64", opponent_elo_max))
    if date_from:
        where_clauses.append("CAST(f.game_ended_at AS DATE) >= @date_from")
        query_parameters.append(bigquery.ScalarQueryParameter("date_from", "DATE", date_from))
    if date_to:
        where_clauses.append("CAST(f.game_ended_at AS DATE) <= @date_to")
        query_parameters.append(bigquery.ScalarQueryParameter("date_to", "DATE", date_to))
    if end_game_triggered is not None:
        where_clauses.append("f.end_game_triggered = @end_game_triggered")
        query_parameters.append(bigquery.ScalarQueryParameter("end_game_triggered", "BOOL", end_game_triggered))

    return " AND ".join(where_clauses), query_parameters


def _build_maps_metrics_query(where_sql):
    metric_definitions = [
        ("games", 1, "Games", None, True, "compact", False),
        ("turns", 2, "Turns", None, True, "number", True),
        ("rounds", 3, "Rounds", None, True, "number", True),
        ("points_per_turn", 4, "Points per turn", None, True, "number", False),
        ("points_per_money", 5, "Points per money", None, True, "number", False),
        ("money_per_turn", 6, "Money per turn", None, True, "number", False),
        ("score", 7, "Score", None, True, "number", False),
        ("appeal", 8, "Appeal", None, True, "number", False),
        ("conservation", 9, "Conservation", None, True, "number", False),
        ("reputation", 10, "Reputation", None, True, "number", False),
        ("projects", 11, "Projects", None, True, "number", False),
        ("upgrades", 12, "Upgrades", None, True, "number", False),
        ("workers", 13, "Workers", None, True, "number", False),
        ("cover_pct", 14, "Cover%", "percentage of map hexes covered", True, "percent", False),
        ("fill_pct", 15, "Fill%", "percentage of games with map fill", True, "percent", False),
        ("animals_pct", 16, "Animals%", "percentage of games with Animals upgrade", True, "percent", False),
        ("association_pct", 17, "Association%", "percentage of games with Association upgrade", True, "percent", False),
        ("build_pct", 18, "Build%", "percentage of games with Build upgrade", True, "percent", False),
        ("cards_pct", 19, "Cards%", "percentage of games with Cards upgrade", True, "percent", False),
        ("sponsors_pct", 20, "Sponsors%", "percentage of games with Sponsors upgrade", True, "percent", False),
        ("determinations", 21, "Determinations", None, False, "number", False),
        ("animals_actions", 22, "Animals actions", None, False, "number", False),
        ("association_actions", 23, "Association actions", None, False, "number", False),
        ("build_actions", 24, "Build actions", None, False, "number", False),
        ("cards_actions", 25, "Cards actions", None, False, "number", False),
        ("sponsors_actions", 26, "Sponsors actions", None, False, "number", False),
        ("universities", 27, "Universities", None, False, "number", False),
        ("partner_zoos", 28, "Partner zoos", None, False, "number", False),
        ("x_tokens_gained", 29, "X-token gained", None, False, "number", False),
        ("x_tokens_spent", 30, "X-token spent", None, False, "number", False),
        ("x_backs", 31, "X-backs", None, False, "number", False),
        ("money_gained", 32, "Money gained", None, False, "number", False),
        ("money_spent_animals", 33, "Money spent (Animals)", None, False, "number", False),
        ("money_spent_build", 34, "Money spent (Build)", None, False, "number", False),
        ("money_spent_donations", 35, "Money spent (Donations)", None, False, "number", False),
        ("money_spent_range", 36, "Money spent (Range)", "money spent for playing cards from reputation range", False, "number", False),
        ("cards_drawn_deck", 37, "Cards drawn from deck", None, False, "number", False),
        ("cards_drawn_range", 38, "Cards drawn from range", None, False, "number", False),
        ("cards_snapped", 39, "Cards snapped", None, False, "number", False),
        ("cards_discarded", 40, "Cards discarded", None, False, "number", False),
        ("enclosures", 41, "Enclosures", None, False, "number", False),
        ("kiosks", 42, "Kiosks", None, False, "number", False),
        ("pavilions", 43, "Pavilions", None, False, "number", False),
        ("unique_buildings", 44, "Unique buildings", None, False, "number", False),
        ("animals_played", 45, "Animals played", None, False, "number", False),
        ("animals_released", 46, "Animals released", None, False, "number", False),
        ("sponsors_played", 47, "Sponsors played", None, False, "number", False),
        ("bird_icons", 48, "Bird icons", None, False, "number", False),
        ("herbivore_icons", 49, "Herbivore icons", None, False, "number", False),
        ("predator_icons", 50, "Predator icons", None, False, "number", False),
        ("primate_icons", 51, "Primate icons", None, False, "number", False),
        ("reptile_icons", 52, "Reptile icons", None, False, "number", False),
        ("sea_animal_icons", 53, "Sea Animal icons", None, False, "number", False),
        ("bear_icons", 54, "Bear icons", None, False, "number", False),
        ("petting_zoo_icons", 55, "Petting zoo icons", None, False, "number", False),
        ("africa_icons", 56, "Africa icons", None, False, "number", False),
        ("america_icons", 57, "America icons", None, False, "number", False),
        ("asia_icons", 58, "Asia icons", None, False, "number", False),
        ("australia_icons", 59, "Australia icons", None, False, "number", False),
        ("europe_icons", 60, "Europe icons", None, False, "number", False),
        ("rock_icons", 61, "Rock icons", None, False, "number", False),
        ("water_icons", 62, "Water icons", None, False, "number", False),
        ("science_icons", 63, "Science icons", None, False, "number", False),
    ]
    metric_config_sql = ",\n        ".join(
        "STRUCT("
        f"{_sql_string(key)} AS metric_key, "
        f"{sort_order} AS sort_order, "
        f"{_sql_string(label)} AS metric, "
        f"{_sql_string(tooltip) if tooltip else 'CAST(NULL AS STRING)'} AS tooltip, "
        f"{'TRUE' if is_default else 'FALSE'} AS is_default, "
        f"{_sql_string(value_format)} AS format, "
        f"{'TRUE' if lower_is_better else 'FALSE'} AS lower_is_better"
        ")"
        for key, sort_order, label, tooltip, is_default, value_format, lower_is_better
        in metric_definitions
    )
    metric_keys_sql = ", ".join(item[0] for item in metric_definitions)
    map_value_selects = ",\n      ".join(
        f"ROUND(MAX(IF(map_name = '{m['full']}', value, NULL)), 4) AS {m['key']}"
        for m in ALL_MAPS_FOR_METRICS
    )
    return f"""
    WITH filtered AS (
      SELECT *
      FROM `{PREPARED_FULL_STATS_TABLE}`
      WHERE {where_sql}
    ),
    per_map AS (
      SELECT
        Map AS map_name,
        CAST(COUNT(DISTINCT table_id) AS FLOAT64) AS games,
        AVG(SAFE_CAST(Number_of_turns AS FLOAT64)) AS turns,
        AVG(SAFE_CAST(total_breaks AS FLOAT64) + 1) AS rounds,
        AVG(SAFE_CAST(points_per_turn AS FLOAT64)) AS points_per_turn,
        AVG(SAFE_CAST(points_per_money AS FLOAT64)) AS points_per_money,
        AVG(SAFE_DIVIDE(SAFE_CAST(Money_gained AS FLOAT64), NULLIF(SAFE_CAST(Number_of_turns AS FLOAT64), 0))) AS money_per_turn,
        AVG(SAFE_CAST(Score AS FLOAT64)) AS score,
        AVG(SAFE_CAST(Appeal AS FLOAT64)) AS appeal,
        AVG(SAFE_CAST(Conservation AS FLOAT64)) AS conservation,
        AVG(SAFE_CAST(Reputation AS FLOAT64)) AS reputation,
        AVG(SAFE_CAST(Conservation_project_association_tasks AS FLOAT64)) AS projects,
        AVG(SAFE_CAST(Upgraded_action_cards AS FLOAT64)) AS upgrades,
        AVG(SAFE_CAST(Association_workers AS FLOAT64)) AS workers,
        AVG(100 * SAFE_DIVIDE(SAFE_CAST(Covered_hexes AS FLOAT64), IF(Map IN ('Map 5: Park Restaurant', 'Map 5a: Park Restaurant'), 43, 42))) AS cover_pct,
        AVG(100 * IF(SAFE_CAST(Covered_hexes AS INT64) >= IF(Map IN ('Map 5: Park Restaurant', 'Map 5a: Park Restaurant'), 43, 42), 1, 0)) AS fill_pct,
        AVG(100 * CAST(COALESCE(Upgraded_Animals_action_card, FALSE) AS INT64)) AS animals_pct,
        AVG(100 * CAST(COALESCE(Upgraded_Association_action_card, FALSE) AS INT64)) AS association_pct,
        AVG(100 * CAST(COALESCE(Upgraded_Build_action_card, FALSE) AS INT64)) AS build_pct,
        AVG(100 * CAST(COALESCE(Upgraded_Cards_action_card, FALSE) AS INT64)) AS cards_pct,
        AVG(100 * CAST(COALESCE(Upgraded_Sponsors_action_card, FALSE) AS INT64)) AS sponsors_pct,
        AVG(SAFE_CAST(determinations AS FLOAT64)) AS determinations,
        AVG(SAFE_CAST(Animals_actions AS FLOAT64)) AS animals_actions,
        AVG(SAFE_CAST(Association_actions AS FLOAT64)) AS association_actions,
        AVG(SAFE_CAST(Build_actions AS FLOAT64)) AS build_actions,
        AVG(SAFE_CAST(Cards_actions AS FLOAT64)) AS cards_actions,
        AVG(SAFE_CAST(Sponsors_actions AS FLOAT64)) AS sponsors_actions,
        AVG(SAFE_CAST(University_association_tasks AS FLOAT64)) AS universities,
        AVG(SAFE_CAST(Partner_zoo_association_tasks AS FLOAT64)) AS partner_zoos,
        AVG(SAFE_CAST(X_Tokens_gained AS FLOAT64)) AS x_tokens_gained,
        AVG(SAFE_CAST(X_Tokens_used AS FLOAT64)) AS x_tokens_spent,
        AVG(SAFE_CAST(X_Tokens_gained_instead_of_action AS FLOAT64)) AS x_backs,
        AVG(SAFE_CAST(Money_gained AS FLOAT64)) AS money_gained,
        AVG(SAFE_CAST(Money_spent_on_animals AS FLOAT64)) AS money_spent_animals,
        AVG(SAFE_CAST(Money_spent_on_enclosures AS FLOAT64)) AS money_spent_build,
        AVG(SAFE_CAST(Money_spent_on_donations AS FLOAT64)) AS money_spent_donations,
        AVG(SAFE_CAST(Money_spent_for_playing_cards_from_reputation_range AS FLOAT64)) AS money_spent_range,
        AVG(SAFE_CAST(Cards_drawn_from_deck AS FLOAT64)) AS cards_drawn_deck,
        AVG(SAFE_CAST(Cards_taken_from_reputation_range AS FLOAT64)) AS cards_drawn_range,
        AVG(SAFE_CAST(Snapped_cards AS FLOAT64)) AS cards_snapped,
        AVG(SAFE_CAST(Discarded_cards AS FLOAT64)) AS cards_discarded,
        AVG(SAFE_CAST(Built_enclosures AS FLOAT64)) AS enclosures,
        AVG(SAFE_CAST(Built_kiosks AS FLOAT64)) AS kiosks,
        AVG(SAFE_CAST(Built_pavilions AS FLOAT64)) AS pavilions,
        AVG(SAFE_CAST(Built_unique_buildings AS FLOAT64)) AS unique_buildings,
        AVG(SAFE_CAST(Played_animals AS FLOAT64)) AS animals_played,
        AVG(SAFE_CAST(Released_animals AS FLOAT64)) AS animals_released,
        AVG(SAFE_CAST(Played_sponsors AS FLOAT64)) AS sponsors_played,
        AVG(SAFE_CAST(Bird_icons AS FLOAT64)) AS bird_icons,
        AVG(SAFE_CAST(Herbivore_icons AS FLOAT64)) AS herbivore_icons,
        AVG(SAFE_CAST(Predator_icons AS FLOAT64)) AS predator_icons,
        AVG(SAFE_CAST(Primate_icons AS FLOAT64)) AS primate_icons,
        AVG(SAFE_CAST(Reptile_icons AS FLOAT64)) AS reptile_icons,
        AVG(SAFE_CAST(Sea_Animal_icons AS FLOAT64)) AS sea_animal_icons,
        AVG(SAFE_CAST(Bear_icons AS FLOAT64)) AS bear_icons,
        AVG(SAFE_CAST(Petting_Zoo_icons AS FLOAT64)) AS petting_zoo_icons,
        AVG(SAFE_CAST(Africa_icons AS FLOAT64)) AS africa_icons,
        AVG(SAFE_CAST(Americas_icons AS FLOAT64)) AS america_icons,
        AVG(SAFE_CAST(Asia_icons AS FLOAT64)) AS asia_icons,
        AVG(SAFE_CAST(Australia_icons AS FLOAT64)) AS australia_icons,
        AVG(SAFE_CAST(Europe_icons AS FLOAT64)) AS europe_icons,
        AVG(SAFE_CAST(Rock_icons AS FLOAT64)) AS rock_icons,
        AVG(SAFE_CAST(Water_icons AS FLOAT64)) AS water_icons,
        AVG(SAFE_CAST(Science_icons AS FLOAT64)) AS science_icons
      FROM filtered
      GROUP BY Map
    ),
    metric_config AS (
      SELECT *
      FROM UNNEST([
        {metric_config_sql}
      ])
    ),
    unpivoted AS (
      SELECT map_name, metric_key, value
      FROM per_map
      UNPIVOT INCLUDE NULLS (
        value FOR metric_key IN ({metric_keys_sql})
      )
    ),
    metric_values AS (
      SELECT
        c.sort_order,
        c.metric,
        c.tooltip,
        c.is_default,
        c.format,
        c.lower_is_better,
        u.map_name,
        u.value
      FROM unpivoted u
      JOIN metric_config c USING(metric_key)
    )
    SELECT
      sort_order,
      metric,
      tooltip,
      is_default,
      format,
      lower_is_better,
      {map_value_selects}
    FROM metric_values
    GROUP BY sort_order, metric, tooltip, is_default, format, lower_is_better
    ORDER BY sort_order
    """


def _build_maps_tournament_h2h_query():
    # H2H reads a native BigQuery cache because Cloud Functions cannot reliably
    # query the Google Sheets external table without Drive-scoped credentials.
    return f"""
    WITH tournament_tables AS (
      SELECT DISTINCT CAST(table_id AS STRING) AS table_id
      FROM `{TOURNAMENT_TABLES_CACHE_TABLE}`
      WHERE table_id IS NOT NULL
    ),
    scoped AS (
      SELECT
        CAST(f.table_id AS STRING) AS table_id,
        f.player,
        f.Map AS map_name,
        SAFE_CAST(f.Score AS FLOAT64) AS score,
        SAFE_CAST(f.Conservation_project_association_tasks AS FLOAT64) AS projects,
        LOWER(TRIM(CAST(f.Starting_position_in_first_round AS STRING))) AS start_position,
        SAFE_CAST(f.elo_delta AS FLOAT64) AS elo_delta
      FROM `freestyle-190711.ark_nova.all_games_stat` f
      JOIN tournament_tables t
        ON CAST(f.table_id AS STRING) = t.table_id
      WHERE CAST(f.is_mw AS INT64) = @is_mw
        AND f.Map IN UNNEST(@h2h_maps)
    ),
    asymmetric_tables AS (
      SELECT table_id
      FROM scoped
      GROUP BY table_id
      HAVING COUNT(*) = 2
        AND COUNT(DISTINCT map_name) = 2
        AND COUNTIF(score IS NULL) = 0
    ),
    paired AS (
      SELECT
        a.table_id,
        a.map_name AS row_map,
        b.map_name AS col_map,
        a.elo_delta AS row_delta,
        CASE
          WHEN a.score > b.score THEN 1.0
          WHEN a.score < b.score THEN 0.0
          WHEN a.projects > b.projects THEN 1.0
          WHEN a.projects < b.projects THEN 0.0
          WHEN a.start_position = 'second player' AND COALESCE(b.start_position, '') != 'second player' THEN 1.0
          WHEN b.start_position = 'second player' AND COALESCE(a.start_position, '') != 'second player' THEN 0.0
          ELSE NULL
        END AS row_win
      FROM scoped a
      JOIN scoped b
        ON a.table_id = b.table_id
       AND a.player != b.player
      JOIN asymmetric_tables v
        ON a.table_id = v.table_id
      WHERE a.map_name != b.map_name
    ),
    resolved AS (
      SELECT *
      FROM paired
      WHERE row_win IS NOT NULL
    ),
    matchups AS (
      SELECT
        'matchup' AS row_type,
        row_map,
        col_map,
        COUNT(*) AS games,
        CAST(SUM(row_win) AS INT64) AS wins,
        CAST(COUNT(*) - SUM(row_win) AS INT64) AS losses,
        ROUND(100 * AVG(row_win), 4) AS win_pct,
        ROUND(AVG(row_delta), 4) AS elo_delta
      FROM resolved
      GROUP BY row_map, col_map
    ),
    overall AS (
      SELECT
        'overall' AS row_type,
        row_map,
        CAST(NULL AS STRING) AS col_map,
        COUNT(*) AS games,
        CAST(SUM(row_win) AS INT64) AS wins,
        CAST(COUNT(*) - SUM(row_win) AS INT64) AS losses,
        ROUND(100 * AVG(row_win), 4) AS win_pct,
        ROUND(AVG(row_delta), 4) AS elo_delta
      FROM resolved
      GROUP BY row_map
    )
    SELECT * FROM matchups
    UNION ALL
    SELECT * FROM overall
    ORDER BY row_type, row_map, col_map
    """


def _build_home_stats_query(where_sql):
    return f"""
    WITH full_filtered AS (
      SELECT f.*
      FROM `{PREPARED_FULL_STATS_TABLE}` f
      WHERE {where_sql}
    ),
    log_filtered AS (
      SELECT
        f.table_id,
        f.player,
        f.Petting_Zoo_icons,
        l.played_animals,
        l.played_projects,
        l.cards_drawn,
        l.two_cp_worker,
        l.petting_zoo_built,
        l.chosen_5cp_bonus,
        l.chosen_8cp_bonus
      FROM full_filtered f
      JOIN `{PREPARED_LOGS_TABLE}` l
        ON f.table_id = l.table_id
       AND f.player = l.player
    ),
    full_metrics AS (
      SELECT
        COUNT(DISTINCT table_id) AS games_indexed,
        SUM(COALESCE(SAFE_CAST(Played_animals AS INT64), 0)) AS animals_played,
        SUM(COALESCE(SAFE_CAST(Played_sponsors AS INT64), 0)) AS sponsors_played,
        SUM(COALESCE(SAFE_CAST(Conservation_project_association_tasks AS INT64), 0)) AS projects_supported,
        SUM(COALESCE(SAFE_CAST(Number_of_breaks_triggered AS INT64), 0)) AS breaks_triggered,
        SUM(COALESCE(SAFE_CAST(X_Tokens_gained AS INT64), 0)) AS x_tokens_gained
      FROM full_filtered
    ),
    emus AS (
      SELECT COUNT(*) AS emus_played
      FROM log_filtered l
      CROSS JOIN UNNEST(IFNULL(l.played_animals, [])) AS pa
      WHERE pa.animal = 'Emu'
    ),
    bignose AS (
      SELECT COUNT(*) AS bignose_project_blocks
      FROM log_filtered holder
      JOIN log_filtered other
        ON holder.table_id = other.table_id
       AND holder.player != other.player
      WHERE 'Primates' IN UNNEST(IFNULL(holder.cards_drawn, []))
        AND NOT EXISTS (
          SELECT 1
          FROM UNNEST(IFNULL(holder.played_projects, [])) AS pp
          WHERE pp.project = 'Primates'
        )
        AND EXISTS (
          SELECT 1
          FROM UNNEST(IFNULL(other.played_animals, [])) AS pa
          WHERE pa.animal = 'Proboscis Monkey'
        )
    ),
    log_metrics AS (
      SELECT
        COUNT(DISTINCT table_id) AS games_logged,
        COUNTIF(COALESCE(two_cp_worker, FALSE)) AS two_cp_workers_taken,
        COUNTIF(COALESCE(petting_zoo_built, 0) = 1 AND COALESCE(Petting_Zoo_icons, 0) = 0) AS empty_petting_zoos_played,
        SUM(
          IF(chosen_5cp_bonus IN ('1 University', '1 Partner-Zoo'), 1, 0)
          + IF(chosen_8cp_bonus IN ('1 University', '1 Partner-Zoo'), 1, 0)
        ) AS free_unis_and_partner_zoos
      FROM log_filtered
    )
    SELECT 'games_indexed' AS metric, games_indexed AS value FROM full_metrics
    UNION ALL SELECT 'animals_played', animals_played FROM full_metrics
    UNION ALL SELECT 'sponsors_played', sponsors_played FROM full_metrics
    UNION ALL SELECT 'projects_supported', projects_supported FROM full_metrics
    UNION ALL SELECT 'breaks_triggered', breaks_triggered FROM full_metrics
    UNION ALL SELECT 'x_tokens_gained', x_tokens_gained FROM full_metrics
    UNION ALL SELECT 'games_logged', games_logged FROM log_metrics
    UNION ALL SELECT 'emus_played', emus_played FROM emus
    UNION ALL SELECT 'two_cp_workers_taken', two_cp_workers_taken FROM log_metrics
    UNION ALL SELECT 'empty_petting_zoos_played', empty_petting_zoos_played FROM log_metrics
    UNION ALL SELECT 'free_unis_and_partner_zoos', free_unis_and_partner_zoos FROM log_metrics
    UNION ALL SELECT 'bignose_project_blocks', bignose_project_blocks FROM bignose
    """


def _sponsor_cp_config_sql():
    parts = []
    for sponsor in SPONSOR_CP_CARDS:
        if sponsor in SPONSOR_CP_0_1_2_3PLUS:
            values = [0, 1, 2, 3]
        elif sponsor in SPONSOR_CP_0_1_2:
            values = [0, 1, 2]
        else:
            values = [0, 1]
        parts.append(
            f"STRUCT({_sql_string(sponsor)} AS sponsor, [{', '.join(str(v) for v in values)}] AS possible_values)"
        )
    return ",\n        ".join(parts)


def _sponsor_appeal_config_sql():
    parts = []
    for sponsor, values in SPONSOR_APPEAL_VALUES.items():
        parts.append(
            f"STRUCT({_sql_string(sponsor)} AS sponsor, [{', '.join(str(v) for v in values)}] AS possible_values)"
        )
    return ",\n        ".join(parts)


def _build_sponsor_endgames_query(where_sql, sponsor_endgames_view):
    if sponsor_endgames_view == SPONSOR_ENDGAMES_VIEW_APPEAL:
        config_sql = _sponsor_appeal_config_sql()
        value_expr = "SAFE_CAST(event.appeal AS INT64)"
        avg_alias = "avg_appeal"
        delta_selects = ",\n      ".join(
            f"ROUND(AVG(IF(value = {v} AND {v} IN UNNEST(possible_values), elo_delta, NULL)), 3) AS delta_{v}"
            for v in range(7)
        )
        count_selects = ",\n      ".join(
            f"COUNTIF(value = {v} AND {v} IN UNNEST(possible_values)) AS count_{v}"
            for v in range(7)
        )
    else:
        config_sql = _sponsor_cp_config_sql()
        value_expr = "SAFE_CAST(event.cp AS INT64)"
        avg_alias = "avg_cp"
        delta_selects = """
      ROUND(AVG(IF(value = 0 AND 0 IN UNNEST(possible_values), elo_delta, NULL)), 3) AS delta_0,
      ROUND(AVG(IF(value = 1 AND 1 IN UNNEST(possible_values), elo_delta, NULL)), 3) AS delta_1,
      ROUND(AVG(IF(value = 2 AND 2 IN UNNEST(possible_values), elo_delta, NULL)), 3) AS delta_2,
      ROUND(AVG(IF(value >= 3 AND 3 IN UNNEST(possible_values), elo_delta, NULL)), 3) AS delta_3_plus"""
        count_selects = """
      COUNTIF(value = 0 AND 0 IN UNNEST(possible_values)) AS count_0,
      COUNTIF(value = 1 AND 1 IN UNNEST(possible_values)) AS count_1,
      COUNTIF(value = 2 AND 2 IN UNNEST(possible_values)) AS count_2,
      COUNTIF(value >= 3 AND 3 IN UNNEST(possible_values)) AS count_3_plus"""

    return f"""
    WITH configured AS (
      SELECT *
      FROM UNNEST([
        {config_sql}
      ])
    ),
    filtered AS (
      SELECT *
      FROM `{PREPARED_LOGS_TABLE}`
      WHERE {where_sql}
    ),
    table_scope AS (
      SELECT table_id
      FROM filtered
      GROUP BY table_id
    ),
    non_conceded_tables AS (
      SELECT p.table_id
      FROM `{PREPARED_LOGS_TABLE}` p
      JOIN table_scope s USING(table_id)
      GROUP BY p.table_id
      HAVING COUNTIF(COALESCE(p.concede, 0) != 0) = 0
    ),
    scoped AS (
      SELECT f.*
      FROM filtered f
      JOIN non_conceded_tables n USING(table_id)
    ),
    played AS (
      SELECT DISTINCT
        s.table_id,
        s.player,
        played.sponsor,
        s.elo,
        s.elo_delta
      FROM scoped s
      CROSS JOIN UNNEST(IFNULL(s.played_sponsors, [])) AS played
      JOIN configured c
        ON played.sponsor = c.sponsor
    ),
    endgame_values AS (
      SELECT
        s.table_id,
        s.player,
        event.sponsor,
        MAX({value_expr}) AS value
      FROM scoped s
      CROSS JOIN UNNEST(IFNULL(s.endgame_from_sponsors, [])) AS event
      JOIN configured c
        ON event.sponsor = c.sponsor
      GROUP BY s.table_id, s.player, event.sponsor
    ),
    observations AS (
      SELECT
        p.sponsor,
        COALESCE(e.value, 0) AS value,
        p.elo,
        p.elo_delta
      FROM played p
      LEFT JOIN endgame_values e
        ON p.table_id = e.table_id
       AND p.player = e.player
       AND p.sponsor = e.sponsor
    ),
    aggregated AS (
      SELECT
        c.sponsor,
        c.possible_values,
        ROUND(AVG(o.value), 2) AS {avg_alias},
        ROUND(AVG(o.elo), 0) AS avg_elo,
        COUNT(o.sponsor) AS n_played,
        {delta_selects},
        {count_selects}
      FROM configured c
      LEFT JOIN observations o
        ON c.sponsor = o.sponsor
      GROUP BY c.sponsor, c.possible_values
    )
    SELECT *
    FROM aggregated
    ORDER BY {avg_alias} DESC NULLS LAST, n_played DESC, sponsor
    """


def _build_combinations_query(
    where_sql,
    combinations_view,
    round_filter_active=False,
    selected_rounds=None,
):
    selected_rounds = selected_rounds or []
    apply_round_filter = round_filter_active and combinations_view != COMBINATIONS_VIEW_CARD_ROUND
    round_sql = ""
    if apply_round_filter:
        exact_rounds = sorted(int(value) for value in selected_rounds if value != "6+")
        conditions = []
        if exact_rounds:
            conditions.append(f"played_round IN ({', '.join(str(value) for value in exact_rounds)})")
        if "6+" in selected_rounds:
            conditions.append("played_round >= 6")
        round_sql = f" AND ({' OR '.join(conditions)})"
    pair_round_sql = ""
    if apply_round_filter:
        pair_conditions_1 = []
        pair_conditions_2 = []
        if exact_rounds:
            exact_values = ", ".join(str(value) for value in exact_rounds)
            pair_conditions_1.append(
                f"EXISTS (SELECT 1 FROM UNNEST(played_rounds_1) AS r WHERE r IN ({exact_values}))"
            )
            pair_conditions_2.append(
                f"EXISTS (SELECT 1 FROM UNNEST(played_rounds_2) AS r WHERE r IN ({exact_values}))"
            )
        if "6+" in selected_rounds:
            pair_conditions_1.append(
                "EXISTS (SELECT 1 FROM UNNEST(played_rounds_1) AS r WHERE r >= 6)"
            )
            pair_conditions_2.append(
                "EXISTS (SELECT 1 FROM UNNEST(played_rounds_2) AS r WHERE r >= 6)"
            )
        pair_round_sql = (
            f" AND ({' OR '.join(pair_conditions_1)})"
            f" AND ({' OR '.join(pair_conditions_2)})"
        )
    common_ctes = f"""
    filtered AS (
      SELECT
        table_id, player, Map, elo, opponent_elo, elo_delta,
        card_name, card_type, played_round
      FROM `{PREPARED_CARD_PLAYS_TABLE}`
      WHERE {where_sql}
        {round_sql}
    ),
    played AS (
      SELECT *
      FROM filtered
    ),
    individual AS (
      SELECT
        card_name,
        ANY_VALUE(card_type) AS card_type,
        AVG(elo_delta) AS individual_delta
      FROM played
      GROUP BY card_name
    )
    """

    pair_type_sql = """
      CASE
        WHEN type_a = type_b THEN
          CONCAT(UPPER(SUBSTR(type_a, 1, 1)), SUBSTR(type_a, 2), ' + ',
                 UPPER(SUBSTR(type_b, 1, 1)), SUBSTR(type_b, 2))
        WHEN (type_a = 'animal' AND type_b = 'project')
          OR (type_a = 'project' AND type_b = 'animal') THEN 'Animal + Project'
        WHEN (type_a = 'animal' AND type_b = 'sponsor')
          OR (type_a = 'sponsor' AND type_b = 'animal') THEN 'Animal + Sponsor'
        ELSE 'Project + Sponsor'
      END
    """

    if combinations_view == COMBINATIONS_VIEW_CARD_MAP:
        return f"""
        WITH
        {common_ctes},
        per_map AS (
          SELECT
            card_name,
            ANY_VALUE(card_type) AS card_type,
            Map AS map_name,
            AVG(elo_delta) AS map_delta,
            AVG(elo) AS avg_elo,
            COUNT(*) AS n_played
          FROM played
          WHERE Map IN UNNEST(@combination_maps)
          GROUP BY card_name, Map
        )
        SELECT
          p.card_name,
          p.card_type,
          p.map_name,
          ROUND(i.individual_delta, 3) AS delta_general,
          ROUND(p.map_delta, 3) AS delta_map,
          ROUND(p.map_delta - i.individual_delta, 3) AS interaction,
          ROUND(p.avg_elo, 0) AS avg_elo,
          p.n_played
        FROM per_map p
        JOIN individual i USING(card_name)
        ORDER BY interaction DESC, n_played DESC, card_name, map_name
        """

    if combinations_view == COMBINATIONS_VIEW_CARD_ROUND:
        return f"""
        WITH
        {common_ctes},
        per_round AS (
          SELECT
            card_name,
            ANY_VALUE(card_type) AS card_type,
            IF(played_round >= 6, '6+', CAST(played_round AS STRING)) AS round_name,
            AVG(elo_delta) AS round_delta,
            AVG(elo) AS avg_elo,
            COUNT(*) AS n_played
          FROM played
          WHERE played_round IS NOT NULL
          GROUP BY card_name, round_name
        )
        SELECT
          p.card_name,
          p.card_type,
          p.round_name,
          ROUND(i.individual_delta, 3) AS delta_general,
          ROUND(p.round_delta, 3) AS delta_round,
          ROUND(p.round_delta - i.individual_delta, 3) AS interaction,
          ROUND(p.avg_elo, 0) AS avg_elo,
          p.n_played
        FROM per_round p
        JOIN individual i USING(card_name)
        ORDER BY interaction DESC, n_played DESC, card_name, round_name
        """

    return f"""
    WITH
    {common_ctes},
    pair_observations AS (
      SELECT
        table_id, player, card_1, type_1, card_2, type_2, elo_delta, elo
      FROM `{PREPARED_CARD_PAIRS_TABLE}`
      WHERE {where_sql}
        {pair_round_sql}
    ),
    pair_agg AS (
      SELECT
        card_1,
        ANY_VALUE(type_1) AS type_1,
        card_2,
        ANY_VALUE(type_2) AS type_2,
        AVG(elo_delta) AS delta_actual,
        AVG(elo) AS avg_elo,
        COUNT(*) AS n_played
      FROM pair_observations
      GROUP BY card_1, card_2
    )
    SELECT
      p.card_1,
      p.type_1,
      ROUND(i1.individual_delta, 3) AS delta_1,
      p.card_2,
      p.type_2,
      ROUND(i2.individual_delta, 3) AS delta_2,
      ROUND(i1.individual_delta + i2.individual_delta, 3) AS delta_combined,
      ROUND(p.delta_actual, 3) AS delta_actual,
      ROUND(p.delta_actual - (i1.individual_delta + i2.individual_delta), 3) AS interaction,
      ROUND(p.avg_elo, 0) AS avg_elo,
      p.n_played,
      {pair_type_sql} AS pair_type
    FROM pair_agg p
    JOIN individual i1 ON p.card_1 = i1.card_name
    JOIN individual i2 ON p.card_2 = i2.card_name
    CROSS JOIN UNNEST([STRUCT(p.type_1 AS type_a, p.type_2 AS type_b)])
    ORDER BY interaction DESC, n_played DESC, card_1, card_2
    """
def _query_card_stats(
    is_mw,
    selected_maps,
    card_types,
    selected_rounds,
    round_filter_active,
    stats_page,
    player_elo_min,
    player_elo_max,
    opponent_elo_min,
    opponent_elo_max,
    date_from,
    date_to,
    end_game_triggered,
    endgames_view=ENDGAMES_VIEW_GENERAL,
    maps_view=MAPS_VIEW_METRICS,
    sponsor_endgames_view=SPONSOR_ENDGAMES_VIEW_CP,
    combinations_view=COMBINATIONS_VIEW_CARD_CARD,
    use_query_cache=True,
):
    if stats_page == STATS_PAGE_HOME:
        where_sql, query_parameters = _build_full_sample_where_sql(
            is_mw,
            selected_maps,
            player_elo_min,
            player_elo_max,
            opponent_elo_min,
            opponent_elo_max,
            date_from,
            date_to,
            end_game_triggered,
            exclude_invalid_maps=False,
        )
        query = _build_home_stats_query(where_sql)
    elif stats_page == STATS_PAGE_MAPS:
        if maps_view == MAPS_VIEW_TOURNAMENT_H2H:
            query_parameters = [
                bigquery.ScalarQueryParameter("is_mw", "INT64", is_mw),
                bigquery.ArrayQueryParameter("h2h_maps", "STRING", VALID_MAPS),
            ]
            query = _build_maps_tournament_h2h_query()
        else:
            where_sql, query_parameters = _build_maps_metrics_where_sql(
                is_mw,
                player_elo_min,
                player_elo_max,
                opponent_elo_min,
                opponent_elo_max,
                date_from,
                date_to,
            )
            query = _build_maps_metrics_query(where_sql)
    else:
        where_sql, query_parameters = _build_where_sql(
            is_mw,
            selected_maps,
            player_elo_min,
            player_elo_max,
            opponent_elo_min,
            opponent_elo_max,
            date_from,
            date_to,
            end_game_triggered,
        )
    if stats_page == STATS_PAGE_SPONSOR_ENDGAMES:
        query = _build_sponsor_endgames_query(where_sql, sponsor_endgames_view)
    if stats_page == STATS_PAGE_COMBINATIONS:
        query = _build_combinations_query(
            where_sql,
            combinations_view,
            round_filter_active,
            selected_rounds,
        )
        if combinations_view == COMBINATIONS_VIEW_CARD_MAP:
            query_parameters.append(
                bigquery.ArrayQueryParameter("combination_maps", "STRING", VALID_MAPS)
            )
    if stats_page in (STATS_PAGE_CARDS, STATS_PAGE_OPENING_HAND):
        query_parameters.append(
            bigquery.ArrayQueryParameter("excluded_projects", "STRING", sorted(EXCLUDED_PROJECTS))
        )
    if stats_page == STATS_PAGE_OPENING_HAND:
        query = _build_opening_hand_stats_query(where_sql)
    elif stats_page == STATS_PAGE_ENDGAMES:
        query = _build_endgames_stats_query(where_sql, endgames_view)
    elif stats_page == STATS_PAGE_CARDS:
        query = _build_card_stats_query(where_sql, round_filter_active, selected_rounds)

    client_started_at = time.perf_counter()
    client = bigquery.Client(project=BIGQUERY_JOB_PROJECT)
    client_ms = _ms_since(client_started_at)
    job_config = bigquery.QueryJobConfig(
        query_parameters=query_parameters,
        use_query_cache=use_query_cache,
    )
    submit_started_at = time.perf_counter()
    job = client.query(query, job_config=job_config, location=BIGQUERY_LOCATION)
    submit_ms = _ms_since(submit_started_at)
    wait_started_at = time.perf_counter()
    results = job.result()
    query_wait_ms = _ms_since(wait_started_at)

    rows = []
    iteration_started_at = time.perf_counter()
    if stats_page == STATS_PAGE_HOME:
        for row in results:
            rows.append({
                "metric": row.metric,
                "value": row.value,
            })
        iteration_ms = _ms_since(iteration_started_at)
        timing = {
            "client_ms": client_ms,
            "submit_ms": submit_ms,
            "query_wait_ms": query_wait_ms,
            "iteration_ms": iteration_ms,
            "job_id": job.job_id,
            "job_created": _dt_iso(job.created),
            "job_started": _dt_iso(job.started),
            "job_ended": _dt_iso(job.ended),
            "job_cache_hit": job.cache_hit,
            "job_total_bytes_processed": job.total_bytes_processed,
            "job_total_slot_ms": job.slot_millis,
        }
        return rows, timing
    if stats_page == STATS_PAGE_MAPS:
        if maps_view == MAPS_VIEW_TOURNAMENT_H2H:
            for row in results:
                rows.append({
                    "row_type": row.row_type,
                    "row_map": row.row_map,
                    "col_map": row.col_map,
                    "games": row.games,
                    "wins": row.wins,
                    "losses": row.losses,
                    "win_pct": row.win_pct,
                    "elo_delta": row.elo_delta,
                })
        else:
            map_keys = [m["key"] for m in ALL_MAPS_FOR_METRICS]
            for row in results:
                item = {
                    "metric": row.metric,
                    "tooltip": row.tooltip,
                    "is_default": row.is_default,
                    "format": row.format,
                    "lower_is_better": row.lower_is_better,
                    "sort_order": row.sort_order,
                }
                for key in map_keys:
                    item[key] = getattr(row, key, None)
                rows.append(item)
        iteration_ms = _ms_since(iteration_started_at)
        timing = {
            "client_ms": client_ms,
            "submit_ms": submit_ms,
            "query_wait_ms": query_wait_ms,
            "iteration_ms": iteration_ms,
            "job_id": job.job_id,
            "job_created": _dt_iso(job.created),
            "job_started": _dt_iso(job.started),
            "job_ended": _dt_iso(job.ended),
            "job_cache_hit": job.cache_hit,
            "job_total_bytes_processed": job.total_bytes_processed,
            "job_total_slot_ms": job.slot_millis,
        }
        return rows, timing

    if stats_page == STATS_PAGE_SPONSOR_ENDGAMES:
        schema_field_names = {field.name for field in results.schema}
        for row in results:
            item = {
                "sponsor": row.sponsor,
                "possible_values": list(row.possible_values or []),
                "avg_elo": row.avg_elo,
                "n_played": row.n_played,
            }
            if "avg_cp" in schema_field_names:
                item["avg_cp"] = row.avg_cp
            if "avg_appeal" in schema_field_names:
                item["avg_appeal"] = row.avg_appeal
            for field_name in (
                "delta_0", "delta_1", "delta_2", "delta_3", "delta_4",
                "delta_5", "delta_6", "delta_3_plus", "count_0", "count_1",
                "count_2", "count_3", "count_4", "count_5", "count_6",
                "count_3_plus",
            ):
                if field_name in schema_field_names:
                    item[field_name] = getattr(row, field_name, None)
            rows.append(item)
        iteration_ms = _ms_since(iteration_started_at)
        timing = {
            "client_ms": client_ms,
            "submit_ms": submit_ms,
            "query_wait_ms": query_wait_ms,
            "iteration_ms": iteration_ms,
            "job_id": job.job_id,
            "job_created": _dt_iso(job.created),
            "job_started": _dt_iso(job.started),
            "job_ended": _dt_iso(job.ended),
            "job_cache_hit": job.cache_hit,
            "job_total_bytes_processed": job.total_bytes_processed,
            "job_total_slot_ms": job.slot_millis,
        }
        return rows, timing

    if stats_page == STATS_PAGE_COMBINATIONS:
        for row in results:
            if combinations_view == COMBINATIONS_VIEW_CARD_MAP:
                rows.append({
                    "card_name": row.card_name,
                    "card_type": row.card_type,
                    "map_name": row.map_name,
                    "delta_general": row.delta_general,
                    "delta_map": row.delta_map,
                    "interaction": row.interaction,
                    "avg_elo": row.avg_elo,
                    "n_played": row.n_played,
                })
            elif combinations_view == COMBINATIONS_VIEW_CARD_ROUND:
                rows.append({
                    "card_name": row.card_name,
                    "card_type": row.card_type,
                    "round_name": row.round_name,
                    "delta_general": row.delta_general,
                    "delta_round": row.delta_round,
                    "interaction": row.interaction,
                    "avg_elo": row.avg_elo,
                    "n_played": row.n_played,
                })
            else:
                rows.append({
                    "card_1": row.card_1,
                    "type_1": row.type_1,
                    "delta_1": row.delta_1,
                    "card_2": row.card_2,
                    "type_2": row.type_2,
                    "delta_2": row.delta_2,
                    "delta_combined": row.delta_combined,
                    "delta_actual": row.delta_actual,
                    "interaction": row.interaction,
                    "avg_elo": row.avg_elo,
                    "n_played": row.n_played,
                    "pair_type": row.pair_type,
                })
        iteration_ms = _ms_since(iteration_started_at)
        timing = {
            "client_ms": client_ms,
            "submit_ms": submit_ms,
            "query_wait_ms": query_wait_ms,
            "iteration_ms": iteration_ms,
            "job_id": job.job_id,
            "job_created": _dt_iso(job.created),
            "job_started": _dt_iso(job.started),
            "job_ended": _dt_iso(job.ended),
            "job_cache_hit": job.cache_hit,
            "job_total_bytes_processed": job.total_bytes_processed,
            "job_total_slot_ms": job.slot_millis,
        }
        return rows, timing

    allowed_card_types = set(card_types)
    if stats_page == STATS_PAGE_ENDGAMES:
        allowed_card_types = {"endgame"}
    schema_field_names = {field.name for field in results.schema}
    for row in results:
        if row.card_type in allowed_card_types:
            item = {
                "card_type": row.card_type,
                "card_name": row.card_name,
                "delta_played": row.delta_played,
                "delta_in_hand": row.delta_in_hand,
                "avg_elo": row.avg_elo,
                "n_played": row.n_played,
                "n_seen": row.n_seen,
                "playrate_pct": row.playrate_pct,
                "avg_cp": getattr(row, "avg_cp", None),
            }
            for field_name in (
                "cp_0_pct", "cp_1_pct", "cp_2_pct", "cp_3_pct", "cp_4_pct",
                "map_1a", "map_2a", "map_3a", "map_4a", "map_5a",
                "map_6a", "map_7a", "map_8a", "map_9", "map_10",
                "map_11", "map_12", "map_13", "map_14", "map_t1",
            ):
                if field_name in schema_field_names:
                    item[field_name] = getattr(row, field_name, None)
            rows.append(item)
    iteration_ms = _ms_since(iteration_started_at)

    timing = {
        "client_ms": client_ms,
        "submit_ms": submit_ms,
        "query_wait_ms": query_wait_ms,
        "iteration_ms": iteration_ms,
        "job_id": job.job_id,
        "job_created": _dt_iso(job.created),
        "job_started": _dt_iso(job.started),
        "job_ended": _dt_iso(job.ended),
        "job_cache_hit": job.cache_hit,
        "job_total_bytes_processed": job.total_bytes_processed,
        "job_total_slot_ms": job.slot_millis,
    }
    return rows, timing


def _refresh_default_snapshot_from_prepared(
    is_mw,
    stats_page=STATS_PAGE_CARDS,
    endgames_view=ENDGAMES_VIEW_GENERAL,
    maps_view=MAPS_VIEW_METRICS,
    sponsor_endgames_view=SPONSOR_ENDGAMES_VIEW_CP,
    combinations_view=COMBINATIONS_VIEW_CARD_CARD,
):
    started_at = time.perf_counter()
    is_home = stats_page == STATS_PAGE_HOME
    snapshot_date_from = None if is_home else (
        MAPS_METRICS_DEFAULT_DATE_FROM
        if stats_page == STATS_PAGE_MAPS and maps_view == MAPS_VIEW_METRICS
        else DEFAULT_DATE_FROM
    )
    rows, timing = _query_card_stats(
        int(is_mw),
        ALL_KNOWN_MAPS if is_home else VALID_MAPS,
        DEFAULT_CARD_TYPES,
        [],
        False,
        stats_page,
        None if is_home else 300,
        None,
        None if is_home else 300,
        None,
        snapshot_date_from,
        None,
        None,
        endgames_view=endgames_view,
        maps_view=maps_view,
        sponsor_endgames_view=sponsor_endgames_view,
        combinations_view=combinations_view,
        use_query_cache=False,
    )
    payload = {
        "status": "ok",
        "round_filter_active": False,
        "stats_page": stats_page,
        "endgames_view": endgames_view if stats_page == STATS_PAGE_ENDGAMES else None,
        "maps_view": maps_view if stats_page == STATS_PAGE_MAPS else None,
        "sponsor_endgames_view": (
            sponsor_endgames_view if stats_page == STATS_PAGE_SPONSOR_ENDGAMES else None
        ),
        "combinations_view": (
            combinations_view if stats_page == STATS_PAGE_COMBINATIONS else None
        ),
        "maps": ALL_MAPS_FOR_METRICS if stats_page == STATS_PAGE_MAPS else None,
        "data": rows,
        "cache_status": "refreshed",
        "source": (
            f"{stats_page}_{endgames_view}_default_snapshot"
            if stats_page == STATS_PAGE_ENDGAMES
            else f"{stats_page}_{maps_view}_default_snapshot"
            if stats_page == STATS_PAGE_MAPS
            else f"{stats_page}_{sponsor_endgames_view}_default_snapshot"
            if stats_page == STATS_PAGE_SPONSOR_ENDGAMES
            else f"{stats_page}_{combinations_view}_default_snapshot"
            if stats_page == STATS_PAGE_COMBINATIONS
            else f"{stats_page}_default_snapshot"
        ),
        "is_mw": int(is_mw),
        "row_count": len(rows),
        "total_ms": _ms_since(started_at),
        "job_id": timing["job_id"],
        "job_created": timing["job_created"],
        "job_started": timing["job_started"],
        "job_ended": timing["job_ended"],
        "job_total_bytes_processed": timing["job_total_bytes_processed"],
        "job_total_slot_ms": timing["job_total_slot_ms"],
    }
    cache_write_ok = _write_cached_snapshot(
        is_mw, payload, stats_page, endgames_view, maps_view,
        sponsor_endgames_view, combinations_view
    )
    return {
        "status": "ok" if cache_write_ok else "error",
        "is_mw": int(is_mw),
        "stats_page": stats_page,
        "endgames_view": endgames_view if stats_page == STATS_PAGE_ENDGAMES else None,
        "maps_view": maps_view if stats_page == STATS_PAGE_MAPS else None,
        "sponsor_endgames_view": (
            sponsor_endgames_view if stats_page == STATS_PAGE_SPONSOR_ENDGAMES else None
        ),
        "combinations_view": (
            combinations_view if stats_page == STATS_PAGE_COMBINATIONS else None
        ),
        "cache_status": "refreshed" if cache_write_ok else "cache_write_failed",
        "rows": len(rows),
        "total_ms": payload["total_ms"],
        "job_id": timing["job_id"],
        "job_total_bytes_processed": timing["job_total_bytes_processed"],
        "job_total_slot_ms": timing["job_total_slot_ms"],
    }


def _run_daily_refresh():
    started_at = time.perf_counter()
    prepared = _refresh_prepared_tables()
    data_version = _write_data_version(prepared)
    home_mw = _refresh_default_snapshot_from_prepared(1, STATS_PAGE_HOME)
    home_base = _refresh_default_snapshot_from_prepared(0, STATS_PAGE_HOME)
    home_bootstrap = _write_home_bootstrap_asset()
    mw = _refresh_default_snapshot_from_prepared(1, STATS_PAGE_CARDS)
    base = _refresh_default_snapshot_from_prepared(0, STATS_PAGE_CARDS)
    opening_hand_mw = _refresh_default_snapshot_from_prepared(1, STATS_PAGE_OPENING_HAND)
    opening_hand_base = _refresh_default_snapshot_from_prepared(0, STATS_PAGE_OPENING_HAND)
    endgames_mw = _refresh_default_snapshot_from_prepared(1, STATS_PAGE_ENDGAMES)
    endgames_base = _refresh_default_snapshot_from_prepared(0, STATS_PAGE_ENDGAMES)
    endgames_cp_distribution_mw = _refresh_default_snapshot_from_prepared(
        1, STATS_PAGE_ENDGAMES, ENDGAMES_VIEW_CP_DISTRIBUTION
    )
    endgames_cp_distribution_base = _refresh_default_snapshot_from_prepared(
        0, STATS_PAGE_ENDGAMES, ENDGAMES_VIEW_CP_DISTRIBUTION
    )
    endgames_cp_by_map_mw = _refresh_default_snapshot_from_prepared(
        1, STATS_PAGE_ENDGAMES, ENDGAMES_VIEW_CP_BY_MAP
    )
    endgames_cp_by_map_base = _refresh_default_snapshot_from_prepared(
        0, STATS_PAGE_ENDGAMES, ENDGAMES_VIEW_CP_BY_MAP
    )
    maps_metrics_mw = _refresh_default_snapshot_from_prepared(1, STATS_PAGE_MAPS)
    maps_metrics_base = _refresh_default_snapshot_from_prepared(0, STATS_PAGE_MAPS)
    maps_h2h_mw = _refresh_default_snapshot_from_prepared(
        1, STATS_PAGE_MAPS, maps_view=MAPS_VIEW_TOURNAMENT_H2H
    )
    maps_h2h_base = _refresh_default_snapshot_from_prepared(
        0, STATS_PAGE_MAPS, maps_view=MAPS_VIEW_TOURNAMENT_H2H
    )
    sponsor_endgames_cp_mw = _refresh_default_snapshot_from_prepared(
        1, STATS_PAGE_SPONSOR_ENDGAMES, sponsor_endgames_view=SPONSOR_ENDGAMES_VIEW_CP
    )
    sponsor_endgames_cp_base = _refresh_default_snapshot_from_prepared(
        0, STATS_PAGE_SPONSOR_ENDGAMES, sponsor_endgames_view=SPONSOR_ENDGAMES_VIEW_CP
    )
    sponsor_endgames_appeal_mw = _refresh_default_snapshot_from_prepared(
        1, STATS_PAGE_SPONSOR_ENDGAMES, sponsor_endgames_view=SPONSOR_ENDGAMES_VIEW_APPEAL
    )
    sponsor_endgames_appeal_base = _refresh_default_snapshot_from_prepared(
        0, STATS_PAGE_SPONSOR_ENDGAMES, sponsor_endgames_view=SPONSOR_ENDGAMES_VIEW_APPEAL
    )
    combinations_card_card_mw = _refresh_default_snapshot_from_prepared(
        1, STATS_PAGE_COMBINATIONS, combinations_view=COMBINATIONS_VIEW_CARD_CARD
    )
    combinations_card_card_base = _refresh_default_snapshot_from_prepared(
        0, STATS_PAGE_COMBINATIONS, combinations_view=COMBINATIONS_VIEW_CARD_CARD
    )
    combinations_card_round_mw = _refresh_default_snapshot_from_prepared(
        1, STATS_PAGE_COMBINATIONS, combinations_view=COMBINATIONS_VIEW_CARD_ROUND
    )
    combinations_card_round_base = _refresh_default_snapshot_from_prepared(
        0, STATS_PAGE_COMBINATIONS, combinations_view=COMBINATIONS_VIEW_CARD_ROUND
    )
    combinations_card_map_mw = _refresh_default_snapshot_from_prepared(
        1, STATS_PAGE_COMBINATIONS, combinations_view=COMBINATIONS_VIEW_CARD_MAP
    )
    combinations_card_map_base = _refresh_default_snapshot_from_prepared(
        0, STATS_PAGE_COMBINATIONS, combinations_view=COMBINATIONS_VIEW_CARD_MAP
    )
    snapshots = [
        home_mw, home_base, mw, base, opening_hand_mw, opening_hand_base, endgames_mw, endgames_base,
        endgames_cp_distribution_mw, endgames_cp_distribution_base,
        endgames_cp_by_map_mw, endgames_cp_by_map_base, maps_metrics_mw, maps_metrics_base,
        maps_h2h_mw, maps_h2h_base, sponsor_endgames_cp_mw, sponsor_endgames_cp_base,
        sponsor_endgames_appeal_mw, sponsor_endgames_appeal_base,
        combinations_card_card_mw, combinations_card_card_base,
        combinations_card_round_mw, combinations_card_round_base,
        combinations_card_map_mw, combinations_card_map_base,
    ]
    status = (
        "ok"
        if data_version and home_bootstrap and all(item["status"] == "ok" for item in snapshots)
        else "error"
    )
    return {
        "status": status,
        "total_ms": _ms_since(started_at),
        "data_version": data_version,
        "prepared": prepared,
        "home_mw": home_mw,
        "home_base": home_base,
        "home_bootstrap": "ok" if home_bootstrap else "error",
        "mw": mw,
        "base": base,
        "opening_hand_mw": opening_hand_mw,
        "opening_hand_base": opening_hand_base,
        "endgames_mw": endgames_mw,
        "endgames_base": endgames_base,
        "endgames_cp_distribution_mw": endgames_cp_distribution_mw,
        "endgames_cp_distribution_base": endgames_cp_distribution_base,
        "endgames_cp_by_map_mw": endgames_cp_by_map_mw,
        "endgames_cp_by_map_base": endgames_cp_by_map_base,
        "maps_metrics_mw": maps_metrics_mw,
        "maps_metrics_base": maps_metrics_base,
        "maps_h2h_mw": maps_h2h_mw,
        "maps_h2h_base": maps_h2h_base,
        "sponsor_endgames_cp_mw": sponsor_endgames_cp_mw,
        "sponsor_endgames_cp_base": sponsor_endgames_cp_base,
        "sponsor_endgames_appeal_mw": sponsor_endgames_appeal_mw,
        "sponsor_endgames_appeal_base": sponsor_endgames_appeal_base,
        "combinations_card_card_mw": combinations_card_card_mw,
        "combinations_card_card_base": combinations_card_card_base,
        "combinations_card_round_mw": combinations_card_round_mw,
        "combinations_card_round_base": combinations_card_round_base,
        "combinations_card_map_mw": combinations_card_map_mw,
        "combinations_card_map_base": combinations_card_map_base,
    }


@functions_framework.http
def get_card_stats(request):
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-Ark-Nova-Maintenance-Token",
        "Content-Type": "application/json",
    }

    if request.method == "OPTIONS":
        return ("", 204, headers)

    request_started_at = time.perf_counter()
    params = request.get_json(silent=True) or {}
    refresh_data = params.get("refresh_data") is True
    debug_timing = params.get("debug") is True
    maintenance_requested = (
        refresh_data
        or debug_timing
        or params.get("refresh_prepared") is True
        or params.get("daily_refresh") is True
    )

    if maintenance_requested and not _has_maintenance_auth(request):
        return _maintenance_auth_error(headers)

    if params.get("refresh_prepared") is True:
        try:
            payload = _refresh_prepared_tables()
            payload["data_version"] = _write_data_version(payload)
            status_code = 200 if payload["data_version"] else 500
            return (json.dumps(payload), status_code, headers)
        except Exception as exc:
            logging.exception("Failed to refresh prepared tables")
            return (json.dumps({"status": "error", "message": str(exc)}), 500, headers)

    if params.get("daily_refresh") is True:
        try:
            payload = _run_daily_refresh()
            status_code = 200 if payload.get("status") == "ok" else 500
            return (json.dumps(payload), status_code, headers)
        except Exception as exc:
            logging.exception("Failed to run daily refresh")
            return (json.dumps({"status": "error", "message": str(exc)}), 500, headers)

    try:
        stats_page = _parse_stats_page(params.get("stats_page", params.get("page", STATS_PAGE_CARDS)))
        endgames_view = (
            _parse_endgames_view(params.get("endgames_view"))
            if stats_page == STATS_PAGE_ENDGAMES
            else ENDGAMES_VIEW_GENERAL
        )
        maps_view = (
            _parse_maps_view(params.get("maps_view"))
            if stats_page == STATS_PAGE_MAPS
            else MAPS_VIEW_METRICS
        )
        sponsor_endgames_view = (
            _parse_sponsor_endgames_view(params.get("sponsor_endgames_view"))
            if stats_page == STATS_PAGE_SPONSOR_ENDGAMES
            else SPONSOR_ENDGAMES_VIEW_CP
        )
        combinations_view = (
            _parse_combinations_view(params.get("combinations_view"))
            if stats_page == STATS_PAGE_COMBINATIONS
            else COMBINATIONS_VIEW_CARD_CARD
        )
        is_mw = _parse_is_mw(params.get("is_mw", 1))
        default_elo_min = None if stats_page == STATS_PAGE_HOME else 300
        player_elo_min = _parse_int_param(
            params.get("player_elo_min", default_elo_min), "player_elo_min", default_elo_min
        )
        player_elo_max = _parse_int_param(params.get("player_elo_max"), "player_elo_max")
        opponent_elo_min = _parse_int_param(
            params.get("opponent_elo_min", default_elo_min), "opponent_elo_min", default_elo_min
        )
        opponent_elo_max = _parse_int_param(params.get("opponent_elo_max"), "opponent_elo_max")
        default_date_from = (
            None
            if stats_page == STATS_PAGE_HOME
            else MAPS_METRICS_DEFAULT_DATE_FROM
            if stats_page == STATS_PAGE_MAPS and maps_view == MAPS_VIEW_METRICS
            else DEFAULT_DATE_FROM
        )
        date_from = _parse_iso_date(
            params.get("date_from", default_date_from.isoformat() if default_date_from else None),
            "date_from",
            default_date_from,
        )
        date_to = _parse_iso_date(params.get("date_to"), "date_to")
        if date_from and date_to and date_from > date_to:
            raise ValueError("date_from must be on or before date_to")
        raw_end_game_triggered = params["end_game_triggered"] if "end_game_triggered" in params else None
        end_game_triggered = _parse_optional_bool(raw_end_game_triggered, "end_game_triggered")
    except ValueError as exc:
        return (json.dumps({"status": "error", "message": str(exc)}), 400, headers)

    allowed_maps = ALL_KNOWN_MAPS if stats_page == STATS_PAGE_HOME else VALID_MAPS
    selected_maps = params.get("maps", allowed_maps)
    if not isinstance(selected_maps, list):
        selected_maps = allowed_maps
    selected_maps = [m for m in selected_maps if m in allowed_maps]
    if not selected_maps and stats_page != STATS_PAGE_HOME:
        selected_maps = VALID_MAPS
    if stats_page == STATS_PAGE_ENDGAMES and endgames_view == ENDGAMES_VIEW_CP_BY_MAP:
        selected_maps = VALID_MAPS
    if stats_page == STATS_PAGE_MAPS:
        selected_maps = VALID_MAPS

    card_types = _parse_card_types(params.get("card_types", DEFAULT_CARD_TYPES))
    selected_rounds, round_filter_active = _parse_round_filter(params.get("rounds"))
    if stats_page in (
        STATS_PAGE_HOME,
        STATS_PAGE_OPENING_HAND,
        STATS_PAGE_ENDGAMES,
        STATS_PAGE_MAPS,
        STATS_PAGE_SPONSOR_ENDGAMES,
    ):
        selected_rounds, round_filter_active = [], False
    if stats_page == STATS_PAGE_COMBINATIONS and combinations_view == COMBINATIONS_VIEW_CARD_ROUND:
        selected_rounds, round_filter_active = [], False
    if stats_page in (STATS_PAGE_ENDGAMES, STATS_PAGE_MAPS, STATS_PAGE_SPONSOR_ENDGAMES):
        end_game_triggered = None
    if stats_page == STATS_PAGE_MAPS and maps_view == MAPS_VIEW_TOURNAMENT_H2H:
        player_elo_min = 300
        player_elo_max = None
        opponent_elo_min = 300
        opponent_elo_max = None
        date_from = DEFAULT_DATE_FROM
        date_to = None

    cacheable_default_request = _is_default_cache_request(
        stats_page,
        maps_view,
        is_mw,
        selected_maps,
        player_elo_min,
        player_elo_max,
        opponent_elo_min,
        opponent_elo_max,
        date_from,
        date_to,
        end_game_triggered,
        round_filter_active,
    )

    if cacheable_default_request and not refresh_data:
        cached_payload = _read_cached_snapshot(
            is_mw, stats_page, endgames_view, maps_view,
            sponsor_endgames_view, combinations_view
        )
        if cached_payload:
            return (json.dumps(cached_payload), 200, headers)

    data_version = _read_data_version()
    filter_cache_blob_name = None
    if (
        CACHE_BUCKET
        and stats_page not in (STATS_PAGE_ENDGAMES, STATS_PAGE_SPONSOR_ENDGAMES)
        and not cacheable_default_request
        and not refresh_data
        and not debug_timing
    ):
        filter_cache_blob_name = _filter_cache_blob_name(
            stats_page,
            is_mw,
            selected_maps,
            card_types,
            selected_rounds,
            round_filter_active,
            player_elo_min,
            player_elo_max,
            opponent_elo_min,
            opponent_elo_max,
            date_from,
            date_to,
            end_game_triggered,
            data_version,
            combinations_view if stats_page == STATS_PAGE_COMBINATIONS else None,
        )
        cached_payload = _read_cache_blob(filter_cache_blob_name, "filter_hit")
        if cached_payload:
            return (json.dumps(cached_payload), 200, headers)

    try:
        rows, timing = _query_card_stats(
            is_mw,
            selected_maps,
            card_types,
            selected_rounds,
            round_filter_active,
            stats_page,
            player_elo_min,
            player_elo_max,
            opponent_elo_min,
            opponent_elo_max,
            date_from,
            date_to,
            end_game_triggered,
            endgames_view=endgames_view,
            maps_view=maps_view,
            sponsor_endgames_view=sponsor_endgames_view,
            combinations_view=combinations_view,
            use_query_cache=(stats_page != STATS_PAGE_ENDGAMES and not debug_timing),
        )
        payload = {
            "status": "ok",
            "round_filter_active": round_filter_active,
            "stats_page": stats_page,
            "endgames_view": endgames_view if stats_page == STATS_PAGE_ENDGAMES else None,
            "maps_view": maps_view if stats_page == STATS_PAGE_MAPS else None,
            "sponsor_endgames_view": (
                sponsor_endgames_view if stats_page == STATS_PAGE_SPONSOR_ENDGAMES else None
            ),
            "combinations_view": (
                combinations_view if stats_page == STATS_PAGE_COMBINATIONS else None
            ),
            "maps": ALL_MAPS_FOR_METRICS if stats_page == STATS_PAGE_MAPS else None,
            "data": rows,
            "cache_status": "live",
        }

        if cacheable_default_request:
            cache_write_ok = _write_cached_snapshot(
                is_mw, payload, stats_page, endgames_view, maps_view,
                sponsor_endgames_view, combinations_view
            )
            payload["cache_status"] = "refreshed" if refresh_data and cache_write_ok else "miss"
            if not cache_write_ok:
                payload["cache_status"] = "cache_write_failed"
        elif filter_cache_blob_name and not debug_timing:
            cache_write_ok = _write_cache_blob(filter_cache_blob_name, payload, "filter_refreshed")
            payload["cache_status"] = "filter_refreshed" if cache_write_ok else "filter_cache_write_failed"

        if debug_timing:
            timing["total_ms"] = _ms_since(request_started_at)
            payload["debug_timing"] = timing

        return (json.dumps(payload), 200, headers)

    except Exception as exc:
        logging.exception("Failed to query card stats")
        return (json.dumps({"status": "error", "message": str(exc)}), 500, headers)





