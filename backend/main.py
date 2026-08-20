import functions_framework
import csv
import copy
import gzip
import hashlib
import hmac
import io
import json
import logging
import math
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from collections import OrderedDict
from functools import lru_cache
from types import SimpleNamespace

from google.cloud import bigquery
from google.cloud import storage
from google.api_core.exceptions import PreconditionFailed


# Constants

DEFAULT_DATE_FROM = date(2025, 1, 1)
MAPS_METRICS_DEFAULT_DATE_FROM = date(2026, 1, 13)
DEFAULT_CARD_TYPES = ["animal", "sponsor", "project"]
VALID_CARD_TYPES = set(DEFAULT_CARD_TYPES)
COMBINATION_PAIR_TYPES = [
    "Animal + Animal", "Animal + Project", "Animal + Sponsor",
    "Project + Project", "Project + Sponsor", "Sponsor + Sponsor",
]
CARD_ACTION_PAIR_TYPES = [
    f"{card_type} + {action_type}"
    for card_type in ("Animal", "Project", "Sponsor")
    for action_type in ("Animals", "Association", "Build", "Cards", "Sponsors")
]

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
CARD_ATTRIBUTES_URL = os.environ.get(
    "CARD_ATTRIBUTES_URL",
    "https://raw.githubusercontent.com/emufriends/stats/main/docs/cards_attributes.csv",
)
CARD_ATTRIBUTES_LOCAL_PATH = os.path.join(os.path.dirname(__file__), "cards_attributes.csv")
CARD_ATTRIBUTES_CACHE_BLOB = f"{CACHE_PREFIX}/metadata/cards-attributes.json"
MERGE_PLAYERS_URL = os.environ.get(
    "MERGE_PLAYERS_URL",
    "https://raw.githubusercontent.com/emufriends/stats/main/docs/merge_players.csv",
)
MERGE_PLAYERS_LOCAL_PATH = os.path.join(os.path.dirname(__file__), "merge_players.csv")
MERGE_PLAYERS_CACHE_BLOB = f"{CACHE_PREFIX}/metadata/merge-players.json"
ARENA_SOURCE_BASE_URL = os.environ.get(
    "ARENA_SOURCE_BASE_URL",
    "https://raw.githubusercontent.com/emufriends/stats/main/docs/arena",
).rstrip("/")
ARENA_END_GRACE = timedelta(hours=2)
ARENA_LOCAL_DIR = os.environ.get(
    "ARENA_LOCAL_DIR", os.path.join(os.path.dirname(__file__), "arena")
)
ARENA_METADATA_CACHE_BLOB = f"{CACHE_PREFIX}/metadata/arena-source.json"
ARENA_MANIFEST_BLOB = f"{CACHE_PREFIX}/players/arena/manifest.json"
ARENA_TOP100_BUNDLE_BLOB = f"{CACHE_PREFIX}/players/arena-top-100/all-seasons.json"
RECORDS_FASTEST_SHEET_URL = os.environ.get(
    "RECORDS_FASTEST_SHEET_URL",
    "https://docs.google.com/spreadsheets/d/1RSOjQdZcGmOY7PBsDY7erGz--dtPJLc3ydNArr9bV48/export?format=csv&gid=1836311698",
)
RECORDS_BIGGEST_TURNS_SHEET_URL = os.environ.get(
    "RECORDS_BIGGEST_TURNS_SHEET_URL",
    "https://docs.google.com/spreadsheets/d/1SfWmRUo3c2jHbezJDVwXxi3zqEm5RdiZxp4hbHfEl0Q/export?format=csv",
)
RECORDS_ELO_LEADERBOARD_SHEET_URL = os.environ.get(
    "RECORDS_ELO_LEADERBOARD_SHEET_URL",
    "https://docs.google.com/spreadsheets/d/1NG3FPP70riMzhHPJ6Suz30bhJxUocFd_rKDKxn0kZbM/export?format=csv&sheet=Masters",
)
RECORDS_MANUAL_CACHE_BLOB = f"{CACHE_PREFIX}/metadata/records-manual-source.json"
RECORDS_ELO_LEADERBOARD_CACHE_BLOB = f"{CACHE_PREFIX}/metadata/records-elo-leaderboard-source.json"
FILTER_CACHE_VERSION = "v38-starting-position-orientation"
DEFAULT_PACK_SCHEMA_VERSION = 18
PLAYERS_HISTORY_WINDOW = 100
PLAYERS_GRAPH_MIN_GAMES = 250
STATS_PAGE_CARDS = "cards"
STATS_PAGE_HOME = "home"
STATS_PAGE_OPENING_HAND = "opening_hand"
STATS_PAGE_ENDGAMES = "endgames"
STATS_PAGE_MAPS = "maps"
STATS_PAGE_SPONSOR_ENDGAMES = "sponsor_endgames"
STATS_PAGE_COMBINATIONS = "combinations"
STATS_PAGE_ICONS = "icons"
STATS_PAGE_BUILD = "build"
STATS_PAGE_PREDICTORS = "predictors"
STATS_PAGE_ACTIONS = "actions"
STATS_PAGE_CONSERVATION = "conservation"
STATS_PAGE_SCORING = "scoring"
STATS_PAGE_WORKERS = "workers"
STATS_PAGE_PLAYERS = "players"
STATS_PAGE_ARENA = "arena"
STATS_PAGE_RECORDS = "records"
STATS_PAGE_MW_ACTION_CARDS = "mw_action_cards"
VALID_STATS_PAGES = {
    STATS_PAGE_CARDS,
    STATS_PAGE_HOME,
    STATS_PAGE_OPENING_HAND,
    STATS_PAGE_ENDGAMES,
    STATS_PAGE_MAPS,
    STATS_PAGE_SPONSOR_ENDGAMES,
    STATS_PAGE_COMBINATIONS,
    STATS_PAGE_ICONS,
    STATS_PAGE_BUILD,
    STATS_PAGE_PREDICTORS,
    STATS_PAGE_ACTIONS,
    STATS_PAGE_CONSERVATION,
    STATS_PAGE_SCORING,
    STATS_PAGE_WORKERS,
    STATS_PAGE_PLAYERS,
    STATS_PAGE_ARENA,
    STATS_PAGE_RECORDS,
    STATS_PAGE_MW_ACTION_CARDS,
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
BUILD_VIEW_ENCLOSURES = "enclosures"
BUILD_VIEW_HEXES = "hexes"
VALID_BUILD_VIEWS = {BUILD_VIEW_ENCLOSURES, BUILD_VIEW_HEXES}
PREDICTORS_VIEW_GENERAL = "general"
PREDICTORS_VIEW_ICON = "icon"
PREDICTORS_VIEW_SPECIFIC = "specific"
VALID_PREDICTORS_VIEWS = {
    PREDICTORS_VIEW_GENERAL,
    PREDICTORS_VIEW_ICON,
    PREDICTORS_VIEW_SPECIFIC,
}
ACTIONS_VIEW_STARTING_POSITION = "starting_position"
ACTIONS_VIEW_UPGRADES = "upgrades"
ACTIONS_VIEW_UPGRADE_ORDER = "upgrade_order"
ACTIONS_VIEW_UPGRADES_BY_MAP = "upgrades_by_map"
VALID_ACTIONS_VIEWS = {
    ACTIONS_VIEW_STARTING_POSITION,
    ACTIONS_VIEW_UPGRADES,
    ACTIONS_VIEW_UPGRADE_ORDER,
    ACTIONS_VIEW_UPGRADES_BY_MAP,
}
CONSERVATION_VIEW_PROJECTS = "projects"
CONSERVATION_VIEW_PROJECT_REWARDS = "project_rewards"
CONSERVATION_VIEW_CP_REWARDS = "cp_rewards"
VALID_CONSERVATION_VIEWS = {
    CONSERVATION_VIEW_PROJECTS,
    CONSERVATION_VIEW_PROJECT_REWARDS,
    CONSERVATION_VIEW_CP_REWARDS,
}
SCORING_VIEW_FINAL_SCORE = "final_score"
SCORING_VIEW_APPEAL = "appeal"
SCORING_VIEW_CONSERVATION_POINTS = "conservation_points"
SCORING_VIEW_REPUTATION = "reputation"
VALID_SCORING_VIEWS = {
    SCORING_VIEW_FINAL_SCORE,
    SCORING_VIEW_APPEAL,
    SCORING_VIEW_CONSERVATION_POINTS,
    SCORING_VIEW_REPUTATION,
}
WORKERS_VIEW_GENERAL = "general"
WORKERS_VIEW_TWO_CP_WORKER = "two_cp_worker"
VALID_WORKERS_VIEWS = {WORKERS_VIEW_GENERAL, WORKERS_VIEW_TWO_CP_WORKER}
PLAYERS_VIEW_GENERAL = "general"
PLAYERS_VIEW_ARENA_TOP_100 = "arena_top_100"
PLAYERS_VIEW_COMPARISON = "comparison"
PLAYERS_VIEW_PERFORMANCE_BY_MAP = "performance_by_map"
VALID_PLAYERS_VIEWS = {
    PLAYERS_VIEW_GENERAL,
    PLAYERS_VIEW_ARENA_TOP_100,
    PLAYERS_VIEW_COMPARISON,
    PLAYERS_VIEW_PERFORMANCE_BY_MAP,
}
ARENA_VIEW_TOP_100 = "top_100"
VALID_ARENA_VIEWS = {ARENA_VIEW_TOP_100}
RECORDS_VIEW_ELO_LEADERBOARD = "elo_leaderboard"
RECORDS_VIEW_FASTEST_GAMES = "fastest_games"
RECORDS_VIEW_HIGHEST_SCORES = "highest_scores"
RECORDS_VIEW_BIGGEST_TURNS = "biggest_turns"
RECORDS_VIEW_MOST_ICONS = "most_icons"
VALID_RECORDS_VIEWS = {
    RECORDS_VIEW_ELO_LEADERBOARD,
    RECORDS_VIEW_FASTEST_GAMES,
    RECORDS_VIEW_HIGHEST_SCORES,
    RECORDS_VIEW_BIGGEST_TURNS,
    RECORDS_VIEW_MOST_ICONS,
}
MW_ACTION_CARDS_VIEW_GENERAL = "general"
MW_ACTION_CARDS_VIEW_DRAFT = "draft"
MW_ACTION_CARDS_VIEW_BY_MAP = "by_map"
MW_ACTION_CARDS_VIEW_SYNERGIES = "synergies"
VALID_MW_ACTION_CARDS_VIEWS = {
    MW_ACTION_CARDS_VIEW_GENERAL,
    MW_ACTION_CARDS_VIEW_DRAFT,
    MW_ACTION_CARDS_VIEW_BY_MAP,
    MW_ACTION_CARDS_VIEW_SYNERGIES,
}
# Marine Worlds replaces two of a player's five normal action cards with
# enhanced variants. Draft telemetry uses canonical backend keys such as
# ``Sponsors 1``; selected-card fields store only the numeric suffix. This
# catalog is the single mapping from those backend identifiers to the
# colloquial names displayed by the frontend (for example Sponsors 1 -> Trade).
MW_ACTION_CARD_CATALOG = (
    (1, "Animals", 1, "Ignore"),
    (2, "Animals", 2, "Hunter"),
    (3, "Animals", 3, "Appeal"),
    (4, "Animals", 4, "Mark"),
    (5, "Association", 1, "Duplicate"),
    (6, "Association", 2, "Hire"),
    (7, "Association", 3, "X-token"),
    (8, "Association", 4, "Determination"),
    (9, "Build", 1, "Pavilion"),
    (10, "Build", 2, "Kiosk"),
    (11, "Build", 3, "+1"),
    (12, "Build", 4, "Terrain"),
    (13, "Cards", 1, "Keep"),
    (14, "Cards", 2, "Digging"),
    (15, "Cards", 3, "Snap"),
    (16, "Cards", 4, "Clever"),
    (17, "Sponsors", 1, "Trade"),
    (18, "Sponsors", 2, "Money"),
    (19, "Sponsors", 3, "Sunbathing"),
    (20, "Sponsors", 4, "Marketing"),
)

# FIDE Rating Regulations table 8.1.1. Index is score percentage 0..100;
# Top 100 performance rating is average opponent Elo plus this difference.
FIDE_PERFORMANCE_DP = (
    -800, -677, -589, -538, -501, -470, -444, -422, -401, -383,
    -366, -351, -336, -322, -309, -296, -284, -273, -262, -251,
    -240, -230, -220, -211, -202, -193, -184, -175, -166, -158,
    -149, -141, -133, -125, -117, -110, -102, -95, -87, -80,
    -72, -65, -57, -50, -43, -36, -29, -21, -14, -7, 0,
    7, 14, 21, 29, 36, 43, 50, 57, 65, 72,
    80, 87, 95, 102, 110, 117, 125, 133, 141, 149,
    158, 166, 175, 184, 193, 202, 211, 220, 230, 240,
    251, 262, 273, 284, 296, 309, 322, 336, 351, 366,
    383, 401, 422, 444, 470, 501, 538, 589, 677, 800,
)

# Fixed reward catalogs make unavailable choices explicit instead of silently
# dropping rows. The first six project rewards are generic; each remaining
# reward is only meaningful on its associated map.
PROJECT_REWARD_CONFIG = [
    (1, "Snapping", "Snapping", None, "generic"),
    (2, "2-size", "2-size", None, "generic"),
    (3, "5 money", "5 Money", None, "generic"),
    (4, "Worker", "Worker", None, "generic"),
    (5, "12 money", "12 Money", None, "generic"),
    (6, "3 X-tokens", "3 X Token", None, "generic"),
    (7, "Marketing (1a)", "Marketing", VALID_MAPS[0], "map"),
    (8, "1 CP (2a)", "1 CP", VALID_MAPS[1], "map"),
    (9, "Determination (3a)", "Determination", VALID_MAPS[2], "map"),
    (10, "University (4a)", "University", VALID_MAPS[3], "map"),
    (11, "Unique building (5a)", "Aviary/Reptile House", VALID_MAPS[4], "map"),
    (12, "Clever (6a)", "Clever", VALID_MAPS[5], "map"),
    (13, "Pouching (7a)", "Pouching", VALID_MAPS[6], "map"),
    (14, "Partner zoo (8a)", "Partner Zoo", VALID_MAPS[7], "map"),
    (15, "Token (9)", "Remove Continent Cube", VALID_MAPS[8], "map"),
    (16, "2 reputation (10)", "2 Reputation", VALID_MAPS[9], "map"),
    (17, "Upgrade (11)", "Upgrade", VALID_MAPS[10], "map"),
    (18, "Animal magnet (12)", "Animal Magnet", VALID_MAPS[11], "map"),
    (19, "Adapt (13)", "Adapt 3", VALID_MAPS[12], "map"),
    (20, "Person sponsor (14)", "Play a person sponsor", VALID_MAPS[13], "map"),
    (21, "Draw + ability (T1)", "Draw from range", VALID_MAPS[14], "map"),
    (22, "3 reputation (T1)", "3 Reputation", VALID_MAPS[14], "map"),
]

CP_REWARD_CONFIG = [
    (1, "University", "1 University", False),
    (2, "Partner zoo", "1 Partner-Zoo", False),
    (3, "Posturing 3", "3 bonus-kiosk-pavilion", True),
    (4, "x2", "1 Multiplier", False),
    (5, "10 money", "10 money", False),
    (6, "2 reputation", "2 reputation", False),
    (7, "3 X-tokens", "3 xtoken", False),
    (8, "3-size", "1 size-3", False),
    (9, "Marketing", "1 bonus-sponsor-gray", False),
    (10, "Extra Shift", "1 bonus-extra-shift", True),
    (11, "Bonus icon", "1 bonus-icon", True),
    (12, "3 cards", "3 take-in-range-or-deck", False),
    (13, "Snap + Handsize", "1 bonus-increased-hand", True),
    (14, "Ignore 3", "3 bonus-ignore-conditions", True),
    (15, "Adapt 3", "3 bonus-scoring-cards", True),
    (16, "5 money", "5 money", False),
]
COMBINATIONS_VIEW_CARD_CARD = "card_card"
COMBINATIONS_VIEW_CARD_MAP = "card_map"
COMBINATIONS_VIEW_CARD_ROUND = "card_round"
COMBINATIONS_VIEW_CARD_ENDGAME = "card_endgame"
COMBINATIONS_VIEW_CARD_ACTION_CARD = "card_action_card"
VALID_COMBINATIONS_VIEWS = {
    COMBINATIONS_VIEW_CARD_CARD,
    COMBINATIONS_VIEW_CARD_MAP,
    COMBINATIONS_VIEW_CARD_ROUND,
    COMBINATIONS_VIEW_CARD_ENDGAME,
    COMBINATIONS_VIEW_CARD_ACTION_CARD,
}
COMBINATION_DEFAULT_MIN_PLAYS = 1000
COMBINATION_PAGE_DEFAULT = 1
COMBINATION_PAGE_SIZE_DEFAULT = 50
COMBINATION_PAGE_SIZES = {25, 50, 100}
COMBINATION_SORT_FIELDS = {
    COMBINATIONS_VIEW_CARD_CARD: {
        "card_1", "card_2", "delta_combined", "delta_actual",
        "interaction", "avg_elo", "n_played", "pair_type",
    },
    COMBINATIONS_VIEW_CARD_MAP: {
        "card_name", "map_name", "delta_general", "delta_map",
        "interaction", "avg_elo", "n_played", "card_type",
    },
    COMBINATIONS_VIEW_CARD_ROUND: {
        "card_name", "round_name", "delta_general", "delta_round",
        "interaction", "avg_elo", "n_played", "card_type",
    },
    COMBINATIONS_VIEW_CARD_ENDGAME: {
        "card_name", "endgame_name", "delta_combined", "delta_actual",
        "interaction", "avg_elo", "n_played", "card_type",
    },
    COMBINATIONS_VIEW_CARD_ACTION_CARD: {
        "card_name", "action_card_name", "delta_combined", "delta_actual",
        "interaction", "avg_elo", "n_played", "pair_type",
    },
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
# Home is intentionally all-map: its filter bar exposes every configured map,
# including legacy Maps 1-8 and beginner Maps A/0. Analytical pages continue to
# use VALID_MAPS unless they explicitly opt into another map population.
LEGACY_MAPS = [
    item["full"] for item in ALL_MAPS_FOR_METRICS
    if item["code"] in {"1", "2", "3", "4", "5", "6", "7", "8"}
]
# Records displays the original eight maps by default, but its complete daily
# snapshots include every known map so browser-side filters can reveal beginner
# maps without querying BigQuery.
RECORDS_DEFAULT_MAPS = VALID_MAPS + LEGACY_MAPS

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
REFRESH_PAGE_PASSWORD = os.environ.get("REFRESH_PAGE_PASSWORD")
REFRESH_STATUS_BLOB = f"{CACHE_PREFIX}/refresh/status.json"
REFRESH_LOCK_BLOB = f"{CACHE_PREFIX}/refresh/lock.json"
REFRESH_LOCK_MAX_AGE = timedelta(minutes=90)
PREPARED_LOGS_TABLE = os.environ.get(
    "PREPARED_LOGS_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.card_logs_prepared",
)
PREPARED_FULL_STATS_TABLE = os.environ.get(
    "PREPARED_FULL_STATS_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.full_stats_prepared",
)
PREPARED_RECORDS_MANUAL_TABLE = os.environ.get(
    "PREPARED_RECORDS_MANUAL_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.records_manual_prepared",
)
PREPARED_PLAYERS_TABLE = os.environ.get(
    "PREPARED_PLAYERS_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.players_stats_prepared",
)
PREPARED_PLAYERS_RECENT_TABLE = os.environ.get(
    "PREPARED_PLAYERS_RECENT_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.players_recent_prepared",
)
PREPARED_PLAYERS_DEFAULT_TABLE = os.environ.get(
    "PREPARED_PLAYERS_DEFAULT_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.players_default_prepared",
)
PREPARED_PLAYERS_BASELINE_TABLE = os.environ.get(
    "PREPARED_PLAYERS_BASELINE_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.players_baseline_prepared",
)
PREPARED_PLAYERS_IDENTITY_ROLLUP_TABLE = os.environ.get(
    "PREPARED_PLAYERS_IDENTITY_ROLLUP_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.players_identity_daily_rollup",
)
PREPARED_PLAYERS_MAP_ROLLUP_TABLE = os.environ.get(
    "PREPARED_PLAYERS_MAP_ROLLUP_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.players_map_performance_rollup",
)
PREPARED_CARD_PLAYS_TABLE = os.environ.get(
    "PREPARED_CARD_PLAYS_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.card_plays_prepared",
)
PREPARED_CARD_PAIRS_TABLE = os.environ.get(
    "PREPARED_CARD_PAIRS_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.card_pairs_prepared",
)
PREPARED_CARD_PLAY_AGGREGATES_TABLE = os.environ.get(
    "PREPARED_CARD_PLAY_AGGREGATES_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.card_play_daily_aggregates",
)
PREPARED_CARD_PAIR_AGGREGATES_TABLE = os.environ.get(
    "PREPARED_CARD_PAIR_AGGREGATES_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.card_pair_daily_aggregates",
)
PREPARED_CARD_PAIR_SCOPE_AGGREGATES_TABLE = os.environ.get(
    "PREPARED_CARD_PAIR_SCOPE_AGGREGATES_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.card_pair_scope_daily_aggregates",
)
PREPARED_HOME_OBSERVATIONS_TABLE = os.environ.get(
    "PREPARED_HOME_OBSERVATIONS_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.home_observations_prepared",
)
PREPARED_ENDGAME_EVENTS_TABLE = os.environ.get(
    "PREPARED_ENDGAME_EVENTS_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.endgame_events_prepared",
)
PREPARED_ACTION_STARTING_TABLE = os.environ.get(
    "PREPARED_ACTION_STARTING_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.action_starting_observations",
)
PREPARED_CONSERVATION_COUNTS_TABLE = os.environ.get(
    "PREPARED_CONSERVATION_COUNTS_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.conservation_count_observations",
)
PREPARED_PREDICTOR_SPECIFIC_TABLE = os.environ.get(
    "PREPARED_PREDICTOR_SPECIFIC_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.predictor_specific_observations",
)
PREPARED_CARD_MOMENTS_TABLE = os.environ.get(
    "PREPARED_CARD_MOMENTS_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.card_moment_observations",
)
PREPARED_SPONSOR_ENDGAME_TABLE = os.environ.get(
    "PREPARED_SPONSOR_ENDGAME_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.sponsor_endgame_observations",
)
PREPARED_PROJECT_REWARD_TABLE = os.environ.get(
    "PREPARED_PROJECT_REWARD_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.project_reward_observations",
)
PREPARED_CP_REWARD_TABLE = os.environ.get(
    "PREPARED_CP_REWARD_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.cp_reward_observations",
)
PREPARED_CARD_ENDGAME_TABLE = os.environ.get(
    "PREPARED_CARD_ENDGAME_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.card_endgame_observations",
)
PREPARED_CARD_ENDGAME_AGGREGATES_TABLE = os.environ.get(
    "PREPARED_CARD_ENDGAME_AGGREGATES_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.card_endgame_daily_aggregates",
)
PREPARED_MW_ACTION_CARD_PLAYERS_TABLE = os.environ.get(
    "PREPARED_MW_ACTION_CARD_PLAYERS_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.mw_action_card_player_observations",
)
PREPARED_MW_ACTION_CARD_DRAFTS_TABLE = os.environ.get(
    "PREPARED_MW_ACTION_CARD_DRAFTS_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.mw_action_card_draft_observations",
)
PREPARED_MW_ACTION_CARD_MAP_AGGREGATES_TABLE = os.environ.get(
    "PREPARED_MW_ACTION_CARD_MAP_AGGREGATES_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.mw_action_card_map_daily_aggregates",
)
PREPARED_MW_ACTION_CARD_SYNERGY_AGGREGATES_TABLE = os.environ.get(
    "PREPARED_MW_ACTION_CARD_SYNERGY_AGGREGATES_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.mw_action_card_synergy_daily_aggregates",
)
PREPARED_CARD_ACTION_CARD_TABLE = os.environ.get(
    "PREPARED_CARD_ACTION_CARD_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.card_action_card_observations",
)
PREPARED_CARD_ACTION_CARD_AGGREGATES_TABLE = os.environ.get(
    "PREPARED_CARD_ACTION_CARD_AGGREGATES_TABLE",
    "ark-nova-stats-dashboard.dashboard_cache.card_action_card_daily_aggregates",
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


def _beta_continued_fraction(a, b, x):
    """Numerical Recipes continued fraction for the incomplete beta function."""
    max_iterations = 200
    epsilon = 3e-14
    fp_min = 1e-300
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < fp_min:
        d = fp_min
    d = 1.0 / d
    result = d
    for iteration in range(1, max_iterations + 1):
        m2 = 2 * iteration
        aa = iteration * (b - iteration) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < fp_min:
            d = fp_min
        c = 1.0 + aa / c
        if abs(c) < fp_min:
            c = fp_min
        d = 1.0 / d
        result *= d * c

        aa = -(a + iteration) * (qab + iteration) * x / (
            (a + m2) * (qap + m2)
        )
        d = 1.0 + aa * d
        if abs(d) < fp_min:
            d = fp_min
        c = 1.0 + aa / c
        if abs(c) < fp_min:
            c = fp_min
        d = 1.0 / d
        delta = d * c
        result *= delta
        if abs(delta - 1.0) < epsilon:
            break
    return result


def _regularized_incomplete_beta(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    log_beta_term = (
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log1p(-x)
    )
    beta_term = math.exp(log_beta_term)
    if x < (a + 1.0) / (a + b + 2.0):
        return beta_term * _beta_continued_fraction(a, b, x) / a
    return 1.0 - beta_term * _beta_continued_fraction(b, a, 1.0 - x) / b


def _student_t_cdf(value, degrees_freedom):
    if value == 0:
        return 0.5
    x = degrees_freedom / (degrees_freedom + value * value)
    tail = 0.5 * _regularized_incomplete_beta(
        degrees_freedom / 2.0, 0.5, x
    )
    return 1.0 - tail if value > 0 else tail


@lru_cache(maxsize=200)
def _t_critical_95(degrees_freedom):
    """Two-sided 95% t critical value; normal limit above 200 df."""
    degrees_freedom = int(degrees_freedom)
    if degrees_freedom < 1:
        return None
    if degrees_freedom > 200:
        return 1.959963984540054
    low = 0.0
    high = 16.0
    for _ in range(70):
        midpoint = (low + high) / 2.0
        if _student_t_cdf(midpoint, degrees_freedom) < 0.975:
            low = midpoint
        else:
            high = midpoint
    return (low + high) / 2.0


def _ci95_fields(prefix, mean, sample_sd, observation_count):
    """Return public CI fields while keeping raw mean/SD internal."""
    try:
        count = int(observation_count or 0)
    except (TypeError, ValueError):
        count = 0
    result = {
        f"{prefix}_ci95_low": None,
        f"{prefix}_ci95_high": None,
        f"{prefix}_ci95_n": count,
    }
    if count < 2 or mean is None or sample_sd is None:
        return result
    try:
        mean_value = float(mean)
        sd_value = float(sample_sd)
    except (TypeError, ValueError):
        return result
    if not math.isfinite(mean_value) or not math.isfinite(sd_value) or sd_value < 0:
        return result
    critical = _t_critical_95(count - 1)
    margin = critical * sd_value / math.sqrt(count)
    result[f"{prefix}_ci95_low"] = round(mean_value - margin, 3)
    result[f"{prefix}_ci95_high"] = round(mean_value + margin, 3)
    return result


def _attach_ci95(item, row, schema_field_names, prefix):
    mean_field = f"{prefix}_ci_mean"
    sd_field = f"{prefix}_ci_sd"
    n_field = f"{prefix}_ci_n"
    if n_field not in schema_field_names:
        return
    item.update(_ci95_fields(
        prefix,
        getattr(row, mean_field, None),
        getattr(row, sd_field, None),
        getattr(row, n_field, None),
    ))


def _clustered_linear_ci(component_clusters, coefficients):
    """Pointwise CR1 interval for a linear combination of ratio means.

    ``component_clusters`` maps each component name to ``table_id -> (n, sum)``.
    The helper mirrors the production BigQuery calculation and exists as a
    small, deterministic regression-test surface for the covariance algebra.
    """
    means = {}
    totals = {}
    all_clusters = set()
    for component, coefficient in coefficients.items():
        observations = component_clusters.get(component) or {}
        total_n = sum(max(0, int(values[0] or 0)) for values in observations.values())
        total_sum = sum(float(values[1] or 0.0) for values in observations.values())
        if total_n <= 0:
            return {
                "interaction": None,
                "interaction_ci95_low": None,
                "interaction_ci95_high": None,
                "interaction_ci95_se": None,
                "interaction_ci95_cluster_n": 0,
                "interaction_ci95_method": "table_cluster_delta",
            }
        totals[component] = total_n
        means[component] = total_sum / total_n
        all_clusters.update(observations)

    cluster_count = len(all_clusters)
    point = sum(coefficients[name] * means[name] for name in coefficients)
    if cluster_count < 2:
        return {
            "interaction": point,
            "interaction_ci95_low": None,
            "interaction_ci95_high": None,
            "interaction_ci95_se": None,
            "interaction_ci95_cluster_n": cluster_count,
            "interaction_ci95_method": "table_cluster_delta",
        }

    squared_influence = 0.0
    for table_id in all_clusters:
        influence = 0.0
        for component, coefficient in coefficients.items():
            count, total = (component_clusters.get(component) or {}).get(
                table_id, (0, 0.0)
            )
            influence += coefficient * (
                float(total or 0.0) - int(count or 0) * means[component]
            ) / totals[component]
        squared_influence += influence * influence
    standard_error = math.sqrt(
        cluster_count / (cluster_count - 1) * squared_influence
    )
    margin = 1.96 * standard_error
    return {
        "interaction": point,
        "interaction_ci95_low": point - margin,
        "interaction_ci95_high": point + margin,
        "interaction_ci95_se": standard_error,
        "interaction_ci95_cluster_n": cluster_count,
        "interaction_ci95_method": "table_cluster_delta",
    }


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


def _parse_combination_list(raw_value, field_name, allowed, default):
    if raw_value is None:
        return list(default)
    if not isinstance(raw_value, list):
        raise ValueError(f"{field_name} must be an array")
    invalid = [value for value in raw_value if value not in allowed]
    if invalid:
        raise ValueError(f"{field_name} contains unsupported values")
    return list(dict.fromkeys(raw_value))


def _parse_stats_page(raw_value):
    if raw_value in (None, ""):
        return STATS_PAGE_CARDS
    value = str(raw_value).strip().lower().replace("-", "_")
    if value not in VALID_STATS_PAGES:
        raise ValueError(
            "stats_page must be cards, home, opening_hand, endgames, maps, "
            "sponsor_endgames, combinations, icons, build, predictors, actions, conservation, scoring, workers, players, arena, records, or mw_action_cards"
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
        raise ValueError(
            "combinations_view must be card_card, card_map, card_round, card_endgame, or card_action_card"
        )
    return value


def _parse_build_view(raw_value):
    if raw_value in (None, ""):
        return BUILD_VIEW_ENCLOSURES
    value = str(raw_value).strip().lower().replace("-", "_")
    if value not in VALID_BUILD_VIEWS:
        raise ValueError("build_view must be enclosures or hexes")
    return value


def _parse_predictors_view(raw_value):
    if raw_value in (None, ""):
        return PREDICTORS_VIEW_GENERAL
    value = str(raw_value).strip().lower().replace("-", "_")
    if value not in VALID_PREDICTORS_VIEWS:
        raise ValueError("predictors_view must be general, icon, or specific")
    return value


def _parse_actions_view(raw_value):
    if raw_value in (None, ""):
        return ACTIONS_VIEW_STARTING_POSITION
    value = str(raw_value).strip().lower().replace("-", "_")
    if value not in VALID_ACTIONS_VIEWS:
        raise ValueError("actions_view must be starting_position, upgrades, upgrade_order, or upgrades_by_map")
    return value


def _parse_conservation_view(raw_value):
    if raw_value in (None, ""):
        return CONSERVATION_VIEW_PROJECTS
    value = str(raw_value).strip().lower().replace("-", "_")
    if value not in VALID_CONSERVATION_VIEWS:
        raise ValueError("conservation_view must be projects, project_rewards, or cp_rewards")
    return value


def _parse_scoring_view(raw_value):
    if raw_value in (None, ""):
        return SCORING_VIEW_FINAL_SCORE
    value = str(raw_value).strip().lower().replace("-", "_")
    if value not in VALID_SCORING_VIEWS:
        raise ValueError(
            "scoring_view must be final_score, appeal, conservation_points, or reputation"
        )
    return value


def _parse_workers_view(raw_value):
    if raw_value in (None, ""):
        return WORKERS_VIEW_GENERAL
    value = str(raw_value).strip().lower().replace("-", "_")
    if value not in VALID_WORKERS_VIEWS:
        raise ValueError("workers_view must be general or two_cp_worker")
    return value


def _parse_players_view(raw_value):
    if raw_value in (None, ""):
        return PLAYERS_VIEW_GENERAL
    value = str(raw_value).strip().lower().replace("-", "_")
    if value not in VALID_PLAYERS_VIEWS:
        raise ValueError(
            "players_view must be general, comparison, performance_by_map, or arena_top_100"
        )
    return value


def _parse_arena_view(raw_value):
    if raw_value in (None, ""):
        return ARENA_VIEW_TOP_100
    value = str(raw_value).strip().lower().replace("-", "_")
    if value not in VALID_ARENA_VIEWS:
        raise ValueError("arena_view must be top_100")
    return value


def _parse_records_view(raw_value):
    if raw_value in (None, ""):
        return RECORDS_VIEW_ELO_LEADERBOARD
    value = str(raw_value).strip().lower().replace("-", "_")
    if value not in VALID_RECORDS_VIEWS:
        raise ValueError(
            "records_view must be elo_leaderboard, fastest_games, highest_scores, "
            "biggest_turns, or most_icons"
        )
    return value


def _parse_mw_action_cards_view(raw_value):
    if raw_value in (None, ""):
        return MW_ACTION_CARDS_VIEW_GENERAL
    value = str(raw_value).strip().lower().replace("-", "_")
    if value not in VALID_MW_ACTION_CARDS_VIEWS:
        raise ValueError(
            "mw_action_cards_view must be general, draft, by_map, or synergies"
        )
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


def _has_refresh_page_auth(request):
    if not REFRESH_PAGE_PASSWORD:
        return False
    provided = request.headers.get("X-Ark-Nova-Refresh-Password", "")
    return hmac.compare_digest(provided, REFRESH_PAGE_PASSWORD)


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


def _refresh_page_auth_error(headers):
    if not REFRESH_PAGE_PASSWORD:
        return (
            json.dumps({
                "status": "error",
                "message": "Manual refresh is not configured",
            }),
            500,
            headers,
        )
    return (
        json.dumps({
            "status": "error",
            "message": "Invalid refresh password",
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
    build_view=BUILD_VIEW_ENCLOSURES,
    predictors_view=PREDICTORS_VIEW_GENERAL,
    actions_view=ACTIONS_VIEW_STARTING_POSITION,
    conservation_view=CONSERVATION_VIEW_PROJECTS,
    scoring_view=SCORING_VIEW_FINAL_SCORE,
    workers_view=WORKERS_VIEW_GENERAL,
    players_view=PLAYERS_VIEW_GENERAL,
    records_view=RECORDS_VIEW_ELO_LEADERBOARD,
    mw_action_cards_view=MW_ACTION_CARDS_VIEW_GENERAL,
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
    if stats_page == STATS_PAGE_ICONS:
        return f"{CACHE_PREFIX}/icons/default-{dataset}.json"
    if stats_page == STATS_PAGE_BUILD:
        return f"{CACHE_PREFIX}/build/{build_view}/delta/default-{dataset}.json"
    if stats_page == STATS_PAGE_PREDICTORS:
        return f"{CACHE_PREFIX}/predictors/{predictors_view}/default-{dataset}.json"
    if stats_page == STATS_PAGE_ACTIONS:
        return f"{CACHE_PREFIX}/actions/{actions_view}/delta/default-{dataset}.json"
    if stats_page == STATS_PAGE_CONSERVATION:
        view_slug = conservation_view.replace("_", "-")
        return f"{CACHE_PREFIX}/conservation/{view_slug}/default-{dataset}.json"
    if stats_page == STATS_PAGE_SCORING:
        view_slug = scoring_view.replace("_", "-")
        return f"{CACHE_PREFIX}/scoring/{view_slug}/default-{dataset}.json"
    if stats_page == STATS_PAGE_WORKERS:
        view_slug = workers_view.replace("_", "-")
        return f"{CACHE_PREFIX}/workers/{view_slug}/default-{dataset}.json"
    if stats_page == STATS_PAGE_PLAYERS:
        view_slug = players_view.replace("_", "-")
        return f"{CACHE_PREFIX}/players/{view_slug}/default-{dataset}.json"
    if stats_page == STATS_PAGE_RECORDS:
        view_slug = records_view.replace("_", "-")
        return f"{CACHE_PREFIX}/records/{view_slug}/default-{dataset}.json"
    if stats_page == STATS_PAGE_MW_ACTION_CARDS:
        view_slug = (
            MW_ACTION_CARDS_VIEW_GENERAL
            if mw_action_cards_view == MW_ACTION_CARDS_VIEW_DRAFT
            else mw_action_cards_view
        ).replace("_", "-")
        return f"{CACHE_PREFIX}/mw-action-cards/{view_slug}/default-mw.json"
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


_MEMORY_CACHE_MAX_ITEMS = 64
_MEMORY_CACHE = OrderedDict()
_MEMORY_CACHE_LOCK = threading.Lock()
_BACKGROUND_EXECUTOR = ThreadPoolExecutor(max_workers=2)
_BACKGROUND_SCOPE_KEYS = set()
_BACKGROUND_SCOPE_LOCK = threading.Lock()


def _memory_cache_get(blob_name):
    """Return an isolated in-process cache value without contacting Storage."""
    with _MEMORY_CACHE_LOCK:
        payload = _MEMORY_CACHE.get(blob_name)
        if payload is None:
            return None
        _MEMORY_CACHE.move_to_end(blob_name)
        return copy.deepcopy(payload)


def _memory_cache_put(blob_name, payload):
    with _MEMORY_CACHE_LOCK:
        _MEMORY_CACHE[blob_name] = copy.deepcopy(payload)
        _MEMORY_CACHE.move_to_end(blob_name)
        while len(_MEMORY_CACHE) > _MEMORY_CACHE_MAX_ITEMS:
            _MEMORY_CACHE.popitem(last=False)


def _read_cache_blob(blob_name, cache_status):
    memory_payload = _memory_cache_get(blob_name)
    if memory_payload is not None:
        memory_payload["cache_status"] = f"memory_{cache_status}"
        return memory_payload
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
        _memory_cache_put(blob_name, payload)
        payload["cache_status"] = cache_status
        return payload
    except Exception:
        logging.exception("Failed to read cache blob %s", blob_name)
        return None


def _write_cache_blob(blob_name, payload, cache_status, compresslevel=6):
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
            gzip.compress(encoded, compresslevel=compresslevel, mtime=0),
            content_type="application/json",
        )
        return True
    except Exception:
        logging.exception("Failed to write cache blob %s", blob_name)
        return False


_REFRESH_PROGRESS_STATE_LOCK = threading.Lock()
_ACTIVE_REFRESH_PROGRESS = None


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def _refresh_status_default():
    """Build the public status shape, seeding completion from the active pack."""
    completed_at = None
    data_version = None
    if CACHE_BUCKET:
        try:
            bucket = storage.Client().bucket(CACHE_BUCKET)
            pack_blob = bucket.blob(f"{CACHE_PREFIX}/bootstrap/default-pack.json")
            if pack_blob.exists():
                pack_blob.reload()
                completed_at = pack_blob.updated.isoformat() if pack_blob.updated else None
                raw = pack_blob.download_as_bytes(raw_download=True)
                if raw.startswith(b"\x1f\x8b"):
                    raw = gzip.decompress(raw)
                data_version = json.loads(raw.decode("utf-8")).get("data_version")
        except Exception:
            logging.exception("Failed to seed refresh status from the default pack")
    return {
        "state": "idle",
        "run_id": None,
        "progress_percent": 0,
        "phase": "Ready",
        "started_at": None,
        "updated_at": _utc_now_iso(),
        "last_completed_at": completed_at,
        "completed_data_version": data_version,
    }


def _read_refresh_status():
    if not CACHE_BUCKET:
        return _refresh_status_default()
    try:
        bucket = storage.Client().bucket(CACHE_BUCKET)
        blob = bucket.blob(REFRESH_STATUS_BLOB)
        if not blob.exists():
            payload = _refresh_status_default()
            _write_refresh_status(payload)
            return payload
        payload = json.loads(blob.download_as_text(encoding="utf-8"))
        return {
            "state": str(payload.get("state") or "idle"),
            "run_id": payload.get("run_id"),
            "progress_percent": max(0, min(100, int(payload.get("progress_percent") or 0))),
            "phase": str(payload.get("phase") or "Ready"),
            "started_at": payload.get("started_at"),
            "updated_at": payload.get("updated_at"),
            "last_completed_at": payload.get("last_completed_at"),
            "completed_data_version": payload.get("completed_data_version"),
        }
    except Exception:
        logging.exception("Failed to read refresh status")
        return _refresh_status_default()


def _write_refresh_status(payload):
    if not CACHE_BUCKET:
        return False
    safe_payload = {
        "state": str(payload.get("state") or "idle"),
        "run_id": payload.get("run_id"),
        "progress_percent": max(0, min(100, int(payload.get("progress_percent") or 0))),
        "phase": str(payload.get("phase") or "Ready"),
        "started_at": payload.get("started_at"),
        "updated_at": payload.get("updated_at") or _utc_now_iso(),
        "last_completed_at": payload.get("last_completed_at"),
        "completed_data_version": payload.get("completed_data_version"),
    }
    try:
        bucket = storage.Client().bucket(CACHE_BUCKET)
        blob = bucket.blob(REFRESH_STATUS_BLOB)
        blob.cache_control = "no-store, max-age=0"
        blob.upload_from_string(
            json.dumps(safe_payload, separators=(",", ":")),
            content_type="application/json; charset=utf-8",
        )
        return True
    except Exception:
        logging.exception("Failed to publish refresh status")
        return False


def _read_refresh_lock():
    if not CACHE_BUCKET:
        return None
    try:
        blob = storage.Client().bucket(CACHE_BUCKET).blob(REFRESH_LOCK_BLOB)
        if not blob.exists():
            return None
        blob.reload()
        payload = json.loads(blob.download_as_text(encoding="utf-8"))
        payload["generation"] = blob.generation
        return payload
    except Exception:
        logging.exception("Failed to inspect refresh lock")
        return None


def _acquire_refresh_lock(run_id):
    if not CACHE_BUCKET:
        return False
    bucket = storage.Client().bucket(CACHE_BUCKET)
    blob = bucket.blob(REFRESH_LOCK_BLOB)
    payload = {"run_id": run_id, "created_at": _utc_now_iso()}
    try:
        blob.upload_from_string(
            json.dumps(payload, separators=(",", ":")),
            content_type="application/json; charset=utf-8",
            if_generation_match=0,
        )
        return True
    except PreconditionFailed:
        existing = _read_refresh_lock()
        try:
            created_at = datetime.fromisoformat(str((existing or {}).get("created_at") or ""))
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            created_at = datetime.min.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - created_at <= REFRESH_LOCK_MAX_AGE:
            return False
        try:
            stale_blob = bucket.blob(REFRESH_LOCK_BLOB)
            stale_blob.delete(if_generation_match=(existing or {}).get("generation"))
            blob.upload_from_string(
                json.dumps(payload, separators=(",", ":")),
                content_type="application/json; charset=utf-8",
                if_generation_match=0,
            )
            return True
        except Exception:
            logging.exception("Failed to replace a stale refresh lock")
            return False


def _release_refresh_lock(run_id):
    if not CACHE_BUCKET:
        return
    try:
        existing = _read_refresh_lock()
        if not existing or existing.get("run_id") != run_id:
            return
        storage.Client().bucket(CACHE_BUCKET).blob(REFRESH_LOCK_BLOB).delete(
            if_generation_match=existing.get("generation")
        )
    except Exception:
        logging.exception("Failed to release refresh lock")


class _RefreshProgress:
    """Persist monotonic, sanitized progress for scheduled and manual refreshes."""

    def __init__(self, run_id):
        previous = _read_refresh_status()
        self.run_id = run_id
        self.last_completed_at = previous.get("last_completed_at")
        self.completed_data_version = previous.get("completed_data_version")
        self.percent = 0
        self.snapshot_count = 0
        self.lock = threading.Lock()
        self.started_at = _utc_now_iso()
        self._publish("running", 0, "Starting refresh")

    def _publish(self, state, percent, phase, completed_at=None, data_version=None):
        self.percent = max(self.percent, max(0, min(100, int(percent))))
        if completed_at:
            self.last_completed_at = completed_at
        if data_version:
            self.completed_data_version = data_version
        _write_refresh_status({
            "state": state,
            "run_id": self.run_id,
            "progress_percent": self.percent,
            "phase": phase,
            "started_at": self.started_at,
            "updated_at": _utc_now_iso(),
            "last_completed_at": self.last_completed_at,
            "completed_data_version": self.completed_data_version,
        })

    def report(self, percent, phase):
        with self.lock:
            self._publish("running", percent, phase)

    def prepared(self, completed, total, label):
        percent = 4 + round((max(0, completed) / max(1, total)) * 41)
        self.report(percent, f"Preparing data: {label}")

    def snapshot_completed(self):
        with self.lock:
            self.snapshot_count += 1
            percent = 50 + round(min(1, self.snapshot_count / 64) * 42)
            self._publish(
                "running",
                percent,
                f"Generating snapshots ({self.snapshot_count})",
            )

    def complete(self, data_version):
        with self.lock:
            completed_at = _utc_now_iso()
            self._publish("succeeded", 100, "Refresh complete", completed_at, data_version)

    def fail(self):
        with self.lock:
            self._publish("failed", self.percent, "Refresh failed")


def _active_refresh_snapshot_completed():
    with _REFRESH_PROGRESS_STATE_LOCK:
        progress = _ACTIVE_REFRESH_PROGRESS
    if progress is not None:
        progress.snapshot_completed()


def _enqueue_cache_blob_write(blob_name, payload, cache_status, compresslevel=6):
    """Make the result reusable in-process, then persist it off the response path."""
    snapshot = dict(payload)
    snapshot["cache_status"] = cache_status
    snapshot["cache_updated_at"] = datetime.now(timezone.utc).isoformat()
    _memory_cache_put(blob_name, snapshot)
    _BACKGROUND_EXECUTOR.submit(
        _write_cache_blob, blob_name, payload, cache_status, compresslevel
    )
    return True


_CARD_ATTRIBUTE_GROUPS = None


def _parse_card_attribute_csv(source_text):
    """Build SQL-ready card groups from the dashboard's canonical CSV."""
    reader = csv.DictReader(io.StringIO(source_text))
    required = {"Type", "Name", "Size", "Reefer"}
    if not required.issubset(set(reader.fieldnames or [])):
        raise ValueError("cards_attributes.csv is missing Type, Name, Size, or Reefer")
    groups = {
        "reefer_animals": set(),
        "small_animals": set(),
        "medium_animals": set(),
        "large_animals": set(),
        "project_cards": set(),
        "sponsor_cards": set(),
    }
    for row in reader:
        card_name = str(row.get("Name") or "").strip().lower()
        card_type = str(row.get("Type") or "").strip().lower()
        if not card_name:
            continue
        if card_type == "project":
            groups["project_cards"].add(card_name)
        elif card_type == "sponsor":
            groups["sponsor_cards"].add(card_name)
        elif card_type == "animal":
            reefer = str(row.get("Reefer") or "").strip().lower()
            if reefer not in {"", "0", "false", "no"}:
                groups["reefer_animals"].add(card_name)
            try:
                size = int(float(str(row.get("Size") or "").strip()))
            except ValueError:
                size = None
            if size in (1, 2):
                groups["small_animals"].add(card_name)
            elif size == 3:
                groups["medium_animals"].add(card_name)
            elif size in (4, 5):
                groups["large_animals"].add(card_name)
    parsed = {key: sorted(values) for key, values in groups.items()}
    if not parsed["small_animals"] or not parsed["project_cards"] or not parsed["sponsor_cards"]:
        raise ValueError("cards_attributes.csv did not produce the required card groups")
    parsed["source_sha256"] = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    return parsed


def _load_card_attribute_groups(force_refresh=False):
    """Use memory/GCS metadata; refresh GCS from the canonical public CSV daily."""
    global _CARD_ATTRIBUTE_GROUPS
    if _CARD_ATTRIBUTE_GROUPS is not None and not force_refresh:
        return _CARD_ATTRIBUTE_GROUPS
    if not force_refresh:
        cached = _read_cache_blob(CARD_ATTRIBUTES_CACHE_BLOB, "hit")
        if cached:
            cached.pop("cache_status", None)
            cached.pop("cache_updated_at", None)
            _CARD_ATTRIBUTE_GROUPS = cached
            return cached
    try:
        if os.path.exists(CARD_ATTRIBUTES_LOCAL_PATH):
            with open(CARD_ATTRIBUTES_LOCAL_PATH, "r", encoding="utf-8-sig", newline="") as source:
                source_text = source.read()
        else:
            request = urllib.request.Request(
                CARD_ATTRIBUTES_URL,
                headers={"User-Agent": "ark-nova-dashboard-refresh"},
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                source_text = response.read().decode("utf-8-sig")
        parsed = _parse_card_attribute_csv(source_text)
        _write_cache_blob(CARD_ATTRIBUTES_CACHE_BLOB, parsed, "refreshed")
        _CARD_ATTRIBUTE_GROUPS = parsed
        return parsed
    except Exception:
        logging.exception("Failed to refresh card attribute metadata from %s", CARD_ATTRIBUTES_URL)
    cached = _read_cache_blob(CARD_ATTRIBUTES_CACHE_BLOB, "hit")
    if cached:
        cached.pop("cache_status", None)
        cached.pop("cache_updated_at", None)
        _CARD_ATTRIBUTE_GROUPS = cached
        return cached
    raise RuntimeError("Card attribute metadata is unavailable")


_MERGE_PLAYERS_METADATA = None


def _parse_merge_players_csv(source_text):
    """Validate the dashboard-owned row-per-identity account mapping."""
    groups = []
    aliases_seen = {}
    group_keys = set()
    reader = csv.reader(io.StringIO(source_text))
    for row_number, raw_row in enumerate(reader, start=1):
        members = [str(value or "").strip() for value in raw_row]
        members = [value for value in members if value]
        if not members:
            continue
        if len(members) < 2:
            raise ValueError(
                f"merge_players.csv row {row_number} must contain at least two player names"
            )
        normalized_members = [value.casefold() for value in members]
        if len(set(normalized_members)) != len(normalized_members):
            raise ValueError(
                f"merge_players.csv row {row_number} contains a duplicate player name"
            )
        for member, normalized in zip(members, normalized_members):
            previous = aliases_seen.get(normalized)
            if previous is not None:
                raise ValueError(
                    f"merge_players.csv player {member!r} occurs in rows "
                    f"{previous} and {row_number}"
                )
            aliases_seen[normalized] = row_number
        group_key = tuple(sorted(normalized_members))
        if group_key in group_keys:
            raise ValueError(f"merge_players.csv row {row_number} duplicates another group")
        group_keys.add(group_key)
        identity = "merge:" + hashlib.sha256(
            "\0".join(group_key).encode("utf-8")
        ).hexdigest()[:20]
        groups.append({"identity": identity, "members": members})
    return {
        "status": "ok",
        "groups": groups,
        "source_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
    }


def _merge_players_maps(metadata):
    alias_to_identity = {}
    identity_to_members = {}
    alias_casefold = {}
    for group in metadata.get("groups", []):
        identity = str(group.get("identity") or "")
        members = [str(value) for value in group.get("members", []) if str(value)]
        if not identity or len(members) < 2:
            continue
        identity_to_members[identity] = members
        for member in members:
            alias_to_identity[member] = identity
            alias_casefold[member.casefold()] = member
    return alias_to_identity, identity_to_members, alias_casefold


def _player_identity(player, metadata=None):
    player = str(player or "").strip()
    metadata = metadata or _load_merge_players_metadata()
    alias_to_identity, _, alias_casefold = _merge_players_maps(metadata)
    exact_alias = alias_casefold.get(player.casefold(), player)
    return alias_to_identity.get(exact_alias, f"player:{player}")


def _player_merge_members(player, metadata=None):
    player = str(player or "").strip()
    metadata = metadata or _load_merge_players_metadata()
    alias_to_identity, identity_to_members, alias_casefold = _merge_players_maps(metadata)
    exact_alias = alias_casefold.get(player.casefold(), player)
    identity = alias_to_identity.get(exact_alias)
    return list(identity_to_members.get(identity, [player]))


def _merge_players_map_cte(metadata):
    rows = []
    for group in metadata.get("groups", []):
        identity = str(group["identity"])
        rows.extend(
            f"STRUCT({_sql_string(member)} AS player, "
            f"{_sql_string(identity)} AS player_identity)"
            for member in group["members"]
        )
    if not rows:
        return (
            "SELECT * FROM UNNEST("
            "ARRAY<STRUCT<player STRING, player_identity STRING>>[])"
        )
    return "SELECT * FROM UNNEST([\n        " + ",\n        ".join(rows) + "\n      ])"


def _load_merge_players_metadata(force_refresh=False):
    """Load merge groups remotely, retaining a validated last-known-good copy."""
    global _MERGE_PLAYERS_METADATA
    if _MERGE_PLAYERS_METADATA is not None and not force_refresh:
        return _MERGE_PLAYERS_METADATA
    if not force_refresh:
        cached = _read_cache_blob(MERGE_PLAYERS_CACHE_BLOB, "hit")
        if cached:
            cached.pop("cache_status", None)
            cached.pop("cache_updated_at", None)
            _MERGE_PLAYERS_METADATA = cached
            return cached
    live_error = None
    try:
        request = urllib.request.Request(
            MERGE_PLAYERS_URL,
            headers={"User-Agent": "ark-nova-dashboard-refresh"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            source_text = response.read().decode("utf-8-sig")
        metadata = _parse_merge_players_csv(source_text)
        if not _write_cache_blob(
            MERGE_PLAYERS_CACHE_BLOB, metadata, "refreshed"
        ):
            raise RuntimeError("Could not publish merge_players.csv metadata")
        _MERGE_PLAYERS_METADATA = metadata
        return metadata
    except Exception as exc:
        live_error = exc
        logging.exception(
            "Failed to refresh merged-player metadata from %s", MERGE_PLAYERS_URL
        )
    cached = _read_cache_blob(MERGE_PLAYERS_CACHE_BLOB, "hit")
    if cached:
        cached.pop("cache_status", None)
        cached.pop("cache_updated_at", None)
        _MERGE_PLAYERS_METADATA = cached
        return cached
    try:
        with open(
            MERGE_PLAYERS_LOCAL_PATH, "r", encoding="utf-8-sig", newline=""
        ) as source:
            metadata = _parse_merge_players_csv(source.read())
        _write_cache_blob(MERGE_PLAYERS_CACHE_BLOB, metadata, "packaged_fallback")
        _MERGE_PLAYERS_METADATA = metadata
        return metadata
    except Exception as local_error:
        raise RuntimeError(
            "Merged-player metadata is unavailable and no validated fallback exists"
        ) from (live_error or local_error)


_ARENA_METADATA = None


def _arena_season_number(value):
    token = str(value or "").strip().upper()
    if len(token) < 2 or token[0] != "S" or not token[1:].isdigit():
        raise ValueError(f"Invalid Arena season name: {value}")
    return int(token[1:])


def _ensure_arena_effective_ends(metadata):
    """Upgrade cached Arena metadata created before the grace boundary existed."""
    for season in (metadata or {}).get("seasons", []):
        if season.get("effective_end_utc"):
            continue
        official_end = datetime.fromisoformat(
            str(season["end_utc"]).replace("Z", "+00:00")
        )
        season["effective_end_utc"] = (
            official_end + ARENA_END_GRACE
        ).isoformat().replace("+00:00", "Z")
    return metadata


def _read_arena_source(filename, missing_ok=False):
    local_path = os.path.join(ARENA_LOCAL_DIR, filename)
    request = urllib.request.Request(
        f"{ARENA_SOURCE_BASE_URL}/{filename}",
        headers={"User-Agent": "ark-nova-dashboard-refresh"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8-sig")
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
    except (urllib.error.URLError, TimeoutError):
        # The packaged copy makes a daily refresh deterministic during a
        # temporary GitHub outage. Remote-first lookup means manually adding a
        # new season/ranking file to the dashboard is still discovered on the
        # next refresh without redeploying the Function.
        pass
    if os.path.exists(local_path):
        with open(local_path, "r", encoding="utf-8-sig", newline="") as source:
            return source.read()
    if missing_ok:
        return None
    raise FileNotFoundError(f"Arena source file is unavailable: {filename}")


def _parse_arena_settings(source_text):
    reader = csv.DictReader(io.StringIO(source_text))
    required = {"Season", "Start (UTC)", "End (UTC)", "Mode"}
    if not required.issubset(set(reader.fieldnames or [])):
        raise ValueError("arena_settings.csv is missing Season, Start (UTC), End (UTC), or Mode")
    seasons = []
    seen = set()
    for raw in reader:
        season = str(raw.get("Season") or "").strip().upper()
        number = _arena_season_number(season)
        if season in seen:
            raise ValueError(f"Duplicate Arena season: {season}")
        seen.add(season)
        mode = str(raw.get("Mode") or "").strip()
        if mode not in {"MW", "Base"}:
            raise ValueError(f"Arena season {season} has invalid Mode {mode!r}")
        try:
            start = datetime.strptime(str(raw.get("Start (UTC)") or "").strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            end = datetime.strptime(str(raw.get("End (UTC)") or "").strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise ValueError(f"Arena season {season} has an invalid UTC timestamp") from exc
        if start >= end:
            raise ValueError(f"Arena season {season} must start before it ends")
        effective_end = end + ARENA_END_GRACE
        seasons.append({
            "season": season,
            "number": number,
            "start_utc": start.isoformat().replace("+00:00", "Z"),
            "end_utc": end.isoformat().replace("+00:00", "Z"),
            # The official deadline remains public metadata. Games that started
            # before it may finish shortly afterwards, so analytical membership
            # uses this separate, end-exclusive grace boundary.
            "effective_end_utc": effective_end.isoformat().replace("+00:00", "Z"),
            "mode": mode,
            "is_mw": 1 if mode == "MW" else 0,
        })
    if not seasons:
        raise ValueError("arena_settings.csv contains no seasons")
    by_start = sorted(seasons, key=lambda item: item["start_utc"])
    for previous, current in zip(by_start, by_start[1:]):
        if current["start_utc"] < previous["effective_end_utc"]:
            raise ValueError(f"Arena seasons {previous['season']} and {current['season']} overlap")
    return sorted(seasons, key=lambda item: item["number"])


def _parse_arena_ranking(source_text, season):
    reader = csv.DictReader(io.StringIO(source_text))
    required = {"#", "BGA Name", "Rating"}
    if not required.issubset(set(reader.fieldnames or [])):
        raise ValueError(f"{season.lower()}.csv is missing #, BGA Name, or Rating")
    rows = []
    names = set()
    for raw in reader:
        try:
            rank = int(str(raw.get("#") or "").strip())
            rating = int(round(float(str(raw.get("Rating") or "").strip())))
        except ValueError as exc:
            raise ValueError(f"{season.lower()}.csv contains a non-numeric rank or rating") from exc
        player = str(raw.get("BGA Name") or "").strip()
        if not player or player in names:
            raise ValueError(f"{season.lower()}.csv contains a blank or duplicate player")
        names.add(player)
        rows.append({"rank": rank, "player": player, "end": rating})
    rows.sort(key=lambda item: item["rank"])
    if len(rows) != 100 or [item["rank"] for item in rows] != list(range(1, 101)):
        raise ValueError(f"{season.lower()}.csv must contain ranks 1 through 100 exactly once")
    return rows


def _arena_manifest(metadata, data_version=None):
    metadata = _ensure_arena_effective_ends(metadata)
    payload = {
        "status": "ok",
        "generated_at": metadata["generated_at"],
        "seasons": [dict(item) for item in metadata["seasons"]],
        "latest_by_mode": dict(metadata["latest_by_mode"]),
        "latest_top_100": metadata.get("latest_top_100"),
    }
    if data_version:
        payload["data_version"] = data_version
    return payload


def _load_arena_metadata(force_refresh=False, publish_manifest=True):
    """Load validated season/ranking CSVs and retain a last-known-good copy."""
    global _ARENA_METADATA
    if _ARENA_METADATA is not None and not force_refresh:
        return _ensure_arena_effective_ends(_ARENA_METADATA)
    if not force_refresh:
        cached = _read_cache_blob(ARENA_METADATA_CACHE_BLOB, "hit")
        if cached:
            cached.pop("cache_status", None)
            cached.pop("cache_updated_at", None)
            _ARENA_METADATA = _ensure_arena_effective_ends(cached)
            return cached
    try:
        settings_text = _read_arena_source("arena_settings.csv")
        seasons = _parse_arena_settings(settings_text)
        rankings = {}
        now = datetime.now(timezone.utc)
        for season in seasons:
            source = _read_arena_source(f"{season['season'].lower()}.csv", missing_ok=True)
            if source is not None:
                rankings[season["season"]] = _parse_arena_ranking(source, season["season"])
            start = datetime.fromisoformat(season["start_utc"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(
                season["effective_end_utc"].replace("Z", "+00:00")
            )
            season["started"] = now >= start
            season["completed"] = now >= end
            season["top_100_available"] = season["season"] in rankings
        latest_by_mode = {}
        for mode in ("MW", "Base"):
            eligible = [item for item in seasons if item["mode"] == mode and item["started"]]
            latest_by_mode[mode.lower()] = max(eligible, key=lambda item: item["number"])["season"] if eligible else None
        available = [item for item in seasons if item["top_100_available"]]
        metadata = {
            "status": "ok",
            "generated_at": now.isoformat(),
            "source_sha256": hashlib.sha256(settings_text.encode("utf-8")).hexdigest(),
            "seasons": seasons,
            "rankings": rankings,
            "latest_by_mode": latest_by_mode,
            "latest_top_100": max(available, key=lambda item: item["number"])["season"] if available else None,
        }
        if not _write_cache_blob(ARENA_METADATA_CACHE_BLOB, metadata, "refreshed"):
            raise RuntimeError("Could not persist Arena metadata")
        if publish_manifest and not _write_cache_blob(ARENA_MANIFEST_BLOB, _arena_manifest(metadata), "refreshed"):
            raise RuntimeError("Could not publish Arena manifest")
        _ARENA_METADATA = _ensure_arena_effective_ends(metadata)
        return metadata
    except Exception:
        logging.exception("Failed to refresh Arena metadata from %s", ARENA_SOURCE_BASE_URL)
        cached = _read_cache_blob(ARENA_METADATA_CACHE_BLOB, "hit")
        if cached:
            cached.pop("cache_status", None)
            cached.pop("cache_updated_at", None)
            _ARENA_METADATA = _ensure_arena_effective_ends(cached)
            return cached
        raise RuntimeError("Arena metadata is unavailable")


_RECORDS_MANUAL_SOURCE = None


def _download_public_csv(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ark-nova-dashboard-refresh"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8-sig")


def _records_sheet_int(raw_value, field_name, row_number):
    token = str(raw_value or "").strip()
    try:
        value = int(token)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Records sheet row {row_number} has invalid {field_name}: {token!r}"
        ) from exc
    return value


def _records_sheet_common(raw, row_number, view):
    player = str(raw.get("Player") or "").strip()
    table_id = str(raw.get("ID") or "").strip()
    map_code = str(raw.get("Map") or "").strip()
    mode_token = str(raw.get("Mode") or "").strip().lower()
    mode_map = {"mw": ("MW", 1), "base": ("Base", 0)}
    map_by_code = {item["code"].lower(): item for item in ALL_MAPS_FOR_METRICS}
    map_item = map_by_code.get(map_code.lower())
    if not player:
        raise ValueError(f"Records sheet row {row_number} has a blank Player")
    if not table_id.isdigit():
        raise ValueError(f"Records sheet row {row_number} has invalid ID: {table_id!r}")
    if mode_token not in mode_map:
        raise ValueError(f"Records sheet row {row_number} has invalid Mode: {raw.get('Mode')!r}")
    if not map_item:
        raise ValueError(f"Records sheet row {row_number} has unknown Map code: {map_code!r}")
    date_token = str(raw.get("Date") or "").strip()
    try:
        parsed_date = datetime.strptime(date_token, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(
            f"Records sheet row {row_number} has invalid Date: {date_token!r}"
        ) from exc
    mode, is_mw = mode_map[mode_token]
    return {
        "record_view": view,
        "source_row": row_number,
        "is_mw": is_mw,
        "mode": mode,
        "player": player,
        "table_id": table_id,
        "map_code": map_item["code"],
        "map_name": map_item["full"],
        "game_date": parsed_date.isoformat(),
    }


def _parse_records_fastest_sheet(source_text):
    reader = csv.DictReader(io.StringIO(source_text))
    # Games to add owns only the manually extrapolated record values. Dataset,
    # map, date, and all filter metadata deliberately come from Full Sample.
    required = {"Turns", "Player", "Score", "ID", "EPT"}
    if not required.issubset(set(reader.fieldnames or [])):
        missing = sorted(required - set(reader.fieldnames or []))
        raise ValueError(f"Fastest Games sheet is missing columns: {', '.join(missing)}")
    rows = []
    seen = set()
    for row_number, raw in enumerate(reader, start=2):
        if not any(str(value or "").strip() for value in raw.values()):
            continue
        player = str(raw.get("Player") or "").strip()
        table_id = str(raw.get("ID") or "").strip()
        if not player:
            raise ValueError(f"Fastest Games row {row_number} has a blank Player")
        if not table_id.isdigit():
            raise ValueError(f"Fastest Games row {row_number} has invalid ID: {table_id!r}")
        item = {
            "record_view": RECORDS_VIEW_FASTEST_GAMES,
            "source_row": row_number,
            "player": player,
            "table_id": table_id,
            "turns": _records_sheet_int(raw.get("Turns"), "Turns", row_number),
            "score": _records_sheet_int(raw.get("Score"), "Score", row_number),
            "ept": _records_sheet_int(raw.get("EPT"), "EPT", row_number),
            "flat": None,
            "end": None,
            "total": None,
            "move": None,
            "actions": None,
            "result_code": None,
        }
        if item["turns"] < 1 or item["turns"] > 23:
            raise ValueError(f"Fastest Games row {row_number} must have Turns between 1 and 23")
        key = (item["table_id"], item["player"].casefold())
        if key in seen:
            raise ValueError(f"Fastest Games sheet has duplicate ID/Player at row {row_number}")
        seen.add(key)
        rows.append(item)
    if not rows:
        raise ValueError("Fastest Games sheet contains no data rows")
    return rows


def _parse_records_biggest_turns_sheet(source_text):
    reader = csv.DictReader(io.StringIO(source_text))
    required = {
        "Flat", "End", "Total", "Player", "Score", "Turns", "Map", "Move",
        "# Actions", "ID", "Result", "Date", "Mode",
    }
    if not required.issubset(set(reader.fieldnames or [])):
        missing = sorted(required - set(reader.fieldnames or []))
        raise ValueError(f"Biggest Turns sheet is missing columns: {', '.join(missing)}")
    rows = []
    seen = set()
    for row_number, raw in enumerate(reader, start=2):
        if not any(str(value or "").strip() for value in raw.values()):
            continue
        item = _records_sheet_common(raw, row_number, RECORDS_VIEW_BIGGEST_TURNS)
        result_code = str(raw.get("Result") or "").strip().upper()
        if result_code not in {"W", "D", "L"}:
            raise ValueError(f"Biggest Turns row {row_number} has invalid Result: {result_code!r}")
        item.update({
            "flat": _records_sheet_int(raw.get("Flat"), "Flat", row_number),
            "end": _records_sheet_int(raw.get("End"), "End", row_number),
            "total": _records_sheet_int(raw.get("Total"), "Total", row_number),
            "score": _records_sheet_int(raw.get("Score"), "Score", row_number),
            "turns": _records_sheet_int(raw.get("Turns"), "Turns", row_number),
            "move": _records_sheet_int(raw.get("Move"), "Move", row_number),
            "actions": _records_sheet_int(raw.get("# Actions"), "# Actions", row_number),
            "ept": 0,
            "result_code": result_code,
        })
        if item["flat"] + item["end"] != item["total"]:
            raise ValueError(
                f"Biggest Turns row {row_number} has Total {item['total']}, "
                f"but Flat + End is {item['flat'] + item['end']}"
            )
        key = (item["is_mw"], item["table_id"], item["player"])
        if key in seen:
            raise ValueError(f"Biggest Turns sheet has duplicate Mode/ID/Player at row {row_number}")
        seen.add(key)
        rows.append(item)
    if not rows:
        raise ValueError("Biggest Turns sheet contains no data rows")
    return rows


def _records_sheet_float(raw_value, field_name, row_number):
    token = str(raw_value or "").strip()
    try:
        value = float(token)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Records sheet row {row_number} has invalid {field_name}: {token!r}"
        ) from exc
    if not math.isfinite(value):
        raise ValueError(
            f"Records sheet row {row_number} has non-finite {field_name}: {token!r}"
        )
    return value


def _parse_records_elo_leaderboard_sheet(source_text):
    """Parse the public Masters sheet by column position.

    The export has an intentionally blank first column, so DictReader would
    create an unstable empty header. Positional parsing keeps the source
    contract explicit: B country, C player, F Peak Elo, H Peak Arena.
    """
    reader = csv.reader(io.StringIO(source_text))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise ValueError("Elo Leaderboard sheet is empty") from exc
    if len(header) < 8:
        raise ValueError("Elo Leaderboard sheet must contain at least eight columns")
    normalized_header = [str(value or "").strip().lower() for value in header]
    expected_headers = {
        1: {"nationality", "country"},
        2: {"bga name", "player"},
        # Spreadsheet Peak Elo is an external historical leaderboard metric,
        # not the deprecated Full Sample `elo` field.
        5: {"peak elo"},
        7: {"peak arena"},
    }
    for index, accepted in expected_headers.items():
        if normalized_header[index] not in accepted:
            raise ValueError(
                f"Elo Leaderboard sheet column {index + 1} must be one of {sorted(accepted)}"
            )

    rows = []
    seen_players = set()
    for row_number, raw in enumerate(reader, start=2):
        if not any(str(value or "").strip() for value in raw):
            continue
        if len(raw) < 8:
            raise ValueError(f"Elo Leaderboard row {row_number} has fewer than eight columns")
        country = str(raw[1] or "").strip().lower()
        player = str(raw[2] or "").strip()
        if len(country) != 2 or not all("a" <= char <= "z" for char in country):
            raise ValueError(
                f"Elo Leaderboard row {row_number} has invalid country code: {raw[1]!r}"
            )
        if not player:
            raise ValueError(f"Elo Leaderboard row {row_number} has a blank player")
        player_key = player.casefold()
        if player_key in seen_players:
            raise ValueError(f"Elo Leaderboard has duplicate player at row {row_number}: {player!r}")
        seen_players.add(player_key)
        peak_elo = _records_sheet_float(raw[5], "Peak Elo", row_number)
        peak_arena = None
        if str(raw[7] or "").strip():
            peak_arena = _records_sheet_float(raw[7], "Peak Arena", row_number)
        rows.append({
            "source_row": row_number,
            "country": country,
            "player": player,
            "peak_elo": peak_elo,
            "peak_arena": peak_arena,
        })

    if len(rows) < 100:
        raise ValueError(f"Elo Leaderboard sheet contains only {len(rows)} valid players; 100 are required")
    rows.sort(key=lambda item: (-item["peak_elo"], item["source_row"], item["player"].casefold()))
    rows = [
        {**item, "rank": rank}
        for rank, item in enumerate(rows[:100], start=1)
    ]
    return rows


def _fetch_records_manual_source():
    fastest_text = _download_public_csv(RECORDS_FASTEST_SHEET_URL)
    biggest_text = _download_public_csv(RECORDS_BIGGEST_TURNS_SHEET_URL)
    fastest = _parse_records_fastest_sheet(fastest_text)
    biggest = _parse_records_biggest_turns_sheet(biggest_text)
    return {
        "status": "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_sha256": hashlib.sha256(
            (fastest_text + "\n---biggest-turns---\n" + biggest_text).encode("utf-8")
        ).hexdigest(),
        "fastest_games": fastest,
        "biggest_turns": biggest,
    }


def _fetch_records_elo_leaderboard_source():
    source_text = _download_public_csv(RECORDS_ELO_LEADERBOARD_SHEET_URL)
    return {
        "status": "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        "rows": _parse_records_elo_leaderboard_sheet(source_text),
    }


def _cached_records_elo_leaderboard_source():
    cached = _read_cache_blob(RECORDS_ELO_LEADERBOARD_CACHE_BLOB, "hit")
    if not cached:
        return None
    cached.pop("cache_status", None)
    cached.pop("cache_updated_at", None)
    return cached


def _refresh_records_elo_leaderboard_snapshots():
    """Refresh the dataset-neutral Masters Top 100 snapshots atomically by view.

    The source sheet has no MW/Base dimension. Both dashboard dataset paths
    therefore publish the same validated rows so changing the global dataset
    cannot make the leaderboard disappear.
    """
    live_error = None
    try:
        source = _fetch_records_elo_leaderboard_source()
        if not _write_cache_blob(RECORDS_ELO_LEADERBOARD_CACHE_BLOB, source, "refreshed"):
            raise RuntimeError("Could not persist validated Elo Leaderboard source")
        source_status = "live"
    except Exception as exc:
        live_error = exc
        logging.exception("Failed to refresh Elo Leaderboard source from Google Sheets")
        source = _cached_records_elo_leaderboard_source()
        if not source:
            raise RuntimeError("Elo Leaderboard is unavailable and no validated cache exists") from exc
        source_status = "cached"

    results = []
    for dataset in (1, 0):
        payload = {
            "status": "ok",
            "stats_page": STATS_PAGE_RECORDS,
            "records_view": RECORDS_VIEW_ELO_LEADERBOARD,
            "is_mw": dataset,
            "data": source["rows"],
            "row_count": len(source["rows"]),
            "source": "records_elo_leaderboard_snapshot",
            "source_status": source_status,
            "source_sha256": source.get("source_sha256"),
        }
        if live_error:
            payload["live_error"] = str(live_error)
        cache_write_ok = _write_cached_snapshot(
            dataset,
            payload,
            STATS_PAGE_RECORDS,
            records_view=RECORDS_VIEW_ELO_LEADERBOARD,
        )
        results.append({
            "status": "ok" if cache_write_ok else "error",
            "is_mw": dataset,
            "stats_page": STATS_PAGE_RECORDS,
            "records_view": RECORDS_VIEW_ELO_LEADERBOARD,
            "cache_status": source_status if cache_write_ok else "cache_write_failed",
            "rows": len(source["rows"]),
        })
    return results


def _cached_records_manual_source():
    cached = _read_cache_blob(RECORDS_MANUAL_CACHE_BLOB, "hit")
    if not cached:
        return None
    cached.pop("cache_status", None)
    cached.pop("cache_updated_at", None)
    return cached


def _sql_string_list(values):
    def bigquery_string(value):
        escaped = str(value).replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"
    return ", ".join(bigquery_string(value) for value in values)


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
    build_view=BUILD_VIEW_ENCLOSURES,
    predictors_view=PREDICTORS_VIEW_GENERAL,
    actions_view=ACTIONS_VIEW_STARTING_POSITION,
    conservation_view=CONSERVATION_VIEW_PROJECTS,
    scoring_view=SCORING_VIEW_FINAL_SCORE,
    workers_view=WORKERS_VIEW_GENERAL,
    players_view=PLAYERS_VIEW_GENERAL,
    records_view=RECORDS_VIEW_ELO_LEADERBOARD,
    mw_action_cards_view=MW_ACTION_CARDS_VIEW_GENERAL,
):
    return _read_cache_blob(
        _cache_blob_name(
            is_mw, stats_page, endgames_view, maps_view,
            sponsor_endgames_view, combinations_view,
            build_view, predictors_view, actions_view, conservation_view, scoring_view, workers_view, players_view, records_view,
            mw_action_cards_view
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
    build_view=BUILD_VIEW_ENCLOSURES,
    predictors_view=PREDICTORS_VIEW_GENERAL,
    actions_view=ACTIONS_VIEW_STARTING_POSITION,
    conservation_view=CONSERVATION_VIEW_PROJECTS,
    scoring_view=SCORING_VIEW_FINAL_SCORE,
    workers_view=WORKERS_VIEW_GENERAL,
    players_view=PLAYERS_VIEW_GENERAL,
    records_view=RECORDS_VIEW_ELO_LEADERBOARD,
    mw_action_cards_view=MW_ACTION_CARDS_VIEW_GENERAL,
):
    return _write_cache_blob(
        _cache_blob_name(
            is_mw, stats_page, endgames_view, maps_view,
            sponsor_endgames_view, combinations_view,
            build_view, predictors_view, actions_view, conservation_view, scoring_view, workers_view, players_view, records_view,
            mw_action_cards_view
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
    source = "window.__ARK_NOVA_DATA_VERSION__=" + json.dumps(_read_data_version()) + ";"
    source += "window.__ARK_NOVA_HOME_DEFAULTS__=" + json.dumps(
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


def _default_snapshot_pack_blob_names():
    """Return the active frontend default manifest, excluding autocomplete indexes."""
    names = []
    for dataset in ("mw", "base"):
        names.extend([
            f"{CACHE_PREFIX}/default-{dataset}.json",
            f"{CACHE_PREFIX}/opening-hand/default-{dataset}.json",
            f"{CACHE_PREFIX}/endgames/default-{dataset}.json",
            f"{CACHE_PREFIX}/endgames/cp-distribution/default-{dataset}.json",
            f"{CACHE_PREFIX}/endgames/cp-by-map/default-{dataset}.json",
            f"{CACHE_PREFIX}/maps/metrics/default-{dataset}.json",
            f"{CACHE_PREFIX}/maps/tournament_h2h/default-{dataset}.json",
            f"{CACHE_PREFIX}/sponsor-endgames/cp/default-{dataset}.json",
            f"{CACHE_PREFIX}/sponsor-endgames/appeal/default-{dataset}.json",
            f"{CACHE_PREFIX}/icons/default-{dataset}.json",
            f"{CACHE_PREFIX}/build/enclosures/delta/default-{dataset}.json",
            f"{CACHE_PREFIX}/build/enclosures/frequency/default-{dataset}.json",
            f"{CACHE_PREFIX}/build/hexes/delta/default-{dataset}.json",
            f"{CACHE_PREFIX}/build/hexes/frequency/default-{dataset}.json",
            f"{CACHE_PREFIX}/predictors/general/default-{dataset}.json",
            f"{CACHE_PREFIX}/predictors/icon/default-{dataset}.json",
            f"{CACHE_PREFIX}/predictors/specific/default-{dataset}.json",
            f"{CACHE_PREFIX}/actions/starting_position/delta/default-{dataset}.json",
            f"{CACHE_PREFIX}/actions/upgrades/delta/default-{dataset}.json",
            f"{CACHE_PREFIX}/actions/upgrade_order/delta/default-{dataset}.json",
            f"{CACHE_PREFIX}/actions/upgrade_order/frequency/default-{dataset}.json",
            f"{CACHE_PREFIX}/actions/upgrades_by_map/delta/default-{dataset}.json",
            f"{CACHE_PREFIX}/actions/upgrades_by_map/frequency/default-{dataset}.json",
            f"{CACHE_PREFIX}/conservation/projects/default-{dataset}.json",
            f"{CACHE_PREFIX}/conservation/project-rewards/default-{dataset}.json",
            f"{CACHE_PREFIX}/conservation/cp-rewards/default-{dataset}.json",
            f"{CACHE_PREFIX}/scoring/final-score/default-{dataset}.json",
            f"{CACHE_PREFIX}/scoring/appeal/default-{dataset}.json",
            f"{CACHE_PREFIX}/scoring/conservation-points/default-{dataset}.json",
            f"{CACHE_PREFIX}/scoring/reputation/default-{dataset}.json",
            f"{CACHE_PREFIX}/workers/general/default-{dataset}.json",
            f"{CACHE_PREFIX}/workers/two-cp-worker/default-{dataset}.json",
            f"{CACHE_PREFIX}/players/general/default-{dataset}.json",
            f"{CACHE_PREFIX}/records/elo-leaderboard/default-{dataset}.json",
            f"{CACHE_PREFIX}/records/fastest-games/default-{dataset}.json",
            f"{CACHE_PREFIX}/records/highest-scores/default-{dataset}.json",
            f"{CACHE_PREFIX}/records/biggest-turns/default-{dataset}.json",
            f"{CACHE_PREFIX}/records/most-icons/default-{dataset}.json",
            f"{CACHE_PREFIX}/combinations/card-card/default-{dataset}.json",
            f"{CACHE_PREFIX}/combinations/card-map/default-{dataset}.json",
            f"{CACHE_PREFIX}/combinations/card-round/default-{dataset}.json",
            f"{CACHE_PREFIX}/combinations/card-endgame/default-{dataset}.json",
        ])
    names.extend([
        f"{CACHE_PREFIX}/combinations/card-action-card/default-mw.json",
        f"{CACHE_PREFIX}/mw-action-cards/general/default-mw.json",
        f"{CACHE_PREFIX}/mw-action-cards/by-map/default-mw.json",
        f"{CACHE_PREFIX}/mw-action-cards/synergies/default-mw.json",
    ])
    return names


def _write_default_snapshot_pack(data_version):
    """Publish all current default payloads as one atomically cached daily asset."""
    if not CACHE_BUCKET or not data_version:
        return False
    try:
        bucket = storage.Client().bucket(CACHE_BUCKET)
        snapshots = {}
        for blob_name in _default_snapshot_pack_blob_names():
            blob = bucket.blob(blob_name)
            if not blob.exists():
                raise RuntimeError(f"Default snapshot is missing: {blob_name}")
            raw = blob.download_as_bytes(raw_download=True)
            if raw.startswith(b"\x1f\x8b"):
                raw = gzip.decompress(raw)
            snapshots[blob_name] = json.loads(raw.decode("utf-8"))
        payload = {
            "status": "ok",
            "schema_version": DEFAULT_PACK_SCHEMA_VERSION,
            "data_version": data_version,
            "snapshots": snapshots,
        }
        encoded = json.dumps(payload, default=_json_default, separators=(",", ":")).encode("utf-8")
        pack_blob_name = f"{CACHE_PREFIX}/bootstrap/default-pack.json"
        blob = bucket.blob(pack_blob_name)
        blob.cache_control = "public, max-age=31536000, immutable"
        blob.content_encoding = "gzip"
        blob.upload_from_string(
            gzip.compress(encoded, compresslevel=6, mtime=0),
            content_type="application/json",
        )
        _memory_cache_put(pack_blob_name, payload)
        return True
    except Exception:
        logging.exception("Failed to publish the daily default snapshot pack")
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
    completed_only,
    data_version,
    subview=None,
    records_player=None,
    records_arena_only=False,
    records_tournament_only=False,
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
        "completed_only": completed_only,
        "records_player": records_player,
        "records_arena_only": bool(records_arena_only),
        "records_tournament_only": bool(records_tournament_only),
    }
    key_json = json.dumps(cache_key, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(key_json.encode("utf-8")).hexdigest()[:32]
    return f"{CACHE_PREFIX}/filters/{digest}.json"


def _is_default_cache_request(
    stats_page,
    maps_view,
    build_view,
    predictors_view,
    actions_view,
    is_mw,
    selected_maps,
    player_elo_min,
    player_elo_max,
    opponent_elo_min,
    opponent_elo_max,
    date_from,
    date_to,
    completed_only,
    round_filter_active,
    players_player=None,
    players_view=PLAYERS_VIEW_GENERAL,
    players_players=None,
    last_x_games=None,
    records_view=RECORDS_VIEW_ELO_LEADERBOARD,
    mw_action_cards_view=MW_ACTION_CARDS_VIEW_GENERAL,
    records_player=None,
    records_arena_only=False,
    records_tournament_only=False,
):
    if stats_page == STATS_PAGE_MW_ACTION_CARDS:
        return (
            int(is_mw) == 1
            and set(selected_maps) == set(VALID_MAPS)
            and player_elo_min == 300
            and player_elo_max is None
            and opponent_elo_min == 300
            and opponent_elo_max is None
            and date_from == DEFAULT_DATE_FROM
            and date_to is None
            and not completed_only
            and not round_filter_active
        )
    if stats_page == STATS_PAGE_MAPS and maps_view == MAPS_VIEW_TOURNAMENT_H2H:
        return int(is_mw) in (0, 1)
    if stats_page == STATS_PAGE_HOME:
        return (
            int(is_mw) in (0, 1)
            and set(selected_maps) == set(ALL_KNOWN_MAPS)
            and player_elo_min == 0
            and player_elo_max is None
            and opponent_elo_min == 0
            and opponent_elo_max is None
            and date_from is None
            and date_to is None
            and completed_only is None
            and not round_filter_active
        )
    if stats_page == STATS_PAGE_PLAYERS:
        return (
            players_view == PLAYERS_VIEW_GENERAL
            and int(is_mw) in (0, 1)
            and set(selected_maps) == set(ALL_KNOWN_MAPS)
            and player_elo_min is None
            and player_elo_max is None
            and opponent_elo_min == 0
            and opponent_elo_max is None
            and date_from is None
            and date_to is None
            and completed_only is None
            and not round_filter_active
            and not players_player
            and not players_players
            and not last_x_games
        )
    if stats_page == STATS_PAGE_RECORDS:
        return (
            records_view in VALID_RECORDS_VIEWS
            and int(is_mw) in (0, 1)
            and set(selected_maps) == set(ALL_KNOWN_MAPS)
            and player_elo_min is None
            and player_elo_max is None
            and opponent_elo_min is None
            and opponent_elo_max is None
            and date_from is None
            and date_to is None
            and completed_only is None
            and not records_player
            and not records_arena_only
            and not records_tournament_only
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
        and completed_only is None
        and not round_filter_active
    )


# BigQuery helpers


def _completed_game_sql(alias=None):
    """Canonical completed player-game predicate used across every data source."""
    prefix = f"{alias}." if alias else ""
    return (
        f"COALESCE({prefix}table_conceded, 0) = 0 "
        f"AND COALESCE(SAFE_CAST({prefix}end_game_triggered AS BOOL), FALSE) = TRUE"
    )


def _refresh_prepared_logs_table(arena_metadata=None):
    """Prepare logs with reusable completion, Arena, and Tournament classifications."""
    arena_metadata = arena_metadata or _load_arena_metadata()
    arena_season_case = _arena_season_case_sql(arena_metadata)
    query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_LOGS_TABLE}`
    PARTITION BY game_date
    CLUSTER BY is_mw, Map, arena_season, is_tournament
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
      f.game_date,
      f.concede,
      f.table_conceded,
      f.end_game_triggered,
      f.pre_match_elo,
      f.opponent_pre_match_elo,
      f.elo_delta,
      f.arena_season,
      f.is_tournament,
      f.starting_position,
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
      l.`1_size_enclosure_built` AS one_size_enclosure_built,
      l.`2_size_enclosure_built` AS two_size_enclosure_built,
      l.`3_size_enclosure_built` AS three_size_enclosure_built,
      l.`4_size_enclosure_built` AS four_size_enclosure_built,
      l.`5_size_enclosure_built` AS five_size_enclosure_built,
      l.aviary_built,
      l.reptile_house_built,
      l.large_aquarium_built,
      l.small_aquarium_built,
      l.association_starting_strength,
      l.build_starting_strength,
      l.cards_starting_strength,
      l.sponsors_starting_strength,
      l.association_action_history,
      l.cp_history,
      l.project_rewards,
      l.`5cp_bonus` AS five_cp_bonus,
      l.`8cp_bonus` AS eight_cp_bonus,
      l.has_round_1_upgrade,
      l.has_round_1_release,
      l.first_upgrade,
      l.second_upgrade,
      l.third_upgrade,
      l.fourth_upgrade,
      l.chosen_5cp_bonus,
      l.chosen_8cp_bonus,
      l.endgame_from_sponsors
    FROM `{PREPARED_FULL_STATS_TABLE}` f
    JOIN valid_log_ids v ON f.table_id = v.table_id
    JOIN `freestyle-190711.ark_nova.game_log_stat_v2` l
      ON f.table_id = l.table_id AND f.player = l.player
    """

    started_at = time.perf_counter()
    client = bigquery.Client(project=BIGQUERY_JOB_PROJECT)
    # BigQuery cannot replace a partitioned table when its clustering fields
    # change. Prepared Logs is rebuilt from source immediately after this drop.
    client.query(
        f"DROP TABLE IF EXISTS `{PREPARED_LOGS_TABLE}`",
        location=BIGQUERY_LOCATION,
    ).result()
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


def _refresh_prepared_full_stats_table(arena_metadata=None):
    """Materialize Full Sample with canonical pre-game Elo semantics.

    The source's legacy ``elo`` and ``opponent_elo`` fields represent mixed
    rating moments and must never enter dashboard statistics. Player Elo is
    the source ``pre_match_elo``. Opponent Elo is derived from the unique
    opposing player row's ``pre_match_elo``; malformed tables deliberately
    receive NULL rather than falling back to legacy metadata.
    """
    arena_metadata = arena_metadata or _load_arena_metadata()
    arena_season_case = _arena_season_case_sql(arena_metadata)
    query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_FULL_STATS_TABLE}`
    PARTITION BY game_date
    CLUSTER BY is_mw, Map, arena_season, is_tournament
    AS
    WITH source_rows AS (
      SELECT
        f.* EXCEPT(elo, opponent_elo, end_game_triggered),
        SAFE_CAST(f.pre_match_elo AS FLOAT64) AS canonical_pre_match_elo,
        SAFE_CAST(f.post_match_elo AS FLOAT64) AS canonical_post_match_elo,
        COALESCE(SAFE_CAST(f.end_game_triggered AS BOOL), FALSE)
          AS canonical_end_game_triggered
      FROM `freestyle-190711.ark_nova.all_games_stat` f
    ),
    player_ratings AS (
      SELECT
        table_id,
        CAST(player AS STRING) AS player,
        IF(
          COUNT(DISTINCT canonical_pre_match_elo) = 1,
          ANY_VALUE(canonical_pre_match_elo),
          CAST(NULL AS FLOAT64)
        ) AS pre_match_elo
      FROM source_rows
      GROUP BY table_id, player
    ),
    opponent_ratings AS (
      SELECT
        me.table_id,
        me.player,
        IF(
          COUNT(DISTINCT opponent.player) = 1,
          ANY_VALUE(opponent.pre_match_elo),
          CAST(NULL AS FLOAT64)
        ) AS opponent_pre_match_elo
      FROM player_ratings me
      LEFT JOIN player_ratings opponent
        ON me.table_id = opponent.table_id
       AND me.player != opponent.player
      GROUP BY me.table_id, me.player
    )
    SELECT
      f.* EXCEPT(
        pre_match_elo, post_match_elo, canonical_pre_match_elo,
        canonical_post_match_elo, canonical_end_game_triggered
      ),
      f.canonical_pre_match_elo AS pre_match_elo,
      f.canonical_post_match_elo AS post_match_elo,
      opponent.opponent_pre_match_elo,
      f.canonical_end_game_triggered AS end_game_triggered,
      CASE LOWER(TRIM(CAST(f.Starting_position_in_first_round AS STRING)))
        WHEN 'first player' THEN 'First player'
        WHEN 'second player' THEN 'Second player'
        ELSE NULL
      END AS starting_position,
      CAST(f.game_ended_at AS DATE) AS game_date,
      MAX(IF(COALESCE(f.concede, 0) != 0, 1, 0))
        OVER (PARTITION BY f.table_id) AS table_conceded,
      {arena_season_case} AS arena_season,
      EXISTS (
        SELECT 1
        FROM `{TOURNAMENT_TABLES_CACHE_TABLE}` t
        WHERE CAST(t.table_id AS STRING) = CAST(f.table_id AS STRING)
      ) AS is_tournament
    FROM source_rows f
    LEFT JOIN opponent_ratings opponent
      ON f.table_id = opponent.table_id
     AND CAST(f.player AS STRING) = opponent.player
    """

    started_at = time.perf_counter()
    client = bigquery.Client(project=BIGQUERY_JOB_PROJECT)
    # BigQuery cannot change a table's clustering fields through CREATE OR
    # REPLACE. This is a backend-owned derivative, so replace it explicitly;
    # the read-only Full Sample source above is never modified.
    client.query(
        f"DROP TABLE IF EXISTS `{PREPARED_FULL_STATS_TABLE}`",
        location=BIGQUERY_LOCATION,
    ).result()
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


def _enrich_and_write_records_manual_table(source_payload):
    """Enrich manual Records rows, then atomically replace the derived table.

    Fastest owns only Turns, Player, Score, ID, and EPT; every other field is
    sourced from the matching Full Sample player row. Biggest Turns retains its
    separate sheet-owned schema and its existing identity validation.
    """
    source_rows = [
        dict(item)
        for key in ("fastest_games", "biggest_turns")
        for item in (source_payload.get(key) or [])
    ]
    if not source_rows:
        raise ValueError("Manual Records source contains no rows")
    table_ids = sorted({item["table_id"] for item in source_rows})
    client = bigquery.Client(project=BIGQUERY_JOB_PROJECT)
    metadata_query = f"""
      SELECT
        CAST(table_id AS STRING) AS table_id,
        CAST(player AS STRING) AS player,
        CAST(Map AS STRING) AS map_name,
        CAST(is_mw AS INT64) AS is_mw,
        SAFE_CAST(game_ended_at AS TIMESTAMP) AS game_ended_at,
        SAFE_CAST(arena_rating_delta AS FLOAT64) AS arena_rating_delta,
        SAFE_CAST(opponent_pre_match_elo AS FLOAT64) AS opponent_pre_match_elo,
        SAFE_CAST(pre_match_elo AS FLOAT64) AS pre_match_elo,
        CAST(starting_position AS STRING) AS starting_position
      FROM `{PREPARED_FULL_STATS_TABLE}`
      WHERE CAST(table_id AS STRING) IN UNNEST(@table_ids)
    """
    metadata_job = client.query(
        metadata_query,
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ArrayQueryParameter("table_ids", "STRING", table_ids),
        ]),
        location=BIGQUERY_LOCATION,
    )
    metadata = {}
    table_metadata = {}
    for row in metadata_job.result():
        key = (str(row.table_id), str(row.player))
        if key in metadata:
            raise ValueError(f"Full Sample contains duplicate Records identity {key[0]}/{key[1]}")
        metadata[key] = row
        table_metadata.setdefault(str(row.table_id), []).append(row)

    map_by_name = {item["full"]: item for item in ALL_MAPS_FOR_METRICS}
    enriched = []
    for item in source_rows:
        key = (item["table_id"], item["player"])
        match = metadata.get(key)
        is_fastest = item["record_view"] == RECORDS_VIEW_FASTEST_GAMES
        if is_fastest:
            table_matches = table_metadata.get(item["table_id"], [])
            if not table_matches:
                raise ValueError(
                    f"Fastest Games row {item['source_row']} ID {item['table_id']} "
                    "does not exist in Full Sample"
                )
            # Player is sheet-owned and may intentionally differ from the
            # source spelling. Prefer exact per-player enrichment, but derive
            # display/filter identity from the table when no exact row exists.
            metadata_rows = [match] if match is not None else table_matches
            map_names = {str(row.map_name) for row in metadata_rows if row.map_name is not None}
            mode_values = {
                int(row.is_mw)
                for row in metadata_rows
                if row.is_mw is not None and int(row.is_mw) in (0, 1)
            }
            timestamps = {
                row.game_ended_at
                for row in metadata_rows
                if row.game_ended_at is not None
            }
            if len(map_names) != 1:
                raise ValueError(
                    f"Fastest Games row {item['source_row']} ID {item['table_id']} "
                    "has no unambiguous Full Sample map"
                )
            if len(mode_values) != 1:
                raise ValueError(
                    f"Fastest Games row {item['source_row']} ID {item['table_id']} "
                    "has no unambiguous Full Sample mode"
                )
            if len(timestamps) != 1:
                raise ValueError(
                    f"Fastest Games row {item['source_row']} ID {item['table_id']} "
                    "has no unambiguous Full Sample end timestamp"
                )
            source_map_name = next(iter(map_names))
            map_item = map_by_name.get(source_map_name)
            if map_item is None:
                raise ValueError(
                    f"Fastest Games row {item['source_row']} ID {item['table_id']} "
                    f"has unsupported Full Sample map {source_map_name!r}"
                )
            source_timestamp = next(iter(timestamps))
            is_mw = next(iter(mode_values))
            mode = "MW" if is_mw == 1 else "Base"
            map_name = map_item["full"]
            map_code = map_item["code"]
            game_date = source_timestamp.date().isoformat()
        else:
            # Biggest Turns remains sheet-owned. Exact upstream matches must
            # agree with its maintained dataset and map identity.
            if match is not None and int(match.is_mw) != int(item["is_mw"]):
                raise ValueError(
                    f"Biggest Turns row {item['source_row']} Mode {item['mode']} "
                    f"does not match Full Sample for ID {item['table_id']}"
                )
            if match is not None and str(match.map_name) != item["map_name"]:
                raise ValueError(
                    f"Biggest Turns row {item['source_row']} Map {item['map_code']} "
                    f"does not match Full Sample map {match.map_name!r}"
                )
            source_timestamp = match.game_ended_at if match is not None else None
            is_mw = int(item["is_mw"])
            mode = item["mode"]
            map_name = item["map_name"]
            map_code = item["map_code"]
            game_date = item["game_date"]
        enriched.append({
            "record_view": item["record_view"],
            "source_row": int(item["source_row"]),
            "is_mw": is_mw,
            "mode": mode,
            "player": item["player"],
            "table_id": item["table_id"],
            "Map": map_name,
            "map_code": map_code,
            "game_date": game_date,
            "game_ended_at": (
                source_timestamp.isoformat()
                if source_timestamp is not None
                else f"{game_date}T00:00:00+00:00"
            ),
            "turns": item.get("turns"),
            "score": item.get("score"),
            "ept": item.get("ept"),
            "flat": item.get("flat"),
            "end": item.get("end"),
            "total": item.get("total"),
            "move": item.get("move"),
            "actions": item.get("actions"),
            "result_code": item.get("result_code"),
            "opponent_pre_match_elo": match.opponent_pre_match_elo if match is not None else None,
            "pre_match_elo": match.pre_match_elo if match is not None else None,
            "starting_position": match.starting_position if match is not None else None,
            "arena_rating_delta": (
                match.arena_rating_delta
                if match is not None
                else next(
                    (
                        row.arena_rating_delta
                        for row in table_metadata.get(item["table_id"], [])
                        if row.arena_rating_delta is not None
                    ),
                    None,
                )
                if is_fastest
                else None
            ),
            "source_enriched": (
                match is not None
                or (
                    is_fastest
                    and bool(table_metadata.get(item["table_id"]))
                )
            ),
        })

    schema = [
        bigquery.SchemaField("record_view", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("source_row", "INT64", mode="REQUIRED"),
        bigquery.SchemaField("is_mw", "INT64", mode="REQUIRED"),
        bigquery.SchemaField("mode", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("player", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("table_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("Map", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("map_code", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("game_date", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("game_ended_at", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("turns", "INT64"),
        bigquery.SchemaField("score", "INT64"),
        bigquery.SchemaField("ept", "INT64"),
        bigquery.SchemaField("flat", "INT64"),
        bigquery.SchemaField("end", "INT64"),
        bigquery.SchemaField("total", "INT64"),
        bigquery.SchemaField("move", "INT64"),
        bigquery.SchemaField("actions", "INT64"),
        bigquery.SchemaField("result_code", "STRING"),
        bigquery.SchemaField("starting_position", "STRING"),
        bigquery.SchemaField("opponent_pre_match_elo", "FLOAT64"),
        bigquery.SchemaField("pre_match_elo", "FLOAT64"),
        bigquery.SchemaField("arena_rating_delta", "FLOAT64"),
        bigquery.SchemaField("source_enriched", "BOOLEAN", mode="REQUIRED"),
    ]
    load_config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        time_partitioning=bigquery.TimePartitioning(field="game_date"),
        clustering_fields=["record_view", "is_mw", "Map"],
    )
    load_job = client.load_table_from_json(
        enriched,
        PREPARED_RECORDS_MANUAL_TABLE,
        job_config=load_config,
        location=BIGQUERY_LOCATION,
    )
    load_job.result()
    return {
        "status": "ok",
        "prepared_table": PREPARED_RECORDS_MANUAL_TABLE,
        "rows": len(enriched),
        "fastest_games": sum(item["record_view"] == RECORDS_VIEW_FASTEST_GAMES for item in enriched),
        "biggest_turns": sum(item["record_view"] == RECORDS_VIEW_BIGGEST_TURNS for item in enriched),
        "source_enriched": sum(bool(item["source_enriched"]) for item in enriched),
        "source_absent": sum(not bool(item["source_enriched"]) for item in enriched),
        "metadata_job_id": metadata_job.job_id,
        "job_id": load_job.job_id,
    }


def _refresh_prepared_records_manual_table():
    """Refresh Google-Sheet Records data, falling back only to fully validated cached rows."""
    global _RECORDS_MANUAL_SOURCE
    live_error = None
    try:
        candidate = _fetch_records_manual_source()
        result = _enrich_and_write_records_manual_table(candidate)
        if not _write_cache_blob(RECORDS_MANUAL_CACHE_BLOB, candidate, "refreshed"):
            raise RuntimeError("Could not persist validated manual Records source")
        _RECORDS_MANUAL_SOURCE = candidate
        result["source_status"] = "live"
        result["source_sha256"] = candidate.get("source_sha256")
        return result
    except Exception as exc:
        live_error = exc
        logging.exception("Failed to refresh manual Records data from Google Sheets")

    cached = _cached_records_manual_source()
    if not cached:
        raise RuntimeError("Manual Records data is unavailable and no validated cache exists") from live_error
    result = _enrich_and_write_records_manual_table(cached)
    _RECORDS_MANUAL_SOURCE = cached
    result["source_status"] = "cached"
    result["source_sha256"] = cached.get("source_sha256")
    result["live_error"] = str(live_error)
    return result


def _arena_season_case_sql(metadata, alias="f"):
    branches = []
    for season in metadata.get("seasons", []):
        branches.append(
            "WHEN SAFE_CAST({a}.arena_rating_delta AS FLOAT64) IS NOT NULL "
            "AND CAST({a}.is_mw AS INT64) = {is_mw} "
            "AND SAFE_CAST({a}.game_ended_at AS TIMESTAMP) >= TIMESTAMP({start}) "
            "AND SAFE_CAST({a}.game_ended_at AS TIMESTAMP) < TIMESTAMP({end}) "
            "THEN {season}".format(
                a=alias,
                is_mw=int(season["is_mw"]),
                start=_sql_string(season["start_utc"]),
                end=_sql_string(season["effective_end_utc"]),
                season=_sql_string(season["season"]),
            )
        )
    return "CASE\n        " + "\n        ".join(branches) + "\n        ELSE NULL END"


def _refresh_prepared_players_table(arena_metadata=None, merge_metadata=None):
    """Build the narrow player-game table used by Players aggregations.

    Full Sample remains read-only. Expensive per-game formulas and winner
    pairing are materialized here once per daily refresh so interactive queries
    scan only the columns they actually need.
    """
    arena_metadata = arena_metadata or _load_arena_metadata()
    merge_metadata = merge_metadata or _load_merge_players_metadata()
    arena_season_case = _arena_season_case_sql(arena_metadata)
    merge_players_map = _merge_players_map_cte(merge_metadata)
    definitions = _players_metric_definitions()
    expressions = _players_metric_expressions()
    money_fields = _players_money_fields()
    ordinary_keys = [key for key, *_ in definitions if key not in money_fields]
    metric_selects = ",\n      ".join(
        f"{expressions[key]} AS {key}" for key in ordinary_keys
    )
    money_selects = ",\n      ".join(
        f"SAFE_CAST({source} AS FLOAT64) AS {key}_raw"
        for key, source in money_fields.items()
    )
    query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_PLAYERS_TABLE}`
    PARTITION BY game_date
    -- The merged analytical identity leads the clustering order because one
    -- selected BGA name may resolve to several historical accounts. Dataset,
    -- map, and opponent Elo still prune the common filtered scans.
    CLUSTER BY player_identity, is_mw, Map, arena_season
    AS
    WITH player_merge_map AS (
      {merge_players_map}
    ),
    tagged AS (
      SELECT
        f.*,
        COUNTIF(SAFE_CAST(f.Game_result AS INT64) = 1)
          OVER (PARTITION BY f.table_id) AS result_one_count,
        COUNTIF(SAFE_CAST(f.Game_result AS INT64) = 2)
          OVER (PARTITION BY f.table_id) AS result_two_count,
        COUNT(*) OVER (PARTITION BY f.table_id) AS result_row_count
      FROM `{PREPARED_FULL_STATS_TABLE}` f
    )
    SELECT
      table_id,
      CAST(f.player AS STRING) AS player,
      COALESCE(
        m.player_identity,
        CONCAT('player:', CAST(f.player AS STRING))
      ) AS player_identity,
      CAST(is_mw AS INT64) AS is_mw,
      Map,
      SAFE_CAST(game_ended_at AS TIMESTAMP) AS game_ended_at,
      game_date,
      SAFE_CAST(pre_match_elo AS FLOAT64) AS pre_match_elo,
      SAFE_CAST(elo_delta AS FLOAT64) AS elo_delta,
      SAFE_CAST(opponent_pre_match_elo AS FLOAT64) AS opponent_pre_match_elo,
      CAST(COALESCE(table_conceded, 0) AS INT64) AS table_conceded,
      COALESCE(SAFE_CAST(end_game_triggered AS BOOL), FALSE)
        AS end_game_triggered,
      result_row_count = 2 AND SAFE_CAST(Game_result AS INT64) = 1 AND result_two_count = 1 AS is_winner,
      CASE
        WHEN result_row_count = 2 AND SAFE_CAST(Game_result AS INT64) = 1 AND result_two_count = 1 THEN 1.0
        WHEN result_row_count = 2 AND SAFE_CAST(Game_result AS INT64) = 2 AND result_one_count = 1 THEN 0.0
        WHEN result_row_count = 2 AND SAFE_CAST(Game_result AS INT64) = 1 AND result_one_count = 2 THEN 0.5
        ELSE CAST(NULL AS FLOAT64)
      END AS arena_game_score,
      SAFE_CAST(arena_rating_delta AS FLOAT64) AS arena_rating_delta,
      SAFE_CAST(post_match_arena_rating AS FLOAT64) AS post_match_arena_rating,
      {arena_season_case} AS arena_season,
      COALESCE(is_tournament, FALSE) AS is_tournament,
      starting_position,
      {metric_selects},
      {money_selects}
    FROM tagged f
    LEFT JOIN player_merge_map m
      ON CAST(f.player AS STRING) = m.player
    """

    started_at = time.perf_counter()
    client = bigquery.Client(project=BIGQUERY_JOB_PROJECT)
    # BigQuery cannot change clustering order through CREATE OR REPLACE. This
    # table is a backend-owned derivative, so nightly maintenance replaces it;
    # Full Sample remains untouched.
    client.query(
        f"DROP TABLE IF EXISTS `{PREPARED_PLAYERS_TABLE}`",
        location=BIGQUERY_LOCATION,
    ).result()
    job = client.query(query, location=BIGQUERY_LOCATION)
    job.result()
    # Last X deliberately has no date predicate, so the date-partitioned table
    # above would have to visit every daily partition before ranking one merged
    # identity. Hash-partition the exact rows by merged identity for that path.
    # A request supplies the one matching bucket, allowing partition pruning
    # before map/Elo filters and the final timestamp rank.
    recent_query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_PLAYERS_RECENT_TABLE}`
    PARTITION BY RANGE_BUCKET(identity_bucket, GENERATE_ARRAY(0, 1024, 1))
    CLUSTER BY player_identity, is_mw, Map, arena_season
    AS
    SELECT
      MOD(
        CAST(CONCAT(
          '0x', SUBSTR(TO_HEX(SHA256(player_identity)), 1, 8)
        ) AS INT64),
        1024
      ) AS identity_bucket,
      f.*
    FROM `{PREPARED_PLAYERS_TABLE}` f
    """
    client.query(
        f"DROP TABLE IF EXISTS `{PREPARED_PLAYERS_RECENT_TABLE}`",
        location=BIGQUERY_LOCATION,
    ).result()
    recent_job = client.query(recent_query, location=BIGQUERY_LOCATION)
    recent_job.result()
    # Players filters aggregate averages, so daily sums and valid-value counts
    # are sufficient whenever Last X is inactive. The baseline rollup drops
    # identity entirely; the identity rollup retains exact accounts so merged
    # account count breakdowns remain correct.
    rollup_metric_keys = ordinary_keys + [
        f"{key}_raw" for key in money_fields
    ]
    rollup_moments = ",\n      ".join(
        expression
        for key in rollup_metric_keys
        for expression in (
            f"SUM({key}) AS {key}_sum",
            f"COUNT({key}) AS {key}_count",
        )
    )
    baseline_query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_PLAYERS_BASELINE_TABLE}`
    PARTITION BY game_date
    CLUSTER BY is_mw, Map, arena_season, is_tournament
    AS
    SELECT
      is_mw,
      Map,
      game_date,
      opponent_pre_match_elo,
      arena_season,
      is_tournament,
      starting_position,
      0 AS table_conceded,
      TRUE AS end_game_triggered,
      is_winner,
      pre_match_elo >= 500 AS is_expert,
      pre_match_elo >= 700 AS is_master,
      COUNT(*) AS observation_count,
      {rollup_moments}
    FROM `{PREPARED_PLAYERS_TABLE}`
    WHERE {_completed_game_sql()}
    GROUP BY
      is_mw, Map, game_date, opponent_pre_match_elo, arena_season, is_tournament, starting_position,
      is_winner, pre_match_elo >= 500, pre_match_elo >= 700
    """
    client.query(
        f"DROP TABLE IF EXISTS `{PREPARED_PLAYERS_BASELINE_TABLE}`",
        location=BIGQUERY_LOCATION,
    ).result()
    baseline_job = client.query(baseline_query, location=BIGQUERY_LOCATION)
    baseline_job.result()
    identity_rollup_query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_PLAYERS_IDENTITY_ROLLUP_TABLE}`
    PARTITION BY game_date
    CLUSTER BY player_identity, is_mw, Map, arena_season
    AS
    SELECT
      player_identity,
      player,
      is_mw,
      Map,
      game_date,
      opponent_pre_match_elo,
      arena_season,
      is_tournament,
      starting_position,
      0 AS table_conceded,
      TRUE AS end_game_triggered,
      COUNT(*) AS observation_count,
      {rollup_moments}
    FROM `{PREPARED_PLAYERS_TABLE}`
    WHERE {_completed_game_sql()}
    GROUP BY
      player_identity, player, is_mw, Map, game_date, opponent_pre_match_elo,
      arena_season, is_tournament, starting_position
    """
    client.query(
        f"DROP TABLE IF EXISTS `{PREPARED_PLAYERS_IDENTITY_ROLLUP_TABLE}`",
        location=BIGQUERY_LOCATION,
    ).result()
    identity_rollup_job = client.query(
        identity_rollup_query, location=BIGQUERY_LOCATION
    )
    identity_rollup_job.result()
    # Performance by map defaults to every qualifying game, unlike General
    # and Comparison. Keep completion as a dimension so its optional toggle
    # remains exact without scanning the player-game table.
    map_rollup_query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_PLAYERS_MAP_ROLLUP_TABLE}`
    PARTITION BY game_date
    CLUSTER BY player_identity, is_mw, Map, arena_season
    AS
    SELECT
      player_identity,
      is_mw,
      Map,
      game_date,
      opponent_pre_match_elo,
      arena_season,
      is_tournament,
      starting_position,
      table_conceded,
      end_game_triggered,
      COUNT(elo_delta) AS delta_count,
      SUM(elo_delta) AS delta_sum,
      SUM(POW(elo_delta, 2)) AS delta_sum_squares
    FROM `{PREPARED_PLAYERS_TABLE}`
    GROUP BY
      player_identity, is_mw, Map, game_date, opponent_pre_match_elo,
      arena_season, is_tournament, starting_position, table_conceded, end_game_triggered
    """
    client.query(
        f"DROP TABLE IF EXISTS `{PREPARED_PLAYERS_MAP_ROLLUP_TABLE}`",
        location=BIGQUERY_LOCATION,
    ).result()
    map_rollup_job = client.query(map_rollup_query, location=BIGQUERY_LOCATION)
    map_rollup_job.result()
    default_selects = ",\n      ".join(
        [f"AVG({key}) AS {key}" for key in ordinary_keys]
        + [f"AVG({key}_raw) AS {key}_raw" for key in money_fields]
    )
    all_maps_sql = ", ".join(_sql_string(value) for value in ALL_KNOWN_MAPS)
    default_query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_PLAYERS_DEFAULT_TABLE}`
    CLUSTER BY player_identity, is_mw
    AS
    WITH scoped AS (
      SELECT *
      FROM `{PREPARED_PLAYERS_TABLE}`
      WHERE {_completed_game_sql()}
        -- Elo NULLs are unknown metadata, not zero-valued observations. The
        -- dashboard treats them as zero only while evaluating range filters,
        -- so the unrestricted Players default retains those games without
        -- altering metric averages or expert/master classifications.
        AND COALESCE(opponent_pre_match_elo, 0) >= 0
        AND Map IN ({all_maps_sql})
    ),
    identity_aggregates AS (
      SELECT
        player_identity,
        is_mw,
        COUNT(*) AS game_count,
        {default_selects}
      FROM scoped
      GROUP BY player_identity, is_mw
    ),
    per_account AS (
      SELECT player_identity, is_mw, player, COUNT(*) AS game_count
      FROM scoped
      GROUP BY player_identity, is_mw, player
    ),
    account_summaries AS (
      SELECT
        player_identity,
        is_mw,
        ARRAY_AGG(
          STRUCT(player AS name, game_count AS game_count)
          ORDER BY player
        ) AS account_counts
      FROM per_account
      GROUP BY player_identity, is_mw
    )
    SELECT a.*, s.account_counts
    FROM identity_aggregates a
    JOIN account_summaries s USING(player_identity, is_mw)
    """
    # The clustering key changes from exact account to merged identity. This is
    # a backend-owned derivative, so replace it explicitly just like the
    # player-game prepared table above.
    client.query(
        f"DROP TABLE IF EXISTS `{PREPARED_PLAYERS_DEFAULT_TABLE}`",
        location=BIGQUERY_LOCATION,
    ).result()
    default_job = client.query(default_query, location=BIGQUERY_LOCATION)
    default_job.result()
    return {
        "status": "ok",
        "prepared_table": PREPARED_PLAYERS_TABLE,
        "recent_prepared_table": PREPARED_PLAYERS_RECENT_TABLE,
        "total_ms": _ms_since(started_at),
        "job_id": job.job_id,
        "job_created": _dt_iso(job.created),
        "job_started": _dt_iso(job.started),
        "job_ended": _dt_iso(job.ended),
        "job_total_bytes_processed": job.total_bytes_processed,
        "job_total_slot_ms": job.slot_millis,
        "default_prepared_table": PREPARED_PLAYERS_DEFAULT_TABLE,
        "default_job_id": default_job.job_id,
        "baseline_prepared_table": PREPARED_PLAYERS_BASELINE_TABLE,
        "baseline_job_id": baseline_job.job_id,
        "identity_rollup_table": PREPARED_PLAYERS_IDENTITY_ROLLUP_TABLE,
        "identity_rollup_job_id": identity_rollup_job.job_id,
        "map_performance_rollup_table": PREPARED_PLAYERS_MAP_ROLLUP_TABLE,
        "map_performance_rollup_job_id": map_rollup_job.job_id,
        "merge_groups": len(merge_metadata.get("groups", [])),
        "merge_source_sha256": merge_metadata.get("source_sha256"),
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
        table_id, player, is_mw, Map, game_date, table_conceded,
        end_game_triggered,
        arena_season, is_tournament, starting_position,
        pre_match_elo, opponent_pre_match_elo, elo_delta,
        pa.animal AS card_name,
        'animal' AS card_type,
        SAFE_CAST(pa.round AS INT64) AS played_round
      FROM `{PREPARED_LOGS_TABLE}`
      CROSS JOIN UNNEST(IFNULL(played_animals, [])) AS pa
      WHERE pa.animal IS NOT NULL

      UNION ALL

      SELECT
        table_id, player, is_mw, Map, game_date, table_conceded,
        end_game_triggered,
        arena_season, is_tournament, starting_position,
        pre_match_elo, opponent_pre_match_elo, elo_delta,
        ps.sponsor AS card_name,
        'sponsor' AS card_type,
        SAFE_CAST(ps.round AS INT64) AS played_round
      FROM `{PREPARED_LOGS_TABLE}`
      CROSS JOIN UNNEST(IFNULL(played_sponsors, [])) AS ps
      WHERE ps.sponsor IS NOT NULL

      UNION ALL

      SELECT
        table_id, player, is_mw, Map, game_date, table_conceded,
        end_game_triggered,
        arena_season, is_tournament, starting_position,
        pre_match_elo, opponent_pre_match_elo, elo_delta,
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
        table_id, player, is_mw, Map, game_date, table_conceded,
        end_game_triggered,
        arena_season, is_tournament, starting_position,
        pre_match_elo, opponent_pre_match_elo, elo_delta, card_name, ANY_VALUE(card_type) AS card_type,
        ARRAY_AGG(DISTINCT played_round IGNORE NULLS) AS played_rounds
      FROM `{PREPARED_CARD_PLAYS_TABLE}`
      GROUP BY
        table_id, player, is_mw, Map, game_date, table_conceded,
        end_game_triggered,
        arena_season, is_tournament, starting_position,
        pre_match_elo, opponent_pre_match_elo, elo_delta, card_name
    )
    SELECT
      a.table_id,
      a.player,
      a.is_mw,
      a.Map,
      a.game_date,
      a.table_conceded,
      a.end_game_triggered,
      a.arena_season,
      a.is_tournament,
      a.starting_position,
      a.pre_match_elo,
      a.opponent_pre_match_elo,
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


def _refresh_prepared_card_play_aggregates_table():
    """Collapse card observations into daily filter dimensions and moments."""
    query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_CARD_PLAY_AGGREGATES_TABLE}`
    PARTITION BY game_date
    CLUSTER BY is_mw, card_name, Map, played_round
    AS
    SELECT
      is_mw,
      Map,
      game_date,
      table_conceded,
      end_game_triggered,
      arena_season,
      is_tournament,
      starting_position,
      SAFE_CAST(pre_match_elo AS FLOAT64) AS pre_match_elo,
      SAFE_CAST(opponent_pre_match_elo AS FLOAT64) AS opponent_pre_match_elo,
      card_name,
      ANY_VALUE(card_type) AS card_type,
      played_round,
      COUNT(*) AS observation_count,
      COUNT(elo_delta) AS delta_count,
      SUM(SAFE_CAST(elo_delta AS FLOAT64)) AS delta_sum
    FROM `{PREPARED_CARD_PLAYS_TABLE}`
    GROUP BY
      is_mw, Map, game_date, table_conceded, end_game_triggered,
      arena_season, is_tournament, starting_position,
      SAFE_CAST(pre_match_elo AS FLOAT64), SAFE_CAST(opponent_pre_match_elo AS FLOAT64),
      card_name, played_round
    """
    started_at = time.perf_counter()
    client = bigquery.Client(project=BIGQUERY_JOB_PROJECT)
    job = client.query(query, location=BIGQUERY_LOCATION)
    job.result()
    return {
        "status": "ok",
        "prepared_table": PREPARED_CARD_PLAY_AGGREGATES_TABLE,
        "total_ms": _ms_since(started_at),
        "job_id": job.job_id,
        "job_total_bytes_processed": job.total_bytes_processed,
        "job_total_slot_ms": job.slot_millis,
    }


def _refresh_prepared_card_pair_aggregates_table():
    """Collapse pair observations into daily filter dimensions and moments.

    Counts, sums, and squared sums preserve weighted averages and sample
    standard deviations without retaining one physical row per player-game
    pair in the interactive query source.
    """
    query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_CARD_PAIR_AGGREGATES_TABLE}`
    PARTITION BY game_date
    CLUSTER BY is_mw, card_1, card_2, Map
    AS
    SELECT
      is_mw,
      Map,
      game_date,
      table_conceded,
      end_game_triggered,
      arena_season,
      is_tournament,
      starting_position,
      SAFE_CAST(pre_match_elo AS FLOAT64) AS pre_match_elo,
      SAFE_CAST(opponent_pre_match_elo AS FLOAT64) AS opponent_pre_match_elo,
      card_1,
      ANY_VALUE(type_1) AS type_1,
      card_2,
      ANY_VALUE(type_2) AS type_2,
      TO_JSON_STRING(played_rounds_1) AS played_rounds_1_json,
      TO_JSON_STRING(played_rounds_2) AS played_rounds_2_json,
      COUNT(*) AS observation_count,
      COUNT(elo_delta) AS delta_count,
      SUM(SAFE_CAST(elo_delta AS FLOAT64)) AS delta_sum,
      SUM(POW(SAFE_CAST(elo_delta AS FLOAT64), 2)) AS delta_sum_squares,
      COUNT(pre_match_elo) AS elo_count,
      SUM(SAFE_CAST(pre_match_elo AS FLOAT64)) AS elo_sum
    FROM `{PREPARED_CARD_PAIRS_TABLE}`
    GROUP BY
      is_mw, Map, game_date, table_conceded, end_game_triggered,
      arena_season, is_tournament, starting_position,
      SAFE_CAST(pre_match_elo AS FLOAT64), SAFE_CAST(opponent_pre_match_elo AS FLOAT64),
      card_1, card_2, played_rounds_1_json, played_rounds_2_json
    """
    started_at = time.perf_counter()
    client = bigquery.Client(project=BIGQUERY_JOB_PROJECT)
    job = client.query(query, location=BIGQUERY_LOCATION)
    job.result()
    return {
        "status": "ok",
        "prepared_table": PREPARED_CARD_PAIR_AGGREGATES_TABLE,
        "total_ms": _ms_since(started_at),
        "job_id": job.job_id,
        "job_total_bytes_processed": job.total_bytes_processed,
        "job_total_slot_ms": job.slot_millis,
    }


def _refresh_prepared_card_pair_scope_aggregates_table():
    """Build the no-round pair source used by the common Card + Card path.

    The round JSON dimension multiplies the daily aggregate substantially.  It
    is necessary only when a round filter is active, so ordinary requests scan
    this second, much narrower table while retaining exact Elo/date/map filters.
    """
    query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_CARD_PAIR_SCOPE_AGGREGATES_TABLE}`
    PARTITION BY game_date
    CLUSTER BY is_mw, card_1, card_2, Map
    AS
    SELECT
      is_mw, Map, game_date, table_conceded, end_game_triggered,
      arena_season, is_tournament, starting_position, pre_match_elo, opponent_pre_match_elo,
      card_1, ANY_VALUE(type_1) AS type_1,
      card_2, ANY_VALUE(type_2) AS type_2,
      SUM(observation_count) AS observation_count,
      SUM(delta_count) AS delta_count,
      SUM(delta_sum) AS delta_sum,
      SUM(delta_sum_squares) AS delta_sum_squares,
      SUM(elo_count) AS elo_count,
      SUM(elo_sum) AS elo_sum
    FROM `{PREPARED_CARD_PAIR_AGGREGATES_TABLE}`
    GROUP BY
      is_mw, Map, game_date, table_conceded, end_game_triggered,
      arena_season, is_tournament, starting_position, pre_match_elo, opponent_pre_match_elo, card_1, card_2
    """
    started_at = time.perf_counter()
    client = bigquery.Client(project=BIGQUERY_JOB_PROJECT)
    job = client.query(query, location=BIGQUERY_LOCATION)
    job.result()
    return {
        "status": "ok",
        "prepared_table": PREPARED_CARD_PAIR_SCOPE_AGGREGATES_TABLE,
        "total_ms": _ms_since(started_at),
        "job_id": job.job_id,
        "job_total_bytes_processed": job.total_bytes_processed,
        "job_total_slot_ms": job.slot_millis,
    }


def _refresh_prepared_home_observations_table():
    """Resolve Home's array and opponent checks once during daily refresh."""
    query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_HOME_OBSERVATIONS_TABLE}`
    PARTITION BY game_date
    CLUSTER BY is_mw, Map, arena_season, is_tournament
    AS
    WITH log_flags AS (
      SELECT
        l.*,
        (SELECT COUNT(*) FROM UNNEST(IFNULL(l.played_animals, [])) pa
          WHERE pa.animal = 'Emu') AS emus_played,
        COALESCE(l.two_cp_worker, FALSE) AS two_cp_workers_taken,
        IF(l.chosen_5cp_bonus IN ('1 University', '1 Partner-Zoo'), 1, 0)
          + IF(l.chosen_8cp_bonus IN ('1 University', '1 Partner-Zoo'), 1, 0)
          AS free_unis_and_partner_zoos,
        IF(
          'Primates' IN UNNEST(IFNULL(l.cards_drawn, []))
          AND NOT EXISTS (
            SELECT 1 FROM UNNEST(IFNULL(l.played_projects, [])) pp
            WHERE pp.project = 'Primates'
          ), 1, 0
        ) AS primates_block_candidate
      FROM `{PREPARED_LOGS_TABLE}` l
    ),
    log_ready AS (
      SELECT
        l.*,
        IF(
          l.primates_block_candidate = 1
          AND EXISTS (
            SELECT 1
            FROM log_flags other
            WHERE other.table_id = l.table_id
              AND other.player != l.player
              AND EXISTS (
                SELECT 1 FROM UNNEST(IFNULL(other.played_animals, [])) pa
                WHERE pa.animal = 'Proboscis Monkey'
              )
          ), 1, 0
        ) AS bignose_project_blocks
      FROM log_flags l
    )
    SELECT
      f.is_mw, f.Map, f.game_date, f.table_conceded, f.end_game_triggered,
      f.arena_season, f.is_tournament, f.table_id, f.player, f.starting_position,
      f.pre_match_elo,
      SAFE_CAST(f.opponent_pre_match_elo AS FLOAT64) AS opponent_pre_match_elo,
      COALESCE(SAFE_CAST(f.Played_animals AS INT64), 0) AS animals_played,
      COALESCE(SAFE_CAST(f.Played_sponsors AS INT64), 0) AS sponsors_played,
      COALESCE(SAFE_CAST(f.Conservation_project_association_tasks AS INT64), 0)
        AS projects_supported,
      COALESCE(SAFE_CAST(f.Number_of_breaks_triggered AS INT64), 0)
        AS breaks_triggered,
      COALESCE(SAFE_CAST(f.X_Tokens_gained AS INT64), 0) AS x_tokens_gained,
      l.player IS NOT NULL AS has_log,
      COALESCE(l.emus_played, 0) AS emus_played,
      IF(COALESCE(l.two_cp_workers_taken, FALSE), 1, 0) AS two_cp_workers_taken,
      IF(
        COALESCE(l.petting_zoo_built, 0) = 1
        AND COALESCE(f.Petting_Zoo_icons, 0) = 0
        AND NOT EXISTS (
          SELECT 1 FROM UNNEST(IFNULL(l.played_sponsors, [])) ps
          WHERE ps.sponsor = 'Horse Whisperer'
        ), 1, 0
      ) AS empty_petting_zoos_played,
      COALESCE(l.free_unis_and_partner_zoos, 0) AS free_unis_and_partner_zoos,
      COALESCE(l.bignose_project_blocks, 0) AS bignose_project_blocks
    FROM `{PREPARED_FULL_STATS_TABLE}` f
    LEFT JOIN log_ready l USING(table_id, player)
    """
    started_at = time.perf_counter()
    client = bigquery.Client(project=BIGQUERY_JOB_PROJECT)
    # The canonical Elo migration removes FLOAT64 rating fields from the
    # clustering specification. BigQuery cannot alter clustering through
    # CREATE OR REPLACE, so explicitly replace this backend-owned derivative.
    client.query(
        f"DROP TABLE IF EXISTS `{PREPARED_HOME_OBSERVATIONS_TABLE}`",
        location=BIGQUERY_LOCATION,
    ).result()
    job = client.query(query, location=BIGQUERY_LOCATION)
    job.result()
    return {
        "status": "ok",
        "prepared_table": PREPARED_HOME_OBSERVATIONS_TABLE,
        "total_ms": _ms_since(started_at),
        "job_id": job.job_id,
        "job_total_bytes_processed": job.total_bytes_processed,
        "job_total_slot_ms": job.slot_millis,
    }


def _refresh_prepared_endgame_events_table():
    """Resolve endgame ownership once per refresh, not once per request.

    Marine Worlds logs can store dealt cards on the opposite player row.  The
    three event roles below preserve the old General-table semantics exactly:
    raw dealt counts, ownership-corrected dealt Delta observations, and scored
    observations (including CP).
    """
    query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_ENDGAME_EVENTS_TABLE}`
    PARTITION BY game_date
    CLUSTER BY is_mw, Map, event_role, card_name
    AS
    WITH completed AS (
      SELECT *
      FROM `{PREPARED_LOGS_TABLE}`
      WHERE {_completed_game_sql()}
    ),
    players AS (
      SELECT DISTINCT table_id, player, starting_position FROM completed
    ),
    dealt AS (
      SELECT
        c.* EXCEPT(endgame, endgame_scores),
        c.player AS dealt_row_player,
        TRIM(card) AS card_name
      FROM completed c
      CROSS JOIN UNNEST(IFNULL(c.endgame, [])) AS card
      WHERE TRIM(card) != ''
    ),
    scored AS (
      SELECT
        c.* EXCEPT(endgame, endgame_scores),
        TRIM(score.endgame) AS card_name,
        SAFE_CAST(score.cp AS FLOAT64) AS cp
      FROM completed c
      CROSS JOIN UNNEST(IFNULL(c.endgame_scores, [])) AS score
      WHERE TRIM(score.endgame) != ''
    ),
    orientation_flags AS (
      SELECT
        p.table_id,
        p.player,
        EXISTS (
          SELECT 1 FROM dealt d JOIN scored s
            ON d.table_id = s.table_id
           AND d.dealt_row_player = s.player
           AND d.card_name = s.card_name
          WHERE d.table_id = p.table_id AND d.dealt_row_player = p.player
        ) AS own_match,
        EXISTS (
          SELECT 1 FROM dealt d JOIN scored s
            ON d.table_id = s.table_id
           AND d.dealt_row_player != s.player
           AND d.card_name = s.card_name
          WHERE d.table_id = p.table_id AND d.dealt_row_player = p.player
        ) AS swapped_match
      FROM players p
    ),
    orientation AS (
      SELECT
        table_id,
        CASE
          WHEN COUNT(*) = 2 AND COUNTIF(own_match) > COUNTIF(swapped_match) THEN 'same'
          WHEN COUNT(*) = 2 AND COUNTIF(swapped_match) > COUNTIF(own_match) THEN 'swapped'
          ELSE 'ambiguous'
        END AS orientation
      FROM orientation_flags
      GROUP BY table_id
    ),
    corrected_dealt AS (
      SELECT d.* EXCEPT(player, starting_position), d.player, d.starting_position
      FROM dealt d
      WHERE d.is_mw = 0

      UNION ALL

      SELECT d.* EXCEPT(player, starting_position), p.player, p.starting_position
      FROM dealt d
      JOIN orientation o USING(table_id)
      JOIN players p
        ON d.table_id = p.table_id
       AND (
         (o.orientation = 'same' AND d.dealt_row_player = p.player)
         OR (o.orientation = 'swapped' AND d.dealt_row_player != p.player)
       )
      WHERE d.is_mw = 1
    ),
    eligible_dealt_delta AS (
      SELECT cd.*
      FROM corrected_dealt cd
      WHERE cd.is_mw = 0 OR EXISTS (
        SELECT 1 FROM scored s
        WHERE cd.table_id = s.table_id
          AND cd.player = s.player
          AND cd.card_name = s.card_name
      )
    ),
    raw_dealt_events AS (
      SELECT
        is_mw, Map, game_date, table_conceded, end_game_triggered,
        arena_season, is_tournament, table_id, dealt_row_player AS player,
        starting_position,
        pre_match_elo, opponent_pre_match_elo, elo_delta, card_name,
        'dealt' AS event_role, CAST(NULL AS FLOAT64) AS cp
      FROM dealt
    ),
    dealt_delta_events AS (
      SELECT
        is_mw, Map, game_date, table_conceded, end_game_triggered,
        arena_season, is_tournament, table_id, player, starting_position,
        pre_match_elo, opponent_pre_match_elo, elo_delta, card_name,
        'dealt_delta' AS event_role, CAST(NULL AS FLOAT64) AS cp
      FROM eligible_dealt_delta
    ),
    scored_events AS (
      SELECT
        is_mw, Map, game_date, table_conceded, end_game_triggered,
        arena_season, is_tournament, table_id, player, starting_position,
        pre_match_elo, opponent_pre_match_elo, elo_delta, card_name,
        'scored' AS event_role, cp
      FROM scored
    )
    SELECT * FROM raw_dealt_events
    UNION ALL SELECT * FROM dealt_delta_events
    UNION ALL SELECT * FROM scored_events
    """
    started_at = time.perf_counter()
    client = bigquery.Client(project=BIGQUERY_JOB_PROJECT)
    job = client.query(query, location=BIGQUERY_LOCATION)
    job.result()
    return {
        "status": "ok",
        "prepared_table": PREPARED_ENDGAME_EVENTS_TABLE,
        "total_ms": _ms_since(started_at),
        "job_id": job.job_id,
        "job_total_bytes_processed": job.total_bytes_processed,
        "job_total_slot_ms": job.slot_millis,
    }


def _refresh_prepared_action_starting_table():
    """Flatten starting-strength and opponent comparisons during refresh."""
    query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_ACTION_STARTING_TABLE}`
    PARTITION BY game_date
    CLUSTER BY is_mw, Map, section, sort_order
    AS
    WITH scoped AS (
      SELECT
        l.*,
        f.Starting_position_in_first_round
      FROM `{PREPARED_LOGS_TABLE}` l
      JOIN `{PREPARED_FULL_STATS_TABLE}` f USING(table_id, player)
      WHERE {_completed_game_sql("f")}
    ),
    paired AS (
      SELECT
        me.*,
        opp.association_starting_strength AS opp_association,
        opp.build_starting_strength AS opp_build,
        opp.cards_starting_strength AS opp_cards,
        opp.sponsors_starting_strength AS opp_sponsors
      FROM scoped me
      JOIN scoped opp
        ON me.table_id = opp.table_id AND me.player != opp.player
    ),
    observations AS (
      SELECT p.*, 'strength' AS section, 1 AS sort_order, 'Association' AS label,
        SAFE_CAST(association_starting_strength AS INT64) AS bucket, CAST(NULL AS BOOL) AS condition_met FROM paired p
      UNION ALL SELECT p.*, 'strength', 2, 'Build', SAFE_CAST(build_starting_strength AS INT64), NULL FROM paired p
      UNION ALL SELECT p.*, 'strength', 3, 'Cards', SAFE_CAST(cards_starting_strength AS INT64), NULL FROM paired p
      UNION ALL SELECT p.*, 'strength', 4, 'Sponsors', SAFE_CAST(sponsors_starting_strength AS INT64), NULL FROM paired p
      UNION ALL SELECT p.*, 'comparison', 1, 'Higher Association strength', NULL,
        SAFE_CAST(association_starting_strength AS INT64) > SAFE_CAST(opp_association AS INT64) FROM paired p
      UNION ALL SELECT p.*, 'comparison', 2, 'Higher Build strength', NULL,
        SAFE_CAST(build_starting_strength AS INT64) > SAFE_CAST(opp_build AS INT64) FROM paired p
      UNION ALL SELECT p.*, 'comparison', 3, 'Higher Cards strength', NULL,
        SAFE_CAST(cards_starting_strength AS INT64) > SAFE_CAST(opp_cards AS INT64) FROM paired p
      UNION ALL SELECT p.*, 'comparison', 4, 'Higher Sponsors strength', NULL,
        SAFE_CAST(sponsors_starting_strength AS INT64) > SAFE_CAST(opp_sponsors AS INT64) FROM paired p
      UNION ALL SELECT p.*, 'comparison', 5, 'First player', NULL,
        LOWER(TRIM(CAST(Starting_position_in_first_round AS STRING))) = 'first player' FROM paired p
    )
    SELECT
      is_mw, Map, game_date, table_conceded, end_game_triggered,
      arena_season, is_tournament, table_id, player, starting_position,
      pre_match_elo, opponent_pre_match_elo,
      elo_delta, section, sort_order, label, bucket, condition_met
    FROM observations
    """
    started_at = time.perf_counter()
    client = bigquery.Client(project=BIGQUERY_JOB_PROJECT)
    job = client.query(query, location=BIGQUERY_LOCATION)
    job.result()
    return {
        "status": "ok",
        "prepared_table": PREPARED_ACTION_STARTING_TABLE,
        "total_ms": _ms_since(started_at),
        "job_id": job.job_id,
        "job_total_bytes_processed": job.total_bytes_processed,
        "job_total_slot_ms": job.slot_millis,
    }


def _refresh_prepared_conservation_counts_table():
    query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_CONSERVATION_COUNTS_TABLE}`
    PARTITION BY game_date
    CLUSTER BY is_mw, Map, subject, subject_count
    AS
    SELECT
      f.is_mw, f.Map, f.game_date, f.table_conceded, f.end_game_triggered,
      f.arena_season, f.is_tournament, f.table_id, f.player, f.starting_position,
      f.pre_match_elo, f.opponent_pre_match_elo, f.elo_delta,
      subject,
      CASE subject
        WHEN 'projects' THEN SAFE_CAST(f.Conservation_project_association_tasks AS INT64)
        ELSE SAFE_CAST(f.Released_animals AS INT64)
      END AS subject_count
    FROM `{PREPARED_FULL_STATS_TABLE}` f
    CROSS JOIN UNNEST(['projects', 'releases']) AS subject
    WHERE {_completed_game_sql("f")}
      AND CASE subject
        WHEN 'projects' THEN SAFE_CAST(f.Conservation_project_association_tasks AS INT64)
        ELSE SAFE_CAST(f.Released_animals AS INT64)
      END BETWEEN 0 AND 7
    """
    started_at = time.perf_counter()
    client = bigquery.Client(project=BIGQUERY_JOB_PROJECT)
    job = client.query(query, location=BIGQUERY_LOCATION)
    job.result()
    return {
        "status": "ok",
        "prepared_table": PREPARED_CONSERVATION_COUNTS_TABLE,
        "total_ms": _ms_since(started_at),
        "job_id": job.job_id,
        "job_total_bytes_processed": job.total_bytes_processed,
        "job_total_slot_ms": job.slot_millis,
    }


def _refresh_prepared_predictor_specific_table():
    observations_query = _build_predictors_specific_query(
        "TRUE", observations_only=True
    )
    query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_PREDICTOR_SPECIFIC_TABLE}`
    PARTITION BY game_date
    CLUSTER BY is_mw, Map, sort_order, condition_met
    AS
    {observations_query}
    """
    started_at = time.perf_counter()
    client = bigquery.Client(project=BIGQUERY_JOB_PROJECT)
    job = client.query(query, location=BIGQUERY_LOCATION)
    job.result()
    return {
        "status": "ok",
        "prepared_table": PREPARED_PREDICTOR_SPECIFIC_TABLE,
        "total_ms": _ms_since(started_at),
        "job_id": job.job_id,
        "job_total_bytes_processed": job.total_bytes_processed,
        "job_total_slot_ms": job.slot_millis,
    }


def _refresh_prepared_card_moments_table():
    """Flatten played/in-hand/seen card moments while retaining exact filters."""
    excluded = _sql_string_list(sorted(EXCLUDED_PROJECTS))
    query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_CARD_MOMENTS_TABLE}`
    PARTITION BY game_date
    CLUSTER BY is_mw, Map, moment, card_type
    AS
    WITH played AS (
      SELECT l.*, TRIM(p.animal) AS card_name, 'animal' AS card_type,
        SAFE_CAST(p.round AS INT64) AS played_round, 'played' AS moment
      FROM `{PREPARED_LOGS_TABLE}` l CROSS JOIN UNNEST(IFNULL(l.played_animals, [])) p
      WHERE TRIM(p.animal) != ''
      UNION ALL
      SELECT l.*, TRIM(p.sponsor), 'sponsor', SAFE_CAST(p.round AS INT64), 'played'
      FROM `{PREPARED_LOGS_TABLE}` l CROSS JOIN UNNEST(IFNULL(l.played_sponsors, [])) p
      WHERE TRIM(p.sponsor) != ''
      UNION ALL
      SELECT l.*, TRIM(p.project), 'project', SAFE_CAST(p.round AS INT64), 'played'
      FROM `{PREPARED_LOGS_TABLE}` l CROSS JOIN UNNEST(IFNULL(l.played_projects, [])) p
      WHERE TRIM(p.project) != '' AND LOWER(TRIM(p.project)) NOT IN ({excluded})
    ),
    in_hand AS (
      SELECT l.*, TRIM(card) AS card_name, CAST(NULL AS STRING) AS card_type,
        CAST(NULL AS INT64) AS played_round, 'in_hand' AS moment
      FROM `{PREPARED_LOGS_TABLE}` l CROSS JOIN UNNEST(IFNULL(l.cards_drawn, [])) card
      WHERE TRIM(card) != '' AND LOWER(TRIM(card)) NOT IN ({excluded})
      QUALIFY ROW_NUMBER() OVER (
        PARTITION BY l.table_id, l.player, TRIM(card) ORDER BY l.table_id
      ) = 1
    ),
    seen AS (
      SELECT l.*, TRIM(card) AS card_name, CAST(NULL AS STRING) AS card_type,
        CAST(NULL AS INT64) AS played_round, 'seen' AS moment
      FROM `{PREPARED_LOGS_TABLE}` l
      CROSS JOIN UNNEST(ARRAY_CONCAT(IFNULL(l.cards_drawn, []), IFNULL(l.display_cards, []))) card
      WHERE TRIM(card) != '' AND LOWER(TRIM(card)) NOT IN ({excluded})
      QUALIFY ROW_NUMBER() OVER (
        PARTITION BY l.table_id, l.player, TRIM(card) ORDER BY l.table_id
      ) = 1
    ),
    all_moments AS (
      SELECT * FROM played
      UNION ALL SELECT * FROM in_hand
      UNION ALL SELECT * FROM seen
    )
    SELECT
      is_mw, Map, game_date, table_conceded, end_game_triggered,
      arena_season, is_tournament, table_id, player, starting_position,
      pre_match_elo, opponent_pre_match_elo,
      elo_delta, card_name, card_type, played_round, moment
    FROM all_moments
    """
    started_at = time.perf_counter()
    client = bigquery.Client(project=BIGQUERY_JOB_PROJECT)
    job = client.query(query, location=BIGQUERY_LOCATION)
    job.result()
    return {
        "status": "ok",
        "prepared_table": PREPARED_CARD_MOMENTS_TABLE,
        "total_ms": _ms_since(started_at),
        "job_id": job.job_id,
        "job_total_bytes_processed": job.total_bytes_processed,
        "job_total_slot_ms": job.slot_millis,
    }


def _refresh_prepared_sponsor_endgame_table():
    sponsor_names = sorted(set(SPONSOR_CP_CARDS) | set(SPONSOR_APPEAL_CARDS))
    sponsors_sql = _sql_string_list(sponsor_names)
    query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_SPONSOR_ENDGAME_TABLE}`
    PARTITION BY game_date
    CLUSTER BY is_mw, Map, sponsor
    AS
    WITH completed AS (
      SELECT * FROM `{PREPARED_LOGS_TABLE}` WHERE {_completed_game_sql()}
    ),
    played AS (
      SELECT DISTINCT l.table_id, l.player, TRIM(p.sponsor) AS sponsor
      FROM completed l CROSS JOIN UNNEST(IFNULL(l.played_sponsors, [])) p
      WHERE TRIM(p.sponsor) IN ({sponsors_sql})
    ),
    rewards AS (
      SELECT
        l.table_id, l.player, TRIM(e.sponsor) AS sponsor,
        MAX(SAFE_CAST(e.cp AS INT64)) AS cp,
        MAX(SAFE_CAST(e.appeal AS INT64)) AS appeal
      FROM completed l CROSS JOIN UNNEST(IFNULL(l.endgame_from_sponsors, [])) e
      WHERE TRIM(e.sponsor) IN ({sponsors_sql})
      GROUP BY l.table_id, l.player, sponsor
    )
    SELECT
      l.is_mw, l.Map, l.game_date, l.table_conceded, l.end_game_triggered,
      l.arena_season, l.is_tournament, l.table_id, l.player, l.starting_position,
      l.pre_match_elo, l.opponent_pre_match_elo, l.elo_delta, p.sponsor,
      COALESCE(r.cp, 0) AS cp, COALESCE(r.appeal, 0) AS appeal
    FROM played p
    JOIN completed l USING(table_id, player)
    LEFT JOIN rewards r USING(table_id, player, sponsor)
    """
    started_at = time.perf_counter()
    client = bigquery.Client(project=BIGQUERY_JOB_PROJECT)
    job = client.query(query, location=BIGQUERY_LOCATION)
    job.result()
    return {
        "status": "ok",
        "prepared_table": PREPARED_SPONSOR_ENDGAME_TABLE,
        "total_ms": _ms_since(started_at),
        "job_id": job.job_id,
        "job_total_bytes_processed": job.total_bytes_processed,
        "job_total_slot_ms": job.slot_millis,
    }


def _refresh_prepared_project_reward_table():
    query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_PROJECT_REWARD_TABLE}`
    PARTITION BY game_date
    CLUSTER BY is_mw, Map, event_kind, raw_value
    AS
    WITH base AS (
      SELECT
        is_mw, Map, game_date, table_conceded, end_game_triggered,
        arena_season, is_tournament, table_id, player, starting_position,
        pre_match_elo, opponent_pre_match_elo,
        elo_delta, 'base' AS event_kind, CAST(NULL AS STRING) AS raw_value,
        CAST(NULL AS INT64) AS reward_order
      FROM `{PREPARED_LOGS_TABLE}`
    ),
    rewards AS (
      SELECT
        l.is_mw, l.Map, l.game_date, l.table_conceded, l.end_game_triggered,
        l.arena_season, l.is_tournament, l.table_id, l.player, l.starting_position,
        l.pre_match_elo,
        l.opponent_pre_match_elo, l.elo_delta, 'reward' AS event_kind,
        LOWER(TRIM(r.reward)) AS raw_value,
        SAFE_CAST(r.`order` AS INT64) AS reward_order
      FROM `{PREPARED_LOGS_TABLE}` l
      CROSS JOIN UNNEST(IFNULL(l.project_rewards, [])) r
      WHERE TRIM(r.reward) != ''
      GROUP BY
        l.is_mw, l.Map, l.game_date, l.table_conceded, l.end_game_triggered,
        l.arena_season, l.is_tournament, l.table_id, l.player, l.starting_position,
        l.pre_match_elo,
        l.opponent_pre_match_elo, l.elo_delta, raw_value, reward_order
    )
    SELECT * FROM base UNION ALL SELECT * FROM rewards
    """
    started_at = time.perf_counter()
    client = bigquery.Client(project=BIGQUERY_JOB_PROJECT)
    job = client.query(query, location=BIGQUERY_LOCATION)
    job.result()
    return {
        "status": "ok", "prepared_table": PREPARED_PROJECT_REWARD_TABLE,
        "total_ms": _ms_since(started_at), "job_id": job.job_id,
        "job_total_bytes_processed": job.total_bytes_processed,
        "job_total_slot_ms": job.slot_millis,
    }


def _refresh_prepared_cp_reward_table():
    query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_CP_REWARD_TABLE}`
    PARTITION BY game_date
    CLUSTER BY is_mw, Map, event_kind, scope
    AS
    WITH paired AS (
      SELECT
        me.*,
        (SELECT MIN(SAFE_CAST(h.move AS INT64)) FROM UNNEST(IFNULL(me.cp_history, [])) h WHERE SAFE_CAST(h.cp AS INT64) >= 5) AS my_5,
        (SELECT MIN(SAFE_CAST(h.move AS INT64)) FROM UNNEST(IFNULL(opp.cp_history, [])) h WHERE SAFE_CAST(h.cp AS INT64) >= 5) AS opp_5,
        (SELECT MIN(SAFE_CAST(h.move AS INT64)) FROM UNNEST(IFNULL(me.cp_history, [])) h WHERE SAFE_CAST(h.cp AS INT64) >= 8) AS my_8,
        (SELECT MIN(SAFE_CAST(h.move AS INT64)) FROM UNNEST(IFNULL(opp.cp_history, [])) h WHERE SAFE_CAST(h.cp AS INT64) >= 8) AS opp_8
      FROM `{PREPARED_LOGS_TABLE}` me
      LEFT JOIN `{PREPARED_LOGS_TABLE}` opp
        ON me.table_id = opp.table_id AND me.player != opp.player
    ),
    chosen_base AS (
      SELECT p.*, '5' AS scope, LOWER(TRIM(chosen_5cp_bonus)) AS raw_value
      FROM paired p WHERE chosen_5cp_bonus IS NOT NULL
      UNION ALL
      SELECT p.*, '8', LOWER(TRIM(chosen_8cp_bonus))
      FROM paired p WHERE chosen_8cp_bonus IS NOT NULL
    ),
    chosen AS (
      SELECT * FROM chosen_base
      UNION ALL
      SELECT * REPLACE('combined' AS scope)
      FROM chosen_base
      QUALIFY ROW_NUMBER() OVER (
        PARTITION BY table_id, player, raw_value ORDER BY scope
      ) = 1
    ),
    opportunity_base AS (
      SELECT p.*, '5' AS scope, LOWER(TRIM(reward)) AS raw_value,
        LOWER(TRIM(chosen_5cp_bonus)) = LOWER(TRIM(reward)) AS chosen
      FROM paired p CROSS JOIN UNNEST(ARRAY_CONCAT(IFNULL(five_cp_bonus, []), ['5 money'])) reward
      WHERE my_5 IS NOT NULL AND (opp_5 IS NULL OR my_5 < opp_5)
      UNION ALL
      SELECT p.*, '8', LOWER(TRIM(reward)),
        LOWER(TRIM(chosen_8cp_bonus)) = LOWER(TRIM(reward))
      FROM paired p CROSS JOIN UNNEST(ARRAY_CONCAT(IFNULL(eight_cp_bonus, []), ['5 money'])) reward
      WHERE my_8 IS NOT NULL AND (opp_8 IS NULL OR my_8 < opp_8)
    ),
    opportunities AS (
      SELECT * FROM opportunity_base
      UNION ALL SELECT * REPLACE('combined' AS scope) FROM opportunity_base
    ),
    chosen_rows AS (
      SELECT
        is_mw, Map, game_date, table_conceded, end_game_triggered,
        arena_season, is_tournament, table_id, player, starting_position,
        pre_match_elo, opponent_pre_match_elo,
        elo_delta, 'chosen' AS event_kind, scope, raw_value,
        CAST(NULL AS BOOL) AS chosen
      FROM chosen
    ),
    opportunity_rows AS (
      SELECT
        is_mw, Map, game_date, table_conceded, end_game_triggered,
        arena_season, is_tournament, table_id, player, starting_position,
        pre_match_elo, opponent_pre_match_elo,
        elo_delta, 'opportunity' AS event_kind, scope, raw_value, chosen
      FROM opportunities
    )
    SELECT * FROM chosen_rows UNION ALL SELECT * FROM opportunity_rows
    """
    started_at = time.perf_counter()
    client = bigquery.Client(project=BIGQUERY_JOB_PROJECT)
    job = client.query(query, location=BIGQUERY_LOCATION)
    job.result()
    return {
        "status": "ok", "prepared_table": PREPARED_CP_REWARD_TABLE,
        "total_ms": _ms_since(started_at), "job_id": job.job_id,
        "job_total_bytes_processed": job.total_bytes_processed,
        "job_total_slot_ms": job.slot_millis,
    }


def _refresh_prepared_card_endgame_table():
    query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_CARD_ENDGAME_TABLE}`
    PARTITION BY game_date
    CLUSTER BY is_mw, Map, card_type, card_name
    AS
    SELECT DISTINCT
      p.is_mw, p.Map, p.game_date, p.table_conceded, p.end_game_triggered,
       p.arena_season, p.is_tournament, p.table_id, p.player, p.starting_position,
      p.pre_match_elo, p.opponent_pre_match_elo, p.elo_delta, p.card_name, p.card_type,
      p.played_round, e.card_name AS endgame_name
    FROM `{PREPARED_CARD_PLAYS_TABLE}` p
    JOIN `{PREPARED_ENDGAME_EVENTS_TABLE}` e USING(table_id, player)
    WHERE e.event_role = 'scored'
      AND {_completed_game_sql("p")}
    """
    started_at = time.perf_counter()
    client = bigquery.Client(project=BIGQUERY_JOB_PROJECT)
    job = client.query(query, location=BIGQUERY_LOCATION)
    job.result()
    return {
        "status": "ok", "prepared_table": PREPARED_CARD_ENDGAME_TABLE,
        "total_ms": _ms_since(started_at), "job_id": job.job_id,
        "job_total_bytes_processed": job.total_bytes_processed,
        "job_total_slot_ms": job.slot_millis,
    }


def _refresh_prepared_card_endgame_aggregates_table():
    """Collapse Card + Endgame events to filterable daily moments."""
    query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_CARD_ENDGAME_AGGREGATES_TABLE}`
    PARTITION BY game_date
    CLUSTER BY is_mw, card_name, endgame_name, Map
    AS
    SELECT
      is_mw, Map, game_date, table_conceded, end_game_triggered,
      arena_season, is_tournament, starting_position,
      SAFE_CAST(pre_match_elo AS FLOAT64) AS pre_match_elo,
      SAFE_CAST(opponent_pre_match_elo AS FLOAT64) AS opponent_pre_match_elo,
      card_name, ANY_VALUE(card_type) AS card_type, played_round, endgame_name,
      COUNT(*) AS observation_count,
      COUNT(elo_delta) AS delta_count,
      SUM(SAFE_CAST(elo_delta AS FLOAT64)) AS delta_sum,
      SUM(POW(SAFE_CAST(elo_delta AS FLOAT64), 2)) AS delta_sum_squares,
      COUNT(pre_match_elo) AS elo_count,
      SUM(SAFE_CAST(pre_match_elo AS FLOAT64)) AS elo_sum
    FROM `{PREPARED_CARD_ENDGAME_TABLE}`
    GROUP BY
      is_mw, Map, game_date, table_conceded, end_game_triggered,
      arena_season, is_tournament, starting_position,
      pre_match_elo, opponent_pre_match_elo,
      card_name, played_round, endgame_name
    """
    started_at = time.perf_counter()
    client = bigquery.Client(project=BIGQUERY_JOB_PROJECT)
    job = client.query(query, location=BIGQUERY_LOCATION)
    job.result()
    return {
        "status": "ok",
        "prepared_table": PREPARED_CARD_ENDGAME_AGGREGATES_TABLE,
        "total_ms": _ms_since(started_at),
        "job_id": job.job_id,
        "job_total_bytes_processed": job.total_bytes_processed,
        "job_total_slot_ms": job.slot_millis,
    }


def _mw_action_card_catalog_sql():
    rows = ",\n      ".join(
        "STRUCT({order} AS card_order, '{card_type}' AS card_type, "
        "{number} AS card_number, '{name}' AS card_name, "
        "'{card_type} {number}' AS card_key)".format(
            order=order,
            card_type=card_type.replace("'", "''"),
            number=number,
            name=name.replace("'", "''"),
        )
        for order, card_type, number, name in MW_ACTION_CARD_CATALOG
    )
    return f"SELECT * FROM UNNEST([\n      {rows}\n    ])"


def _mw_action_card_telemetry_condition(alias="f"):
    number_fields = (
        "Animals_Action_Card_Number",
        "Association_Action_Card_Number",
        "Build_Action_Card_Number",
        "Cards_Action_Card_Number",
        "Sponsors_Action_Card_Number",
    )
    draft_fields = (
        "First_drafted_action_card",
        "Second_drafted_action_card",
        "Third_drafted_action_card",
    )
    number_checks = [
        f"IFNULL(SAFE_CAST({alias}.{field} AS INT64) BETWEEN 0 AND 4, FALSE)"
        for field in number_fields
    ]
    draft_checks = [
        "IFNULL(REGEXP_CONTAINS(TRIM(CAST({alias}.{field} AS STRING)), "
        "r'^(Animals|Association|Build|Cards|Sponsors) [1-4]$'), FALSE)".format(
            alias=alias, field=field
        )
        for field in draft_fields
    ]
    return " AND ".join(number_checks + draft_checks)


def _refresh_prepared_mw_action_card_tables():
    """Materialize only complete two-player MW action-card telemetry.

    Marine Worlds deals each player three special action cards through a
    choose/pass, choose/pass, receive-returned-card draft.  Players then keep
    two different action types.  Draft strings use canonical backend keys such
    as ``Sponsors 1``; selected cards use the five numeric action-card fields.
    ``MW_ACTION_CARD_CATALOG`` is the single mapping from those representations
    to frontend colloquial names such as ``Trade``.
    """
    telemetry_ok = _mw_action_card_telemetry_condition("f")
    catalog_sql = _mw_action_card_catalog_sql()
    eligible_cte = f"""
    eligible_tables AS (
      SELECT table_id
      FROM `{PREPARED_FULL_STATS_TABLE}` f
      WHERE CAST(f.is_mw AS INT64) = 1
      GROUP BY table_id
      HAVING COUNT(*) = 2
        AND COUNT(DISTINCT player) = 2
        AND COUNTIF(NOT ({telemetry_ok})) = 0
    )
    """
    player_query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_MW_ACTION_CARD_PLAYERS_TABLE}`
    PARTITION BY game_date
    CLUSTER BY card_key, Map, arena_season, is_tournament
    AS
    WITH
    {eligible_cte},
    catalog AS ({catalog_sql}),
    selected AS (
      SELECT
        f.table_id, f.player, f.Map, opponent.Map AS opponent_map, f.game_date,
        f.table_conceded, f.end_game_triggered, f.arena_season,
        f.is_tournament, f.starting_position,
        f.pre_match_elo, f.opponent_pre_match_elo, f.elo_delta,
        picked.card_type, picked.card_number,
        COALESCE(
          CASE picked.card_type
            WHEN 'Animals' THEN f.Upgraded_Animals_action_card
            WHEN 'Association' THEN f.Upgraded_Association_action_card
            WHEN 'Build' THEN f.Upgraded_Build_action_card
            WHEN 'Cards' THEN f.Upgraded_Cards_action_card
            WHEN 'Sponsors' THEN f.Upgraded_Sponsors_action_card
          END,
          FALSE
        ) AS upgraded
      FROM `{PREPARED_FULL_STATS_TABLE}` f
      JOIN eligible_tables e USING(table_id)
      JOIN `{PREPARED_FULL_STATS_TABLE}` opponent
        ON opponent.table_id = f.table_id AND opponent.player != f.player
      CROSS JOIN UNNEST([
        STRUCT('Animals' AS card_type, SAFE_CAST(f.Animals_Action_Card_Number AS INT64) AS card_number),
        STRUCT('Association', SAFE_CAST(f.Association_Action_Card_Number AS INT64)),
        STRUCT('Build', SAFE_CAST(f.Build_Action_Card_Number AS INT64)),
        STRUCT('Cards', SAFE_CAST(f.Cards_Action_Card_Number AS INT64)),
        STRUCT('Sponsors', SAFE_CAST(f.Sponsors_Action_Card_Number AS INT64))
      ]) picked
      WHERE picked.card_number BETWEEN 1 AND 4
    )
    SELECT
      1 AS is_mw,
      c.card_order, c.card_type, c.card_number, c.card_name, c.card_key,
      s.table_id, s.player, s.Map, s.opponent_map, s.game_date,
      s.table_conceded, s.end_game_triggered, s.arena_season,
      s.is_tournament, s.starting_position,
      s.pre_match_elo, s.opponent_pre_match_elo, s.elo_delta,
      s.upgraded
    FROM selected s
    JOIN catalog c USING(card_type, card_number)
    """
    draft_query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_MW_ACTION_CARD_DRAFTS_TABLE}`
    PARTITION BY game_date
    CLUSTER BY card_key, p1_map, p2_map, arena_season
    AS
    WITH
    {eligible_cte},
    catalog AS ({catalog_sql}),
    ranked AS (
      SELECT
        f.*,
        ROW_NUMBER() OVER (
          PARTITION BY table_id
          ORDER BY IF(starting_position = 'First player', 1, 2), player
        ) AS player_order
      FROM `{PREPARED_FULL_STATS_TABLE}` f
      JOIN eligible_tables e USING(table_id)
    ),
    paired AS (
      SELECT
        table_id,
        MAX(IF(player_order = 1, Map, NULL)) AS p1_map,
        MAX(IF(player_order = 2, Map, NULL)) AS p2_map,
        MAX(IF(player_order = 1, pre_match_elo, NULL)) AS p1_pre_match_elo,
        MAX(IF(player_order = 2, pre_match_elo, NULL)) AS p2_pre_match_elo,
        MAX(IF(player_order = 1, opponent_pre_match_elo, NULL)) AS p1_opponent_pre_match_elo,
        MAX(IF(player_order = 2, opponent_pre_match_elo, NULL)) AS p2_opponent_pre_match_elo,
        MAX(game_date) AS game_date,
        MAX(table_conceded) AS table_conceded,
        LOGICAL_AND(end_game_triggered) AS end_game_triggered,
        MAX(arena_season) AS arena_season,
        LOGICAL_OR(is_tournament) AS is_tournament,
        MAX(IF(player_order = 1, First_drafted_action_card, NULL)) AS p1_first,
        MAX(IF(player_order = 2, First_drafted_action_card, NULL)) AS p2_first,
        MAX(IF(player_order = 1, Second_drafted_action_card, NULL)) AS p1_second,
        MAX(IF(player_order = 2, Second_drafted_action_card, NULL)) AS p2_second,
        MAX(IF(player_order = 1, Third_drafted_action_card, NULL)) AS p1_third,
        MAX(IF(player_order = 2, Third_drafted_action_card, NULL)) AS p2_third,
        ARRAY_CONCAT_AGG([
          CONCAT('Animals ', CAST(Animals_Action_Card_Number AS STRING)),
          CONCAT('Association ', CAST(Association_Action_Card_Number AS STRING)),
          CONCAT('Build ', CAST(Build_Action_Card_Number AS STRING)),
          CONCAT('Cards ', CAST(Cards_Action_Card_Number AS STRING)),
          CONCAT('Sponsors ', CAST(Sponsors_Action_Card_Number AS STRING))
        ]) AS selected_cards
      FROM ranked
      GROUP BY table_id
    )
    SELECT
      1 AS is_mw,
      c.card_order, c.card_type, c.card_number, c.card_name, c.card_key,
      p.table_id, p.game_date, p.p1_map, p.p2_map,
      p.p1_pre_match_elo, p.p2_pre_match_elo,
      p.p1_opponent_pre_match_elo, p.p2_opponent_pre_match_elo,
      p.table_conceded, p.end_game_triggered, p.arena_season, p.is_tournament,
      c.card_key IN UNNEST(p.selected_cards) AS picked,
      c.card_key IN (p.p1_first, p.p2_first) AS drafted_first,
      c.card_key IN (p.p1_second, p.p2_second) AS drafted_second,
      c.card_key IN (p.p1_third, p.p2_third) AS undrafted
    FROM paired p
    CROSS JOIN catalog c
    WHERE c.card_key IN (
      p.p1_first, p.p2_first, p.p1_second, p.p2_second, p.p1_third, p.p2_third
    )
    """
    map_aggregate_query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_MW_ACTION_CARD_MAP_AGGREGATES_TABLE}`
    PARTITION BY game_date
    CLUSTER BY card_key, Map, arena_season, is_tournament
    AS
    SELECT
      game_date, Map, starting_position, pre_match_elo, opponent_pre_match_elo,
      table_conceded, end_game_triggered, arena_season, is_tournament,
      card_order, card_key, card_type, card_number, card_name,
      COUNT(*) AS observation_count,
      COUNT(elo_delta) AS delta_count,
      SUM(elo_delta) AS delta_sum,
      SUM(POW(elo_delta, 2)) AS delta_sum_squares
    FROM `{PREPARED_MW_ACTION_CARD_PLAYERS_TABLE}`
    WHERE Map = opponent_map AND Map IN UNNEST({json.dumps(VALID_MAPS)})
    GROUP BY
      game_date, Map, starting_position, pre_match_elo, opponent_pre_match_elo,
      table_conceded, end_game_triggered, arena_season, is_tournament,
      card_order, card_key, card_type, card_number, card_name
    """
    synergy_aggregate_query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_MW_ACTION_CARD_SYNERGY_AGGREGATES_TABLE}`
    PARTITION BY game_date
    CLUSTER BY card_1_key, card_2_key, Map, arena_season
    AS
    WITH player_pairs AS (
      SELECT
        table_id, player, game_date, Map, opponent_map,
        starting_position, pre_match_elo, opponent_pre_match_elo, elo_delta,
        table_conceded, end_game_triggered, arena_season, is_tournament,
        ARRAY_AGG(STRUCT(
          card_order, card_key, card_type, card_number, card_name
        ) ORDER BY card_order) AS cards
      FROM `{PREPARED_MW_ACTION_CARD_PLAYERS_TABLE}`
      GROUP BY
        table_id, player, game_date, Map, opponent_map,
        starting_position, pre_match_elo, opponent_pre_match_elo, elo_delta,
        table_conceded, end_game_triggered, arena_season, is_tournament
      HAVING COUNT(*) = 2 AND COUNT(DISTINCT card_type) = 2
    ), observations AS (
      SELECT
        game_date, Map, opponent_map, starting_position,
        pre_match_elo, opponent_pre_match_elo,
        table_conceded, end_game_triggered, arena_season, is_tournament,
        cards[OFFSET(0)].card_order AS card_1_order,
        cards[OFFSET(0)].card_key AS card_1_key,
        cards[OFFSET(0)].card_type AS card_1_type,
        cards[OFFSET(0)].card_number AS card_1_number,
        cards[OFFSET(0)].card_name AS card_1_name,
        cards[OFFSET(1)].card_order AS card_2_order,
        cards[OFFSET(1)].card_key AS card_2_key,
        cards[OFFSET(1)].card_type AS card_2_type,
        cards[OFFSET(1)].card_number AS card_2_number,
        cards[OFFSET(1)].card_name AS card_2_name,
        elo_delta
      FROM player_pairs
    )
    SELECT
      game_date, Map, opponent_map, starting_position,
      pre_match_elo, opponent_pre_match_elo,
      table_conceded, end_game_triggered, arena_season, is_tournament,
      card_1_order, card_1_key, card_1_type, card_1_number, card_1_name,
      card_2_order, card_2_key, card_2_type, card_2_number, card_2_name,
      COUNT(*) AS observation_count,
      COUNT(elo_delta) AS delta_count,
      SUM(elo_delta) AS delta_sum,
      SUM(POW(elo_delta, 2)) AS delta_sum_squares,
      COUNT(pre_match_elo) AS elo_count,
      SUM(pre_match_elo) AS elo_sum
    FROM observations
    GROUP BY
      game_date, Map, opponent_map, starting_position,
      pre_match_elo, opponent_pre_match_elo,
      table_conceded, end_game_triggered, arena_season, is_tournament,
      card_1_order, card_1_key, card_1_type, card_1_number, card_1_name,
      card_2_order, card_2_key, card_2_type, card_2_number, card_2_name
    """
    card_action_query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_CARD_ACTION_CARD_TABLE}`
    PARTITION BY game_date
    CLUSTER BY card_name, action_card_key, Map, arena_season
    AS
    WITH normal_cards AS (
      SELECT
        table_id, player, ANY_VALUE(is_mw) AS is_mw, ANY_VALUE(Map) AS Map,
        ANY_VALUE(game_date) AS game_date,
        ANY_VALUE(table_conceded) AS table_conceded,
        LOGICAL_AND(end_game_triggered) AS end_game_triggered,
        ANY_VALUE(arena_season) AS arena_season,
        LOGICAL_OR(is_tournament) AS is_tournament,
        ANY_VALUE(starting_position) AS starting_position,
        ANY_VALUE(pre_match_elo) AS pre_match_elo,
        ANY_VALUE(opponent_pre_match_elo) AS opponent_pre_match_elo,
        ANY_VALUE(elo_delta) AS elo_delta,
        card_name, ANY_VALUE(card_type) AS card_type,
        TO_JSON_STRING(ARRAY_AGG(DISTINCT played_round ORDER BY played_round)) AS played_rounds_json
      FROM `{PREPARED_CARD_PLAYS_TABLE}`
      WHERE CAST(is_mw AS INT64) = 1
      GROUP BY table_id, player, card_name
    )
    SELECT
      n.table_id, n.player, n.is_mw, n.Map, a.opponent_map, n.game_date,
      n.table_conceded, n.end_game_triggered, n.arena_season, n.is_tournament,
      n.starting_position,
      n.pre_match_elo, n.opponent_pre_match_elo, n.elo_delta,
      n.card_name, n.card_type, n.played_rounds_json,
      a.card_order AS action_card_order, a.card_key AS action_card_key,
      a.card_type AS action_card_type, a.card_number AS action_card_number,
      a.card_name AS action_card_name
    FROM normal_cards n
    JOIN `{PREPARED_MW_ACTION_CARD_PLAYERS_TABLE}` a
      ON a.table_id = n.table_id AND a.player = n.player
    """
    card_action_aggregate_query = f"""
    CREATE OR REPLACE TABLE `{PREPARED_CARD_ACTION_CARD_AGGREGATES_TABLE}`
    PARTITION BY game_date
    CLUSTER BY card_name, action_card_key, Map, arena_season
    AS
    SELECT
      is_mw, game_date, Map, opponent_map, starting_position,
      pre_match_elo, opponent_pre_match_elo,
      table_conceded, end_game_triggered, arena_season, is_tournament,
      card_name, card_type, played_rounds_json,
      action_card_order, action_card_key, action_card_type,
      action_card_number, action_card_name,
      COUNT(*) AS observation_count,
      COUNT(elo_delta) AS delta_count,
      SUM(elo_delta) AS delta_sum,
      SUM(POW(elo_delta, 2)) AS delta_sum_squares,
      COUNT(pre_match_elo) AS elo_count,
      SUM(pre_match_elo) AS elo_sum
    FROM `{PREPARED_CARD_ACTION_CARD_TABLE}`
    GROUP BY
      is_mw, game_date, Map, opponent_map, starting_position,
      pre_match_elo, opponent_pre_match_elo,
      table_conceded, end_game_triggered, arena_season, is_tournament,
      card_name, card_type, played_rounds_json,
      action_card_order, action_card_key, action_card_type,
      action_card_number, action_card_name
    """
    client = bigquery.Client(project=BIGQUERY_JOB_PROJECT)
    started_at = time.perf_counter()
    player_job = client.query(player_query, location=BIGQUERY_LOCATION)
    draft_job = client.query(draft_query, location=BIGQUERY_LOCATION)
    player_job.result()
    card_action_job = client.query(card_action_query, location=BIGQUERY_LOCATION)
    card_action_job.result()
    aggregate_jobs = {
        "map": client.query(map_aggregate_query, location=BIGQUERY_LOCATION),
        "synergy": client.query(synergy_aggregate_query, location=BIGQUERY_LOCATION),
        "card_action": client.query(card_action_aggregate_query, location=BIGQUERY_LOCATION),
    }
    draft_job.result()
    for job in aggregate_jobs.values():
        job.result()
    all_jobs = [player_job, draft_job, card_action_job, *aggregate_jobs.values()]
    return {
        "status": "ok",
        "player_table": PREPARED_MW_ACTION_CARD_PLAYERS_TABLE,
        "draft_table": PREPARED_MW_ACTION_CARD_DRAFTS_TABLE,
        "map_table": PREPARED_MW_ACTION_CARD_MAP_AGGREGATES_TABLE,
        "synergy_table": PREPARED_MW_ACTION_CARD_SYNERGY_AGGREGATES_TABLE,
        "card_action_table": PREPARED_CARD_ACTION_CARD_TABLE,
        "card_action_aggregate_table": PREPARED_CARD_ACTION_CARD_AGGREGATES_TABLE,
        "total_ms": _ms_since(started_at),
        "player_job_id": player_job.job_id,
        "draft_job_id": draft_job.job_id,
        "job_total_bytes_processed": sum(
            int(job.total_bytes_processed or 0) for job in all_jobs
        ),
        "job_total_slot_ms": sum(int(job.slot_millis or 0) for job in all_jobs),
    }


def _refresh_prepared_tables(arena_metadata=None, merge_metadata=None, progress_callback=None):
    arena_metadata = arena_metadata or _load_arena_metadata()
    steps = [
        ("full_stats", "Full Sample", lambda: _refresh_prepared_full_stats_table(arena_metadata)),
        ("logs", "Logs", lambda: _refresh_prepared_logs_table(arena_metadata)),
        ("records_manual", "Records sheets", _refresh_prepared_records_manual_table),
        ("players", "Players", lambda: _refresh_prepared_players_table(arena_metadata, merge_metadata)),
        ("card_plays", "Card plays", _refresh_prepared_card_plays_table),
        ("card_pairs", "Card pairs", _refresh_prepared_card_pairs_table),
        ("card_play_aggregates", "Card aggregates", _refresh_prepared_card_play_aggregates_table),
        ("card_pair_aggregates", "Card-pair aggregates", _refresh_prepared_card_pair_aggregates_table),
        ("card_pair_scope_aggregates", "Card-pair scopes", _refresh_prepared_card_pair_scope_aggregates_table),
        ("home_observations", "Home observations", _refresh_prepared_home_observations_table),
        ("endgame_events", "Endgame events", _refresh_prepared_endgame_events_table),
        ("action_starting", "Starting positions", _refresh_prepared_action_starting_table),
        ("conservation_counts", "Conservation", _refresh_prepared_conservation_counts_table),
        ("predictor_specific", "Predictors", _refresh_prepared_predictor_specific_table),
        ("card_moments", "Card moments", _refresh_prepared_card_moments_table),
        ("sponsor_endgames", "Sponsor endgames", _refresh_prepared_sponsor_endgame_table),
        ("project_rewards", "Project rewards", _refresh_prepared_project_reward_table),
        ("cp_rewards", "CP rewards", _refresh_prepared_cp_reward_table),
        ("card_endgames", "Card/endgame pairs", _refresh_prepared_card_endgame_table),
        ("card_endgame_aggregates", "Card/endgame aggregates", _refresh_prepared_card_endgame_aggregates_table),
        ("mw_action_cards", "MW Action Cards", _refresh_prepared_mw_action_card_tables),
    ]
    results = {}
    for index, (key, label, operation) in enumerate(steps, start=1):
        results[key] = operation()
        if progress_callback:
            progress_callback(index, len(steps), label)
    full_stats = results["full_stats"]
    return {
        "status": "ok",
        "prepared_table": PREPARED_LOGS_TABLE,
        "job_id": full_stats["job_id"],
        **results,
    }


def _refresh_player_index_snapshot(is_mw, merge_metadata=None):
    """Publish autocomplete names without exposing merged-identity groups."""
    dataset = "mw" if int(is_mw) == 1 else "base"
    blob_name = f"{CACHE_PREFIX}/players/index/default-{dataset}.json"
    query = f"""
      SELECT DISTINCT TRIM(CAST(player AS STRING)) AS player
      FROM `{PREPARED_PLAYERS_TABLE}`
      WHERE CAST(is_mw AS INT64) = @is_mw
        AND Map IN UNNEST(@selected_maps)
        AND {_completed_game_sql()}
        AND player IS NOT NULL
        AND TRIM(CAST(player AS STRING)) != ''
      ORDER BY player
    """
    started_at = time.perf_counter()
    client = bigquery.Client(project=BIGQUERY_JOB_PROJECT)
    job = client.query(
        query,
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("is_mw", "INT64", int(is_mw)),
            bigquery.ArrayQueryParameter("selected_maps", "STRING", ALL_KNOWN_MAPS),
        ]),
        location=BIGQUERY_LOCATION,
    )
    players = [str(row.player) for row in job.result() if row.player]
    player_set = set(players)
    merge_metadata = merge_metadata or _load_merge_players_metadata()
    for group in merge_metadata.get("groups", []):
        members = [str(value) for value in group.get("members", []) if str(value)]
        if any(member in player_set for member in members):
            player_set.update(members)
    players = sorted(player_set, key=lambda value: (value.casefold(), value))
    cache_ok = _write_cache_blob(
        blob_name,
        {
            "status": "ok",
            "players": players,
            "dataset": dataset,
        },
        "refreshed",
    )
    return {
        "status": "ok" if cache_ok else "error",
        "dataset": dataset,
        "players": len(players),
        "cache_status": "refreshed" if cache_ok else "cache_write_failed",
        "total_ms": _ms_since(started_at),
        "job_id": job.job_id,
        "job_total_bytes_processed": job.total_bytes_processed,
        "job_total_slot_ms": job.slot_millis,
    }


def _comparison_player_search(index_payload, term, selected_players, metadata=None):
    """Return eligible Comparison aliases without publishing identity mappings."""
    metadata = metadata or _load_merge_players_metadata()
    normalized_term = str(term or "").strip().casefold()
    if len(normalized_term) < 3:
        return []
    excluded_identities = {
        _player_identity(player, metadata) for player in selected_players or []
    }
    matches = []
    for player in index_payload.get("players", []):
        name = str(player or "").strip()
        if not name or normalized_term not in name.casefold():
            continue
        if _player_identity(name, metadata) in excluded_identities:
            continue
        matches.append(name)
        if len(matches) >= 50:
            break
    return matches


def _fide_performance_rating(score_rate, average_opponent_elo):
    """Return FIDE table 8.1.1 tournament performance for a score rate.

    Arena uses the official integer score-percentage lookup rather than the
    continuous logistic approximation. Draws count as half a point; malformed
    results never enter either the score rate or this opponent-Elo average.
    """
    if score_rate is None or average_opponent_elo is None:
        return None
    score_rate = max(0.0, min(1.0, float(score_rate)))
    percentage = max(0, min(100, int(math.floor(score_rate * 100.0 + 0.5))))
    return int(round(float(average_opponent_elo) + FIDE_PERFORMANCE_DP[percentage]))


def _arena_top100_season_payload(season):
    """Rebuild one closed Arena ranking table and its compact rating history."""
    ranking = season.get("ranking") or []
    players = [item["player"] for item in ranking]
    query = f"""
      SELECT
        player,
        COUNT(*) AS games,
        MAX(post_match_arena_rating) AS peak,
        AVG(arena_game_score) AS score_rate,
        AVG(opponent_pre_match_elo) AS opponent_pre_match_elo,
        AVG(IF(arena_game_score IS NOT NULL, opponent_pre_match_elo, NULL)) AS pr_opponent_elo,
        AVG(IF({_completed_game_sql()}, turns, NULL)) AS turns,
        AVG(IF({_completed_game_sql()}, points_per_turn, NULL)) AS ppt,
        ARRAY_AGG(
          IF(
            post_match_arena_rating IS NULL,
            NULL,
            STRUCT(
              FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', game_ended_at) AS ended_at,
              CAST(table_id AS STRING) AS table_id,
              post_match_arena_rating AS rating
            )
          ) IGNORE NULLS
          ORDER BY game_ended_at, CAST(table_id AS STRING)
        ) AS history
      FROM `{PREPARED_PLAYERS_TABLE}`
      WHERE arena_season = @arena_season
        AND is_mw = @is_mw
        AND game_date BETWEEN @start_date AND @end_date
        AND game_ended_at >= @start_utc
        AND game_ended_at < @end_utc
        AND player IN UNNEST(@players)
      GROUP BY player
    """
    started_at = time.perf_counter()
    client = bigquery.Client(project=BIGQUERY_JOB_PROJECT)
    start = datetime.fromisoformat(season["start_utc"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(
        season["effective_end_utc"].replace("Z", "+00:00")
    )
    job = client.query(
        query,
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("arena_season", "STRING", season["season"]),
            bigquery.ScalarQueryParameter("is_mw", "INT64", int(season["is_mw"])),
            bigquery.ScalarQueryParameter("start_date", "DATE", start.date()),
            bigquery.ScalarQueryParameter("end_date", "DATE", end.date()),
            bigquery.ScalarQueryParameter("start_utc", "TIMESTAMP", start),
            bigquery.ScalarQueryParameter("end_utc", "TIMESTAMP", end),
            bigquery.ArrayQueryParameter("players", "STRING", players),
        ]),
        location=BIGQUERY_LOCATION,
    )
    by_player = {str(row.player): row for row in job.result()}
    rows = []
    series = []
    for ranked in ranking:
        player = ranked["player"]
        aggregate = by_player.get(player)
        games = int(getattr(aggregate, "games", 0) or 0) if aggregate else 0
        score_rate = getattr(aggregate, "score_rate", None) if aggregate else None
        average_opponent = getattr(aggregate, "opponent_pre_match_elo", None) if aggregate else None
        pr_opponent = getattr(aggregate, "pr_opponent_elo", None) if aggregate else None
        rows.append({
            "rank": int(ranked["rank"]),
            "player": player,
            "end": int(round(float(ranked["end"]))),
            "peak": getattr(aggregate, "peak", None) if aggregate else None,
            "games": games,
            "winrate": float(score_rate) * 100.0 if score_rate is not None else None,
            # Public payload compatibility: this key means the opponent's
            # canonical pre-match Elo.
            "opponent_elo": average_opponent,
            "pr": _fide_performance_rating(score_rate, pr_opponent),
            "turns": getattr(aggregate, "turns", None) if aggregate else None,
            "ppt": getattr(aggregate, "ppt", None) if aggregate else None,
        })
        history = list(getattr(aggregate, "history", None) or []) if aggregate else []
        def history_value(item, key):
            return item.get(key) if isinstance(item, dict) else getattr(item, key)
        series.append({
            "rank": int(ranked["rank"]),
            "player": player,
            # Parallel arrays avoid repeating player names and object keys for
            # every graph point in the static all-season bundle.
            "timestamps": [str(history_value(item, "ended_at")) for item in history],
            "ratings": [float(history_value(item, "rating")) for item in history],
        })
    return {
        "season": season["season"],
        "mode": season["mode"],
        "start_utc": season["start_utc"],
        "end_utc": season["end_utc"],
        "effective_end_utc": season["effective_end_utc"],
        "rows": rows,
        "series": series,
        "total_ms": _ms_since(started_at),
        "job_id": job.job_id,
        "job_total_bytes_processed": job.total_bytes_processed,
        "job_total_slot_ms": job.slot_millis,
    }


def _refresh_arena_top100_bundle(arena_metadata, data_version):
    """Publish all completed ranking-file seasons as one atomic static bundle."""
    rankings = arena_metadata.get("rankings") or {}
    available = []
    for season in arena_metadata.get("seasons", []):
        ranking = rankings.get(season.get("season"))
        if season.get("top_100_available") and ranking:
            available.append({**season, "ranking": ranking})
    available.sort(key=lambda item: item["number"], reverse=True)
    started_at = time.perf_counter()
    results = {}
    with ThreadPoolExecutor(max_workers=min(4, max(1, len(available)))) as executor:
        futures = {
            executor.submit(_arena_top100_season_payload, season): season["season"]
            for season in available
        }
        for future, season_name in [(future, futures[future]) for future in futures]:
            results[season_name] = future.result()

    public_seasons = [{
        "season": item["season"],
        "number": int(item["number"]),
        "mode": item["mode"],
        "is_mw": int(item["is_mw"]),
        "start_utc": item["start_utc"],
        "end_utc": item["end_utc"],
        "effective_end_utc": item["effective_end_utc"],
    } for item in available]
    payload = {
        "status": "ok",
        "data_version": data_version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "latest_season": public_seasons[0]["season"] if public_seasons else None,
        "seasons": public_seasons,
        "data": {item["season"]: results[item["season"]] for item in available},
    }
    cache_ok = _write_cache_blob(ARENA_TOP100_BUNDLE_BLOB, payload, "refreshed")
    manifest_ok = cache_ok and _write_cache_blob(
        ARENA_MANIFEST_BLOB,
        _arena_manifest(arena_metadata, data_version),
        "refreshed",
    )
    return {
        "status": "ok" if cache_ok and manifest_ok else "error",
        "cache_status": "refreshed" if cache_ok and manifest_ok else "cache_write_failed",
        "seasons": len(available),
        "rows": sum(len(item.get("rows") or []) for item in results.values()),
        "total_ms": _ms_since(started_at),
        "season_jobs": {
            name: {
                "total_ms": item.get("total_ms"),
                "job_id": item.get("job_id"),
                "job_total_bytes_processed": item.get("job_total_bytes_processed"),
                "job_total_slot_ms": item.get("job_total_slot_ms"),
            }
            for name, item in results.items()
        },
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
    completed_only,
    arena_only=False,
    tournament_only=False,
    starting_positions=None,
):
    """Build the shared focal-player filter.

    Starting position is intentionally a player-observation dimension. Omitting
    it means both positions (and preserves malformed legacy rows); a restrictive
    request is applied before any downstream Last-X or rolling-window logic.
    """
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
        where_clauses.append("COALESCE(pre_match_elo, 0) >= @player_elo_min")
        query_parameters.append(bigquery.ScalarQueryParameter("player_elo_min", "INT64", player_elo_min))
    if player_elo_max is not None:
        where_clauses.append("COALESCE(pre_match_elo, 0) <= @player_elo_max")
        query_parameters.append(bigquery.ScalarQueryParameter("player_elo_max", "INT64", player_elo_max))
    if opponent_elo_min is not None:
        where_clauses.append("COALESCE(opponent_pre_match_elo, 0) >= @opponent_elo_min")
        query_parameters.append(bigquery.ScalarQueryParameter("opponent_elo_min", "INT64", opponent_elo_min))
    if opponent_elo_max is not None:
        where_clauses.append("COALESCE(opponent_pre_match_elo, 0) <= @opponent_elo_max")
        query_parameters.append(bigquery.ScalarQueryParameter("opponent_elo_max", "INT64", opponent_elo_max))
    if date_from:
        where_clauses.append("game_date >= @date_from")
        query_parameters.append(bigquery.ScalarQueryParameter("date_from", "DATE", date_from))
    if date_to:
        where_clauses.append("game_date <= @date_to")
        query_parameters.append(bigquery.ScalarQueryParameter("date_to", "DATE", date_to))
    if completed_only:
        where_clauses.append(_completed_game_sql())
    if arena_only:
        where_clauses.append("arena_season IS NOT NULL")
    if tournament_only:
        where_clauses.append("COALESCE(is_tournament, FALSE)")
    if starting_positions:
        where_clauses.append("starting_position IN UNNEST(@starting_positions)")
        query_parameters.append(bigquery.ArrayQueryParameter(
            "starting_positions", "STRING", starting_positions
        ))

    return " AND ".join(where_clauses), query_parameters


def _build_card_stats_query(where_sql, round_filter_active, selected_rounds):
    # Card moments are flattened during the daily refresh. Keeping the old
    # branch below for one rollout gives a simple rollback path, while this
    # early return removes all request-time array expansion.
    round_sql = ""
    if round_filter_active:
        exact = sorted(int(value) for value in selected_rounds if value != "6+")
        parts = []
        if exact:
            parts.append(f"played_round IN ({', '.join(map(str, exact))})")
        if "6+" in selected_rounds:
            parts.append("played_round >= 6")
        round_sql = " AND (" + " OR ".join(parts) + ")"
    show_context = not round_filter_active
    return f"""
    WITH filtered AS (
      SELECT * FROM `{PREPARED_CARD_MOMENTS_TABLE}`
      WHERE {where_sql}
    ),
    played_agg AS (
      SELECT
        card_name,
        card_type,
        COUNT(DISTINCT table_id) AS n_played,
        ROUND(AVG(elo_delta), 3) AS delta_played,
        AVG(elo_delta) AS delta_played_ci_mean,
        STDDEV_SAMP(elo_delta) AS delta_played_ci_sd,
        COUNT(elo_delta) AS delta_played_ci_n,
        ROUND(AVG(pre_match_elo), 0) AS avg_elo
      FROM filtered
      WHERE moment = 'played'{round_sql}
      GROUP BY card_name, card_type
    ),
    in_hand_agg AS (
      SELECT
        card_name,
        ROUND(AVG(elo_delta), 3) AS delta_in_hand,
        AVG(elo_delta) AS delta_in_hand_ci_mean,
        STDDEV_SAMP(elo_delta) AS delta_in_hand_ci_sd,
        COUNT(elo_delta) AS delta_in_hand_ci_n
      FROM filtered
      WHERE moment = 'in_hand' AND {str(show_context).upper()}
      GROUP BY card_name
    ),
    seen_agg AS (
      SELECT card_name, COUNT(DISTINCT table_id) AS n_seen
      FROM filtered
      WHERE moment = 'seen' AND {str(show_context).upper()}
      GROUP BY card_name
    )
    SELECT
      p.card_type,
      p.card_name,
      p.delta_played,
      {'h.delta_in_hand' if show_context else 'CAST(NULL AS FLOAT64)'} AS delta_in_hand,
      p.delta_played_ci_mean,
      p.delta_played_ci_sd,
      p.delta_played_ci_n,
      {'h.delta_in_hand_ci_mean' if show_context else 'CAST(NULL AS FLOAT64)'} AS delta_in_hand_ci_mean,
      {'h.delta_in_hand_ci_sd' if show_context else 'CAST(NULL AS FLOAT64)'} AS delta_in_hand_ci_sd,
      {'COALESCE(h.delta_in_hand_ci_n, 0)' if show_context else 'CAST(0 AS INT64)'} AS delta_in_hand_ci_n,
      p.avg_elo,
      p.n_played,
      {'s.n_seen' if show_context else 'CAST(NULL AS INT64)'} AS n_seen,
      CASE
        WHEN {str(not show_context).upper()} OR s.n_seen IS NULL OR s.n_seen = 0 THEN NULL
        ELSE ROUND(100.0 * p.n_played / s.n_seen, 2)
      END AS playrate_pct
    FROM played_agg p
    LEFT JOIN in_hand_agg h USING(card_name)
    LEFT JOIN seen_agg s USING(card_name)
    ORDER BY p.card_type, playrate_pct DESC NULLS LAST, n_played DESC
    """

    if round_filter_active:
        animal_round_sql = f" AND {_round_condition('pa', selected_rounds)}"
        sponsor_round_sql = f" AND {_round_condition('ps', selected_rounds)}"
        project_round_sql = f" AND {_round_condition('pp', selected_rounds)}"
        return f"""
        WITH log_filtered AS (
          SELECT table_id, player, played_animals, played_sponsors, played_projects, elo_delta, pre_match_elo
          FROM `{PREPARED_LOGS_TABLE}`
          WHERE {where_sql}
        ),
        played_animals AS (
          SELECT l.table_id, l.player, pa.animal AS card_name, 'animal' AS card_type, l.elo_delta, l.pre_match_elo
          FROM log_filtered l
          CROSS JOIN UNNEST(l.played_animals) AS pa
          WHERE pa.animal IS NOT NULL
            {animal_round_sql}
        ),
        played_sponsors AS (
          SELECT l.table_id, l.player, ps.sponsor AS card_name, 'sponsor' AS card_type, l.elo_delta, l.pre_match_elo
          FROM log_filtered l
          CROSS JOIN UNNEST(l.played_sponsors) AS ps
          WHERE ps.sponsor IS NOT NULL
            {sponsor_round_sql}
        ),
        played_projects AS (
          SELECT l.table_id, l.player, pp.project AS card_name, 'project' AS card_type, l.elo_delta, l.pre_match_elo
          FROM log_filtered l
          CROSS JOIN UNNEST(l.played_projects) AS pp
          WHERE pp.project IS NOT NULL
            AND LOWER(pp.project) NOT IN UNNEST(@excluded_projects)
            {project_round_sql}
        ),
        all_played AS (
          SELECT table_id, player, card_name, card_type, elo_delta, pre_match_elo FROM played_animals
          UNION ALL
          SELECT table_id, player, card_name, card_type, elo_delta, pre_match_elo FROM played_sponsors
          UNION ALL
          SELECT table_id, player, card_name, card_type, elo_delta, pre_match_elo FROM played_projects
        ),
        played_agg AS (
          SELECT
            card_name,
            card_type,
            COUNT(DISTINCT table_id) AS n_played,
            ROUND(AVG(elo_delta), 3) AS delta_played,
            AVG(elo_delta) AS delta_played_ci_mean,
            STDDEV_SAMP(elo_delta) AS delta_played_ci_sd,
            COUNT(elo_delta) AS delta_played_ci_n,
            ROUND(AVG(pre_match_elo), 0) AS avg_elo
          FROM all_played
          GROUP BY card_name, card_type
        )
        SELECT
          card_type,
          card_name,
          delta_played,
          CAST(NULL AS FLOAT64) AS delta_in_hand,
          delta_played_ci_mean,
          delta_played_ci_sd,
          delta_played_ci_n,
          CAST(NULL AS FLOAT64) AS delta_in_hand_ci_mean,
          CAST(NULL AS FLOAT64) AS delta_in_hand_ci_sd,
          CAST(0 AS INT64) AS delta_in_hand_ci_n,
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
        pre_match_elo
      FROM `{PREPARED_LOGS_TABLE}`
      WHERE {where_sql}
    ),
    played_animals AS (
      SELECT l.table_id, l.player, pa.animal AS card_name, 'animal' AS card_type, l.elo_delta, l.pre_match_elo
      FROM log_filtered l
      CROSS JOIN UNNEST(l.played_animals) AS pa
      WHERE pa.animal IS NOT NULL
    ),
    played_sponsors AS (
      SELECT l.table_id, l.player, ps.sponsor AS card_name, 'sponsor' AS card_type, l.elo_delta, l.pre_match_elo
      FROM log_filtered l
      CROSS JOIN UNNEST(l.played_sponsors) AS ps
      WHERE ps.sponsor IS NOT NULL
    ),
    played_projects AS (
      SELECT l.table_id, l.player, pp.project AS card_name, 'project' AS card_type, l.elo_delta, l.pre_match_elo
      FROM log_filtered l
      CROSS JOIN UNNEST(l.played_projects) AS pp
      WHERE pp.project IS NOT NULL
        AND LOWER(pp.project) NOT IN UNNEST(@excluded_projects)
    ),
    all_played AS (
      SELECT table_id, player, card_name, card_type, elo_delta, pre_match_elo FROM played_animals
      UNION ALL
      SELECT table_id, player, card_name, card_type, elo_delta, pre_match_elo FROM played_sponsors
      UNION ALL
      SELECT table_id, player, card_name, card_type, elo_delta, pre_match_elo FROM played_projects
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
        AVG(elo_delta) AS delta_played_ci_mean,
        STDDEV_SAMP(elo_delta) AS delta_played_ci_sd,
        COUNT(elo_delta) AS delta_played_ci_n,
        ROUND(AVG(pre_match_elo), 0) AS avg_elo
      FROM all_played
      GROUP BY card_name, card_type
    ),
    in_hand_agg AS (
      SELECT
        card_name,
        ROUND(AVG(elo_delta), 3) AS delta_in_hand,
        AVG(elo_delta) AS delta_in_hand_ci_mean,
        STDDEV_SAMP(elo_delta) AS delta_in_hand_ci_sd,
        COUNT(elo_delta) AS delta_in_hand_ci_n
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
      p.delta_played_ci_mean,
      p.delta_played_ci_sd,
      p.delta_played_ci_n,
      h.delta_in_hand_ci_mean,
      h.delta_in_hand_ci_sd,
      COALESCE(h.delta_in_hand_ci_n, 0) AS delta_in_hand_ci_n,
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
        pre_match_elo
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
        ROUND(AVG(elo_delta), 3) AS delta_dealt,
        AVG(elo_delta) AS delta_dealt_ci_mean,
        STDDEV_SAMP(elo_delta) AS delta_dealt_ci_sd,
        COUNT(elo_delta) AS delta_dealt_ci_n
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
        AVG(elo_delta) AS delta_kept_ci_mean,
        STDDEV_SAMP(elo_delta) AS delta_kept_ci_sd,
        COUNT(elo_delta) AS delta_kept_ci_n,
        ROUND(AVG(pre_match_elo), 0) AS avg_elo
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
      d.delta_dealt_ci_mean AS delta_played_ci_mean,
      d.delta_dealt_ci_sd AS delta_played_ci_sd,
      COALESCE(d.delta_dealt_ci_n, 0) AS delta_played_ci_n,
      k.delta_kept_ci_mean AS delta_in_hand_ci_mean,
      k.delta_kept_ci_sd AS delta_in_hand_ci_sd,
      COALESCE(k.delta_kept_ci_n, 0) AS delta_in_hand_ci_n,
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
    WITH filtered AS (
      SELECT *
      FROM `{PREPARED_ENDGAME_EVENTS_TABLE}`
      WHERE {where_sql}
    ),
    dealt_counts AS (
      SELECT
        card_name,
        COUNT(*) AS n_dealt
      FROM filtered
      WHERE event_role = 'dealt'
      GROUP BY card_name
    ),
    dealt_delta AS (
      SELECT
        card_name,
        ROUND(AVG(elo_delta), 3) AS delta_dealt,
        AVG(elo_delta) AS delta_dealt_ci_mean,
        STDDEV_SAMP(elo_delta) AS delta_dealt_ci_sd,
        COUNT(elo_delta) AS delta_dealt_ci_n
      FROM filtered
      WHERE event_role = 'dealt_delta'
      GROUP BY card_name
    ),
    scored AS (
      SELECT
        card_name,
        COUNT(*) AS n_scored,
        ROUND(AVG(elo_delta), 3) AS delta_scored,
        AVG(elo_delta) AS delta_scored_ci_mean,
        STDDEV_SAMP(elo_delta) AS delta_scored_ci_sd,
        COUNT(elo_delta) AS delta_scored_ci_n,
        ROUND(AVG(pre_match_elo), 0) AS avg_elo,
        ROUND(AVG(cp), 2) AS avg_cp
      FROM filtered
      WHERE event_role = 'scored'
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
      dd.delta_dealt_ci_mean AS delta_played_ci_mean,
      dd.delta_dealt_ci_sd AS delta_played_ci_sd,
      COALESCE(dd.delta_dealt_ci_n, 0) AS delta_played_ci_n,
      s.delta_scored_ci_mean AS delta_in_hand_ci_mean,
      s.delta_scored_ci_sd AS delta_in_hand_ci_sd,
      COALESCE(s.delta_scored_ci_n, 0) AS delta_in_hand_ci_n,
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
    completed_tables AS (
      SELECT p.table_id
      FROM `{PREPARED_LOGS_TABLE}` p
      JOIN table_scope s USING(table_id)
      GROUP BY p.table_id
      HAVING COUNTIF(COALESCE(p.concede, 0) != 0) = 0
        AND COUNTIF(NOT COALESCE(SAFE_CAST(p.end_game_triggered AS BOOL), FALSE)) = 0
    ),
    scored_events AS (
      SELECT
        TRIM(score.endgame) AS card_name,
        SAFE_CAST(score.cp AS INT64) AS cp
      FROM log_filtered lf
      JOIN completed_tables n USING(table_id)
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
    completed_tables AS (
      SELECT p.table_id
      FROM `{PREPARED_LOGS_TABLE}` p
      JOIN table_scope s USING(table_id)
      GROUP BY p.table_id
      HAVING COUNTIF(COALESCE(p.concede, 0) != 0) = 0
        AND COUNTIF(NOT COALESCE(SAFE_CAST(p.end_game_triggered AS BOOL), FALSE)) = 0
    ),
    scored_events AS (
      SELECT
        TRIM(score.endgame) AS card_name,
        lf.Map AS map_name,
        SAFE_CAST(score.cp AS FLOAT64) AS cp
      FROM log_filtered lf
      JOIN completed_tables n USING(table_id)
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
    arena_only=False,
    tournament_only=False,
    starting_positions=None,
):
    # Elo NULLs remain NULL in prepared data and statistical calculations.
    # Only range comparisons treat missing metadata as zero, allowing an
    # unrestricted/blank minimum of zero to retain those observations.
    where_clauses = [
        "CAST(is_mw AS INT64) = @is_mw",
        _completed_game_sql(),
    ]
    query_parameters = [bigquery.ScalarQueryParameter("is_mw", "INT64", is_mw)]

    if player_elo_min is not None:
        where_clauses.append("COALESCE(pre_match_elo, 0) >= @player_elo_min")
        query_parameters.append(bigquery.ScalarQueryParameter("player_elo_min", "INT64", player_elo_min))
    if player_elo_max is not None:
        where_clauses.append("COALESCE(pre_match_elo, 0) <= @player_elo_max")
        query_parameters.append(bigquery.ScalarQueryParameter("player_elo_max", "INT64", player_elo_max))
    if opponent_elo_min is not None:
        where_clauses.append("COALESCE(opponent_pre_match_elo, 0) >= @opponent_elo_min")
        query_parameters.append(bigquery.ScalarQueryParameter("opponent_elo_min", "INT64", opponent_elo_min))
    if opponent_elo_max is not None:
        where_clauses.append("COALESCE(opponent_pre_match_elo, 0) <= @opponent_elo_max")
        query_parameters.append(bigquery.ScalarQueryParameter("opponent_elo_max", "INT64", opponent_elo_max))
    if date_from:
        where_clauses.append("game_date >= @date_from")
        query_parameters.append(bigquery.ScalarQueryParameter("date_from", "DATE", date_from))
    if date_to:
        where_clauses.append("game_date <= @date_to")
        query_parameters.append(bigquery.ScalarQueryParameter("date_to", "DATE", date_to))
    if arena_only:
        where_clauses.append("arena_season IS NOT NULL")
    if tournament_only:
        where_clauses.append("COALESCE(is_tournament, FALSE)")
    if starting_positions:
        where_clauses.append("starting_position IN UNNEST(@starting_positions)")
        query_parameters.append(bigquery.ArrayQueryParameter(
            "starting_positions", "STRING", starting_positions
        ))

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
    completed_only,
    exclude_invalid_maps=True,
    arena_only=False,
    tournament_only=False,
    starting_positions=None,
):
    # Home passes exclude_invalid_maps=False so its aggregate tiles use the
    # same complete map population shown by its default filter chips. Keep the
    # restricted default for all analytical pages. As in the Logs builder,
    # COALESCE belongs only to Elo range predicates; source values remain NULL.
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
        where_clauses.append("COALESCE(f.pre_match_elo, 0) >= @player_elo_min")
        query_parameters.append(bigquery.ScalarQueryParameter("player_elo_min", "INT64", player_elo_min))
    if player_elo_max is not None:
        where_clauses.append("COALESCE(f.pre_match_elo, 0) <= @player_elo_max")
        query_parameters.append(bigquery.ScalarQueryParameter("player_elo_max", "INT64", player_elo_max))
    if opponent_elo_min is not None:
        where_clauses.append("COALESCE(f.opponent_pre_match_elo, 0) >= @opponent_elo_min")
        query_parameters.append(bigquery.ScalarQueryParameter("opponent_elo_min", "INT64", opponent_elo_min))
    if opponent_elo_max is not None:
        where_clauses.append("COALESCE(f.opponent_pre_match_elo, 0) <= @opponent_elo_max")
        query_parameters.append(bigquery.ScalarQueryParameter("opponent_elo_max", "INT64", opponent_elo_max))
    if date_from:
        where_clauses.append("CAST(f.game_ended_at AS DATE) >= @date_from")
        query_parameters.append(bigquery.ScalarQueryParameter("date_from", "DATE", date_from))
    if date_to:
        where_clauses.append("CAST(f.game_ended_at AS DATE) <= @date_to")
        query_parameters.append(bigquery.ScalarQueryParameter("date_to", "DATE", date_to))
    if completed_only:
        where_clauses.append(_completed_game_sql("f"))
    if arena_only:
        where_clauses.append("f.arena_season IS NOT NULL")
    if tournament_only:
        where_clauses.append("COALESCE(f.is_tournament, FALSE)")
    if starting_positions:
        where_clauses.append("f.starting_position IN UNNEST(@starting_positions)")
        query_parameters.append(bigquery.ArrayQueryParameter(
            "starting_positions", "STRING", starting_positions
        ))

    return " AND ".join(where_clauses), query_parameters


def _maps_metric_definitions():
    """Canonical metric catalog shared by Maps/Metrics and Players/General."""
    return [
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
        ("money_gained_income", 33, "Money gained (income)", None, False, "number", False),
        ("money_spent_animals_pct", 34, "Money spent (Animals)", "Animals spending as a percentage of total money spent", False, "percent", False),
        ("money_spent_build_pct", 35, "Money spent (Build)", "Build spending as a percentage of total money spent", False, "percent", False),
        ("money_spent_donations_pct", 36, "Money spent (Donations)", "Donations spending as a percentage of total money spent", False, "percent", False),
        ("money_spent_range_pct", 37, "Money spent (Range)", "Range spending as a percentage of total money spent", False, "percent", False),
        ("cards_drawn_deck", 39, "Cards drawn (deck)", None, False, "number", False),
        ("cards_drawn_range", 40, "Cards drawn (Range)", None, False, "number", False),
        ("cards_snapped", 41, "Cards snapped", None, False, "number", False),
        ("cards_discarded", 42, "Cards discarded", None, False, "number", False),
        ("enclosures", 43, "Enclosures", None, False, "number", False),
        ("kiosks", 44, "Kiosks", None, False, "number", False),
        ("pavilions", 45, "Pavilions", None, False, "number", False),
        ("unique_buildings", 46, "Unique buildings", None, False, "number", False),
        ("animals_played", 47, "Animals played", None, False, "number", False),
        ("animals_released", 48, "Animals released", None, False, "number", False),
        ("sponsors_played", 49, "Sponsors played", None, False, "number", False),
        ("bird_icons", 50, "Bird icons", None, False, "number", False),
        ("herbivore_icons", 51, "Herbivore icons", None, False, "number", False),
        ("predator_icons", 52, "Predator icons", None, False, "number", False),
        ("primate_icons", 53, "Primate icons", None, False, "number", False),
        ("reptile_icons", 54, "Reptile icons", None, False, "number", False),
        ("sea_animal_icons", 55, "Sea Animal icons", None, False, "number", False),
        ("bear_icons", 56, "Bear icons", None, False, "number", False),
        ("petting_zoo_icons", 57, "Petting zoo icons", None, False, "number", False),
        ("africa_icons", 58, "Africa icons", None, False, "number", False),
        ("america_icons", 59, "America icons", None, False, "number", False),
        ("asia_icons", 60, "Asia icons", None, False, "number", False),
        ("australia_icons", 61, "Australia icons", None, False, "number", False),
        ("europe_icons", 62, "Europe icons", None, False, "number", False),
        ("rock_icons", 63, "Rock icons", None, False, "number", False),
        ("water_icons", 64, "Water icons", None, False, "number", False),
        ("science_icons", 65, "Science icons", None, False, "number", False),
    ]


def _build_maps_metrics_query(where_sql):
    metric_definitions = _maps_metric_definitions()
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
    map_tooltip_selects = ",\n      ".join(
        f"ROUND(MAX(IF(map_name = '{m['full']}', tooltip_value, NULL)), 4) AS tooltip_{m['key']}"
        for m in ALL_MAPS_FOR_METRICS
    )
    return f"""
    WITH filtered AS (
      SELECT *
      FROM `{PREPARED_FULL_STATS_TABLE}`
      WHERE {where_sql}
    ),
    per_map_base AS (
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
        AVG(100 * SAFE_DIVIDE(
          CASE
            WHEN Map IN ('Map 5: Park Restaurant', 'Map 5a: Park Restaurant', 'Map 10: Rescue Station') THEN 43
            WHEN Map = 'Map 0' THEN 39
            ELSE 42
          END - SAFE_CAST(Empty_hexes AS FLOAT64),
          CASE
            WHEN Map IN ('Map 5: Park Restaurant', 'Map 5a: Park Restaurant', 'Map 10: Rescue Station') THEN 43
            WHEN Map = 'Map 0' THEN 39
            ELSE 42
          END
        )) AS cover_pct,
        AVG(100 * IF(SAFE_CAST(Empty_hexes AS INT64) = 0, 1, 0)) AS fill_pct,
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
        AVG(SAFE_CAST(Money_gained_through_income AS FLOAT64)) AS money_gained_income,
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
    per_map AS (
      SELECT
        base.*,
        100 * SAFE_DIVIDE(money_spent_animals,
          money_spent_animals + money_spent_build + money_spent_donations + money_spent_range
        ) AS money_spent_animals_pct,
        100 * SAFE_DIVIDE(money_spent_build,
          money_spent_animals + money_spent_build + money_spent_donations + money_spent_range
        ) AS money_spent_build_pct,
        100 * SAFE_DIVIDE(money_spent_donations,
          money_spent_animals + money_spent_build + money_spent_donations + money_spent_range
        ) AS money_spent_donations_pct,
        100 * SAFE_DIVIDE(money_spent_range,
          money_spent_animals + money_spent_build + money_spent_donations + money_spent_range
        ) AS money_spent_range_pct,
        money_spent_animals AS tooltip_money_spent_animals,
        money_spent_build AS tooltip_money_spent_build,
        money_spent_donations AS tooltip_money_spent_donations,
        money_spent_range AS tooltip_money_spent_range
      FROM per_map_base base
    ),
    metric_config AS (
      SELECT *
      FROM UNNEST([
        {metric_config_sql}
      ])
    ),
    unpivoted AS (
      SELECT
        map_name,
        metric_key,
        value,
        CASE metric_key
          WHEN 'money_spent_animals_pct' THEN tooltip_money_spent_animals
          WHEN 'money_spent_build_pct' THEN tooltip_money_spent_build
          WHEN 'money_spent_donations_pct' THEN tooltip_money_spent_donations
          WHEN 'money_spent_range_pct' THEN tooltip_money_spent_range
          ELSE NULL
        END AS tooltip_value
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
        u.value,
        u.tooltip_value
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
      {map_value_selects},
      {map_tooltip_selects}
    FROM metric_values
    GROUP BY sort_order, metric, tooltip, is_default, format, lower_is_better
    ORDER BY sort_order
    """


def _players_metric_definitions():
    """Players keeps the Maps catalog but replaces Rounds with two break metrics."""
    definitions = []
    next_order = 1
    for key, _sort_order, label, tooltip, is_default, value_format, lower_is_better in _maps_metric_definitions():
        if key in {"games", "rounds"}:
            continue
        if key == "turns":
            definitions.append((key, next_order, label, tooltip, is_default, value_format, lower_is_better))
            next_order += 1
            definitions.append((
                "breaks_triggered", next_order, "Breaks triggered", None, False, "number", False
            ))
            next_order += 1
            definitions.append((
                "break_pct", next_order, "Break%", "percentage of available breaks that were triggered", False, "percent", False
            ))
            next_order += 1
            continue
        if key == "money_per_turn":
            label = "$ gained per turn"
        definitions.append((key, next_order, label, tooltip, is_default, value_format, lower_is_better))
        next_order += 1
    return definitions


def _players_metric_expressions():
    """Full Sample expressions for Players, including player-only break metrics."""
    return {
        "turns": "SAFE_CAST(Number_of_turns AS FLOAT64)",
        "breaks_triggered": "SAFE_CAST(Number_of_breaks_triggered AS FLOAT64)",
        "break_pct": "100 * SAFE_DIVIDE(SAFE_CAST(Number_of_breaks_triggered AS FLOAT64), NULLIF(SAFE_CAST(total_breaks AS FLOAT64), 0))",
        "points_per_turn": "SAFE_CAST(points_per_turn AS FLOAT64)",
        "points_per_money": "SAFE_CAST(points_per_money AS FLOAT64)",
        "money_per_turn": "SAFE_DIVIDE(SAFE_CAST(Money_gained AS FLOAT64), NULLIF(SAFE_CAST(Number_of_turns AS FLOAT64), 0))",
        "score": "SAFE_CAST(Score AS FLOAT64)",
        "appeal": "SAFE_CAST(Appeal AS FLOAT64)",
        "conservation": "SAFE_CAST(Conservation AS FLOAT64)",
        "reputation": "SAFE_CAST(Reputation AS FLOAT64)",
        "projects": "SAFE_CAST(Conservation_project_association_tasks AS FLOAT64)",
        "upgrades": "SAFE_CAST(Upgraded_action_cards AS FLOAT64)",
        "workers": "SAFE_CAST(Association_workers AS FLOAT64)",
        "cover_pct": "100 * SAFE_DIVIDE(CASE WHEN Map IN ('Map 5: Park Restaurant', 'Map 5a: Park Restaurant', 'Map 10: Rescue Station') THEN 43 WHEN Map = 'Map 0' THEN 39 ELSE 42 END - SAFE_CAST(Empty_hexes AS FLOAT64), CASE WHEN Map IN ('Map 5: Park Restaurant', 'Map 5a: Park Restaurant', 'Map 10: Rescue Station') THEN 43 WHEN Map = 'Map 0' THEN 39 ELSE 42 END)",
        "fill_pct": "100 * IF(SAFE_CAST(Empty_hexes AS INT64) = 0, 1, 0)",
        "animals_pct": "100 * CAST(COALESCE(Upgraded_Animals_action_card, FALSE) AS INT64)",
        "association_pct": "100 * CAST(COALESCE(Upgraded_Association_action_card, FALSE) AS INT64)",
        "build_pct": "100 * CAST(COALESCE(Upgraded_Build_action_card, FALSE) AS INT64)",
        "cards_pct": "100 * CAST(COALESCE(Upgraded_Cards_action_card, FALSE) AS INT64)",
        "sponsors_pct": "100 * CAST(COALESCE(Upgraded_Sponsors_action_card, FALSE) AS INT64)",
        "determinations": "SAFE_CAST(determinations AS FLOAT64)",
        "animals_actions": "SAFE_CAST(Animals_actions AS FLOAT64)",
        "association_actions": "SAFE_CAST(Association_actions AS FLOAT64)",
        "build_actions": "SAFE_CAST(Build_actions AS FLOAT64)",
        "cards_actions": "SAFE_CAST(Cards_actions AS FLOAT64)",
        "sponsors_actions": "SAFE_CAST(Sponsors_actions AS FLOAT64)",
        "universities": "SAFE_CAST(University_association_tasks AS FLOAT64)",
        "partner_zoos": "SAFE_CAST(Partner_zoo_association_tasks AS FLOAT64)",
        "x_tokens_gained": "SAFE_CAST(X_Tokens_gained AS FLOAT64)",
        "x_tokens_spent": "SAFE_CAST(X_Tokens_used AS FLOAT64)",
        "x_backs": "SAFE_CAST(X_Tokens_gained_instead_of_action AS FLOAT64)",
        "money_gained": "SAFE_CAST(Money_gained AS FLOAT64)",
        "money_gained_income": "SAFE_CAST(Money_gained_through_income AS FLOAT64)",
        "cards_drawn_deck": "SAFE_CAST(Cards_drawn_from_deck AS FLOAT64)",
        "cards_drawn_range": "SAFE_CAST(Cards_taken_from_reputation_range AS FLOAT64)",
        "cards_snapped": "SAFE_CAST(Snapped_cards AS FLOAT64)",
        "cards_discarded": "SAFE_CAST(Discarded_cards AS FLOAT64)",
        "enclosures": "SAFE_CAST(Built_enclosures AS FLOAT64)",
        "kiosks": "SAFE_CAST(Built_kiosks AS FLOAT64)",
        "pavilions": "SAFE_CAST(Built_pavilions AS FLOAT64)",
        "unique_buildings": "SAFE_CAST(Built_unique_buildings AS FLOAT64)",
        "animals_played": "SAFE_CAST(Played_animals AS FLOAT64)",
        "animals_released": "SAFE_CAST(Released_animals AS FLOAT64)",
        "sponsors_played": "SAFE_CAST(Played_sponsors AS FLOAT64)",
        "bird_icons": "SAFE_CAST(Bird_icons AS FLOAT64)",
        "herbivore_icons": "SAFE_CAST(Herbivore_icons AS FLOAT64)",
        "predator_icons": "SAFE_CAST(Predator_icons AS FLOAT64)",
        "primate_icons": "SAFE_CAST(Primate_icons AS FLOAT64)",
        "reptile_icons": "SAFE_CAST(Reptile_icons AS FLOAT64)",
        "sea_animal_icons": "SAFE_CAST(Sea_Animal_icons AS FLOAT64)",
        "bear_icons": "SAFE_CAST(Bear_icons AS FLOAT64)",
        "petting_zoo_icons": "SAFE_CAST(Petting_Zoo_icons AS FLOAT64)",
        "africa_icons": "SAFE_CAST(Africa_icons AS FLOAT64)",
        "america_icons": "SAFE_CAST(Americas_icons AS FLOAT64)",
        "asia_icons": "SAFE_CAST(Asia_icons AS FLOAT64)",
        "australia_icons": "SAFE_CAST(Australia_icons AS FLOAT64)",
        "europe_icons": "SAFE_CAST(Europe_icons AS FLOAT64)",
        "rock_icons": "SAFE_CAST(Rock_icons AS FLOAT64)",
        "water_icons": "SAFE_CAST(Water_icons AS FLOAT64)",
        "science_icons": "SAFE_CAST(Science_icons AS FLOAT64)",
    }


def _players_money_fields():
    return {
        "money_spent_animals_pct": "Money_spent_on_animals",
        "money_spent_build_pct": "Money_spent_on_enclosures",
        "money_spent_donations_pct": "Money_spent_on_donations",
        "money_spent_range_pct": "Money_spent_for_playing_cards_from_reputation_range",
    }


def _players_history_groups():
    """Return the invisible compatibility groups used by Players graphs."""
    groups = [
        (
            "upgrade_percentages",
            ["animals_pct", "association_pct", "build_pct", "cards_pct", "sponsors_pct"],
        ),
        (
            "action_counts",
            [
                "animals_actions", "association_actions", "build_actions",
                "cards_actions", "sponsors_actions",
            ],
        ),
        ("association_bonuses", ["universities", "partner_zoos"]),
        ("x_tokens", ["x_tokens_gained", "x_tokens_spent"]),
        ("small_buildings", ["kiosks", "pavilions"]),
        (
            "icons",
            [
                "bird_icons", "herbivore_icons", "predator_icons",
                "primate_icons", "reptile_icons", "sea_animal_icons",
                "bear_icons", "petting_zoo_icons", "africa_icons",
                "america_icons", "asia_icons", "australia_icons",
                "europe_icons", "rock_icons", "water_icons", "science_icons",
            ],
        ),
    ]
    grouped = {
        key: group_name
        for group_name, keys in groups
        for key in keys
    }
    for key, *_ in _players_metric_definitions():
        grouped.setdefault(key, f"metric:{key}")
    return grouped


def _players_history_metric_catalog():
    groups = _players_history_groups()
    return {
        key: {
            "key": key,
            "sort_order": int(sort_order),
            "label": label,
            "format": value_format,
            "group": groups[key],
        }
        for key, sort_order, label, _tooltip, _is_default, value_format,
        _lower_is_better in _players_metric_definitions()
    }


def _players_history_value_sql(metric_key, alias="f"):
    money_fields = _players_money_fields()
    if metric_key not in money_fields:
        return f"{alias}.{metric_key}"
    denominator = " + ".join(
        f"COALESCE({alias}.{key}_raw, 0)" for key in money_fields
    )
    return (
        f"100 * SAFE_DIVIDE({alias}.{metric_key}_raw, "
        f"NULLIF(({denominator}), 0))"
    )


def _players_history_cache_blob_name(
    data_version,
    is_mw,
    identities,
    metric_keys,
    selected_maps,
    opponent_elo_min,
    opponent_elo_max,
    date_from,
    date_to,
    last_x_games,
    arena_seasons,
    tournament_only,
    starting_positions,
):
    scope = {
        "schema": 3,
        "data_version": data_version,
        "is_mw": int(is_mw),
        "identities": sorted(identities),
        "metrics": sorted(metric_keys),
        "maps": sorted(selected_maps),
        "opponent_elo_min": opponent_elo_min,
        "opponent_elo_max": opponent_elo_max,
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "last_x_games": last_x_games,
        "arena_seasons": sorted(arena_seasons or []),
        "tournament_only": bool(tournament_only),
        "starting_positions": sorted(starting_positions or []),
    }
    digest = hashlib.sha256(
        json.dumps(scope, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:32]
    return f"{CACHE_PREFIX}/filters/players-history/{digest}.json"


def _query_players_history(
    is_mw,
    identities,
    metric_keys,
    selected_maps,
    opponent_elo_min,
    opponent_elo_max,
    date_from,
    date_to,
    last_x_games,
    arena_seasons,
    tournament_only,
    starting_positions,
):
    """Return compact trailing-100 histories for selected merged identities."""
    catalog = _players_history_metric_catalog()
    invalid = [key for key in metric_keys if key not in catalog]
    if invalid:
        raise ValueError(f"Unknown Players history metric: {invalid[0]}")

    value_selects = ",\n        ".join(
        f"{_players_history_value_sql(key)} AS {key}" for key in metric_keys
    )
    rolling_selects = ",\n        ".join(
        f"AVG({key}) OVER ("
        "PARTITION BY player_identity "
        "ORDER BY game_ended_at, CAST(table_id AS STRING) "
        f"ROWS BETWEEN {PLAYERS_HISTORY_WINDOW - 1} PRECEDING AND CURRENT ROW"
        f") AS {key}"
        for key in metric_keys
    )
    point_struct_fields = ", ".join(
        ["r.game_number", "r.game_ended_at"]
        + [f"r.{key}" for key in metric_keys]
    )
    where = [
        "f.identity_bucket IN UNNEST(@identity_buckets)",
        "f.player_identity IN UNNEST(@identities)",
        "CAST(f.is_mw AS INT64) = @is_mw",
        "f.Map IN UNNEST(@selected_maps)",
        _completed_game_sql("f"),
    ]
    parameters = [
        bigquery.ArrayQueryParameter("identity_buckets", "INT64", [
            int(hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8], 16) % 1024
            for identity in identities
        ]),
        bigquery.ArrayQueryParameter("identities", "STRING", identities),
        bigquery.ScalarQueryParameter("is_mw", "INT64", int(is_mw)),
        bigquery.ArrayQueryParameter("selected_maps", "STRING", selected_maps),
        bigquery.ScalarQueryParameter("last_x_games", "INT64", int(last_x_games or 0)),
    ]
    if opponent_elo_min is not None:
        where.append("COALESCE(f.opponent_pre_match_elo, 0) >= @opponent_elo_min")
        parameters.append(bigquery.ScalarQueryParameter(
            "opponent_elo_min", "INT64", opponent_elo_min
        ))
    if opponent_elo_max is not None:
        where.append("COALESCE(f.opponent_pre_match_elo, 0) <= @opponent_elo_max")
        parameters.append(bigquery.ScalarQueryParameter(
            "opponent_elo_max", "INT64", opponent_elo_max
        ))
    if date_from:
        where.append("f.game_date >= @date_from")
        parameters.append(bigquery.ScalarQueryParameter("date_from", "DATE", date_from))
    if date_to:
        where.append("f.game_date <= @date_to")
        parameters.append(bigquery.ScalarQueryParameter("date_to", "DATE", date_to))
    if arena_seasons:
        where.append("f.arena_season IN UNNEST(@arena_seasons)")
        parameters.append(bigquery.ArrayQueryParameter(
            "arena_seasons", "STRING", arena_seasons
        ))
    if tournament_only:
        where.append("COALESCE(f.is_tournament, FALSE)")
    if starting_positions:
        where.append("f.starting_position IN UNNEST(@starting_positions)")
        parameters.append(bigquery.ArrayQueryParameter(
            "starting_positions", "STRING", starting_positions
        ))

    query = f"""
    WITH filtered AS (
      SELECT
        f.player_identity,
        f.table_id,
        f.game_ended_at,
        {value_selects}
      FROM `{PREPARED_PLAYERS_RECENT_TABLE}` f
      WHERE {' AND '.join(where)}
    ),
    newest AS (
      SELECT
        *,
        ROW_NUMBER() OVER (
          PARTITION BY player_identity
          ORDER BY game_ended_at DESC, CAST(table_id AS STRING) DESC
        ) AS newest_rank
      FROM filtered
    ),
    limited AS (
      SELECT * EXCEPT(newest_rank)
      FROM newest
      WHERE @last_x_games = 0 OR newest_rank <= @last_x_games
    ),
    ordered AS (
      SELECT
        *,
        ROW_NUMBER() OVER (
          PARTITION BY player_identity
          ORDER BY game_ended_at, CAST(table_id AS STRING)
        ) AS game_number,
        COUNT(*) OVER (PARTITION BY player_identity) AS game_count
      FROM limited
    ),
    rolled AS (
      SELECT
        player_identity,
        game_number,
        game_count,
        game_ended_at,
        {rolling_selects}
      FROM ordered
    ),
    counts AS (
      SELECT player_identity, MAX(game_count) AS game_count
      FROM ordered
      GROUP BY player_identity
    ),
    point_arrays AS (
      SELECT
        player_identity,
        ARRAY_AGG(
          STRUCT({point_struct_fields})
          ORDER BY game_number
        ) AS points
      FROM rolled r
      WHERE game_number >= {PLAYERS_HISTORY_WINDOW}
      GROUP BY player_identity
    )
    SELECT c.player_identity, c.game_count, p.points
    FROM counts c
    LEFT JOIN point_arrays p USING(player_identity)
    ORDER BY c.player_identity
    """
    started_at = time.perf_counter()
    client = bigquery.Client(project=BIGQUERY_JOB_PROJECT)
    job = client.query(
        query,
        job_config=bigquery.QueryJobConfig(
            query_parameters=parameters,
            use_query_cache=True,
        ),
        location=BIGQUERY_LOCATION,
    )
    results = job.result()
    players = []
    for row in results:
        points = list(row.points or [])
        # Nested STRUCT values can be returned as dictionaries by newer
        # google-cloud-bigquery releases and as Row objects by older ones.
        # Accept both so history serialization is independent of the runtime.
        point_value = lambda point, key: (
            point.get(key) if isinstance(point, dict) else getattr(point, key)
        )
        players.append({
            "player_identity": row.player_identity,
            "game_count": int(row.game_count or 0),
            "game_numbers": [
                int(point_value(point, "game_number")) for point in points
            ],
            "timestamps": [
                _dt_iso(point_value(point, "game_ended_at")) for point in points
            ],
            "series": {
                key: [
                    (
                        float(point_value(point, key))
                        if point_value(point, key) is not None else None
                    )
                    for point in points
                ]
                for key in metric_keys
            },
        })
    return {
        "status": "ok",
        "window_size": PLAYERS_HISTORY_WINDOW,
        "metrics": [catalog[key] for key in metric_keys],
        "players": players,
        "_server_timing": {
            "query_wait_ms": _ms_since(started_at),
            "job_id": job.job_id,
            "job_cache_hit": job.cache_hit,
            "job_total_bytes_processed": job.total_bytes_processed,
            "job_total_slot_ms": job.slot_millis,
        },
    }


def _load_players_history(
    data_version,
    players_view,
    aliases,
    identities,
    metric_keys,
    is_mw,
    selected_maps,
    opponent_elo_min,
    opponent_elo_max,
    date_from,
    date_to,
    last_x_games,
    arena_seasons,
    tournament_only,
    starting_positions,
):
    blob_name = _players_history_cache_blob_name(
        data_version,
        is_mw,
        identities,
        metric_keys,
        selected_maps,
        opponent_elo_min,
        opponent_elo_max,
        date_from,
        date_to,
        last_x_games,
        arena_seasons,
        tournament_only,
        starting_positions,
    )
    cached = _read_cache_blob(blob_name, "players_history_hit")
    if cached and isinstance(cached.get("players"), list):
        core = cached
        timing = {"cache_lookup_ms": 0}
    else:
        core = _query_players_history(
            is_mw,
            sorted(set(identities)),
            metric_keys,
            selected_maps,
            opponent_elo_min,
            opponent_elo_max,
            date_from,
            date_to,
            last_x_games,
            arena_seasons,
            tournament_only,
            starting_positions,
        )
        timing = core.pop("_server_timing", {})
        _enqueue_cache_blob_write(
            blob_name, core, "players_history_refreshed", compresslevel=3
        )

    by_identity = {
        item.get("player_identity"): item for item in core.get("players", [])
    }
    decorated = []
    for alias, identity in zip(aliases, identities):
        source = by_identity.get(identity) or {
            "game_count": 0,
            "game_numbers": [],
            "timestamps": [],
            "series": {key: [] for key in metric_keys},
        }
        decorated.append({
            "name": alias,
            "game_count": int(source.get("game_count") or 0),
            "game_numbers": source.get("game_numbers") or [],
            "timestamps": source.get("timestamps") or [],
            "series": source.get("series") or {},
        })

    minimum_failed = [
        item for item in decorated
        if int(item.get("game_count") or 0) < PLAYERS_GRAPH_MIN_GAMES
    ]
    if minimum_failed:
        message = (
            "Minimum game count: 250"
            if players_view == PLAYERS_VIEW_GENERAL
            else "Minimum game count for any player: 250"
        )
        raise ValueError(message)

    payload = {
        "status": "ok",
        "stats_page": STATS_PAGE_PLAYERS,
        "players_view": players_view,
        "players_history": True,
        "window_size": PLAYERS_HISTORY_WINDOW,
        "metrics": core.get("metrics") or [],
        "players": decorated,
        "cache_status": (
            cached.get("cache_status") if cached else "players_history_write_queued"
        ),
        "_server_timing": timing,
    }
    return payload


def _players_total_spent_sql():
    return "(SAFE_CAST(Money_spent_on_animals AS FLOAT64) + SAFE_CAST(Money_spent_on_enclosures AS FLOAT64) + SAFE_CAST(Money_spent_on_donations AS FLOAT64) + SAFE_CAST(Money_spent_for_playing_cards_from_reputation_range AS FLOAT64))"


def _build_players_query(where_sql, component="combined", source_table=None):
    """Aggregate every Players metric after one scan of each required population.

    `baseline` excludes the selected-player branch, while `selected` avoids the
    global comparison populations. The live endpoint uses those components for
    independent caching; default snapshot generation uses `combined`.
    """
    if component not in {"combined", "baseline", "selected"}:
        raise ValueError("Invalid Players query component")
    source_table = source_table or (
        PREPARED_PLAYERS_BASELINE_TABLE
        if component == "baseline"
        else PREPARED_PLAYERS_TABLE
    )
    use_recent = source_table == PREPARED_PLAYERS_RECENT_TABLE
    source_from_sql = f"`{source_table}` f"
    recent_parent_predicate = (
        "AND f.identity_bucket = @players_identity_bucket"
        if use_recent else ""
    )
    # Put the exact player predicate in the physical prepared-table scan for a
    # selected-only request. Leaving it in a downstream CTE prevents reliable
    # cluster pruning and makes a one-player query scan the global population.
    selected_scope_sql = (
        "AND NULLIF(@players_identity, '') IS NOT NULL "
        "AND f.player_identity = @players_identity"
        if component == "selected" else ""
    )
    metric_definitions = _players_metric_definitions()
    money_fields = _players_money_fields()
    ordinary_keys = [key for key, *_ in metric_definitions if key not in money_fields]
    baseline_conditions = {
        "all_players": "TRUE",
        "winners": "is_winner",
        "experts": "pre_match_elo >= 500",
        "masters": "pre_match_elo >= 700",
    }

    baseline_fields = []
    for population, condition in baseline_conditions.items():
        baseline_fields.append(f"COUNTIF({condition}) AS count_{population}")
        baseline_fields.extend(
            f"AVG(IF({condition}, {key}, NULL)) AS {key}_{population}"
            for key in ordinary_keys
        )
        baseline_fields.extend(
            f"AVG(IF({condition}, {key}_raw, NULL)) AS {key}_raw_{population}"
            for key in money_fields
        )
    selected_fields = ["COUNT(*) AS count_player"]
    selected_fields.extend(f"AVG({key}) AS {key}_player" for key in ordinary_keys)
    selected_fields.extend(f"AVG({key}_raw) AS {key}_raw_player" for key in money_fields)
    selected_fields.append(
        "(SELECT IFNULL(ARRAY_AGG(STRUCT(player AS name, game_count AS game_count) "
        "ORDER BY player), ARRAY<STRUCT<name STRING, game_count INT64>>[]) "
        "FROM selected_account_rows) AS account_counts"
    )

    if component == "selected":
        baseline_agg = "SELECT " + ", ".join(
            ["0 AS count_all_players", "0 AS count_winners", "0 AS count_experts", "0 AS count_masters"]
            + [f"CAST(NULL AS FLOAT64) AS {key}_{population}" for population in baseline_conditions for key in ordinary_keys]
            + [f"CAST(NULL AS FLOAT64) AS {key}_raw_{population}" for population in baseline_conditions for key in money_fields]
        )
    else:
        baseline_agg = "SELECT\n        " + ",\n        ".join(baseline_fields) + "\n      FROM scoped"
    if component == "baseline":
        selected_agg = "SELECT " + ", ".join(
            ["0 AS count_player"]
            + [f"CAST(NULL AS FLOAT64) AS {key}_player" for key in ordinary_keys]
            + [f"CAST(NULL AS FLOAT64) AS {key}_raw_player" for key in money_fields]
            + [
                "ARRAY<STRUCT<name STRING, game_count INT64>>[] "
                "AS account_counts"
            ]
        )
    else:
        selected_agg = "SELECT\n        " + ",\n        ".join(selected_fields) + "\n      FROM selected"

    def metric_value(key, population, source):
        if key not in money_fields:
            return f"{source}.{key}_{population}"
        numerator = f"{source}.{key}_raw_{population}"
        denominator = " + ".join(
            f"{source}.{money_key}_raw_{population}" for money_key in money_fields
        )
        return f"100 * SAFE_DIVIDE({numerator}, {denominator})"

    def tooltip_value(key, population, source):
        return (
            f"{source}.{key}_raw_{population}"
            if key in money_fields else "CAST(NULL AS FLOAT64)"
        )

    metric_structs = []
    for key, sort_order, label, tooltip, is_default, value_format, lower_is_better in metric_definitions:
        fields = [
            f"{sort_order} AS sort_order",
            f"{_sql_string(label)} AS metric",
            f"{_sql_string(tooltip) if tooltip else 'CAST(NULL AS STRING)'} AS tooltip",
            f"{'TRUE' if is_default else 'FALSE'} AS is_default",
            f"{_sql_string(value_format)} AS format",
            f"{'TRUE' if lower_is_better else 'FALSE'} AS lower_is_better",
            f"{metric_value(key, 'player', 's')} AS player",
            "s.count_player AS count_player",
            f"{tooltip_value(key, 'player', 's')} AS tooltip_player",
            "s.account_counts AS account_counts",
        ]
        for population in baseline_conditions:
            fields.extend([
                f"{metric_value(key, population, 'b')} AS {population}",
                f"b.count_{population} AS count_{population}",
                f"{tooltip_value(key, population, 'b')} AS tooltip_{population}",
            ])
        metric_structs.append("STRUCT(" + ", ".join(fields) + ")")

    return f"""
    WITH scoped AS (
      SELECT f.*
      FROM {source_from_sql}
      WHERE {where_sql}
        AND {_completed_game_sql("f")}
        {selected_scope_sql}
        {recent_parent_predicate}
    ),
    selected_ranked AS (
      SELECT
        f.*,
        ROW_NUMBER() OVER (
          ORDER BY f.game_ended_at DESC, CAST(f.table_id AS STRING) DESC
        ) AS player_rank
      FROM scoped f
      WHERE NULLIF(@players_identity, '') IS NOT NULL
        AND f.player_identity = @players_identity
    ),
    selected AS (
      SELECT * FROM selected_ranked
      WHERE @last_x_games = 0 OR player_rank <= @last_x_games
    ),
    selected_account_rows AS (
      SELECT player, COUNT(*) AS game_count
      FROM selected
      GROUP BY player
    ),
    baseline_agg AS (
      {baseline_agg}
    ),
    selected_agg AS (
      {selected_agg}
    )
    SELECT metric_row.*
    FROM baseline_agg b
    CROSS JOIN selected_agg s
    CROSS JOIN UNNEST([
      {', '.join(metric_structs)}
    ]) AS metric_row
    ORDER BY metric_row.sort_order
    """


def _build_players_rollup_query(where_sql, component):
    """Build General from daily weighted moments when Last X is inactive."""
    if component not in {"baseline", "selected"}:
        raise ValueError("Players rollups require a single component")
    metric_definitions = _players_metric_definitions()
    money_fields = _players_money_fields()
    ordinary_keys = [
        key for key, *_ in metric_definitions if key not in money_fields
    ]
    metric_keys = ordinary_keys + [
        f"{key}_raw" for key in money_fields
    ]
    baseline_conditions = {
        "all_players": "TRUE",
        "winners": "is_winner",
        "experts": "is_expert",
        "masters": "is_master",
    }

    def weighted_average(key, condition="TRUE"):
        return (
            "SAFE_DIVIDE("
            f"SUM(IF({condition}, {key}_sum, 0)), "
            f"SUM(IF({condition}, {key}_count, 0)))"
        )

    if component == "baseline":
        source_table = PREPARED_PLAYERS_BASELINE_TABLE
        identity_predicate = ""
        baseline_fields = []
        for population, condition in baseline_conditions.items():
            baseline_fields.append(
                f"SUM(IF({condition}, observation_count, 0)) "
                f"AS count_{population}"
            )
            baseline_fields.extend(
                f"{weighted_average(key, condition)} AS {key}_{population}"
                for key in metric_keys
            )
        baseline_agg = (
            "SELECT\n        "
            + ",\n        ".join(baseline_fields)
            + "\n      FROM scoped"
        )
        selected_agg = "SELECT " + ", ".join(
            ["0 AS count_player"]
            + [
                f"CAST(NULL AS FLOAT64) AS {key}_player"
                for key in metric_keys
            ]
            + [
                "ARRAY<STRUCT<name STRING, game_count INT64>>[] "
                "AS account_counts"
            ]
        )
        account_cte = (
            "selected_account_rows AS ("
            "SELECT CAST(NULL AS STRING) AS player, 0 AS game_count "
            "FROM UNNEST([1]) WHERE FALSE)"
        )
    else:
        source_table = PREPARED_PLAYERS_IDENTITY_ROLLUP_TABLE
        identity_predicate = (
            "AND NULLIF(@players_identity, '') IS NOT NULL "
            "AND f.player_identity = @players_identity"
        )
        baseline_agg = "SELECT " + ", ".join(
            [
                "0 AS count_all_players",
                "0 AS count_winners",
                "0 AS count_experts",
                "0 AS count_masters",
            ]
            + [
                f"CAST(NULL AS FLOAT64) AS {key}_{population}"
                for population in baseline_conditions
                for key in metric_keys
            ]
        )
        selected_fields = ["SUM(observation_count) AS count_player"]
        selected_fields.extend(
            f"{weighted_average(key)} AS {key}_player" for key in metric_keys
        )
        selected_fields.append(
            "(SELECT IFNULL(ARRAY_AGG(STRUCT(player AS name, game_count AS game_count) "
            "ORDER BY player), ARRAY<STRUCT<name STRING, game_count INT64>>[]) "
            "FROM selected_account_rows) AS account_counts"
        )
        selected_agg = (
            "SELECT\n        "
            + ",\n        ".join(selected_fields)
            + "\n      FROM scoped"
        )
        account_cte = """
        selected_account_rows AS (
          SELECT player, SUM(observation_count) AS game_count
          FROM scoped
          GROUP BY player
        )
        """

    def metric_value(key, population, source):
        if key not in money_fields:
            return f"{source}.{key}_{population}"
        numerator = f"{source}.{key}_raw_{population}"
        denominator = " + ".join(
            f"{source}.{money_key}_raw_{population}"
            for money_key in money_fields
        )
        return f"100 * SAFE_DIVIDE({numerator}, {denominator})"

    def tooltip_value(key, population, source):
        return (
            f"{source}.{key}_raw_{population}"
            if key in money_fields
            else "CAST(NULL AS FLOAT64)"
        )

    metric_structs = []
    for (
        key,
        sort_order,
        label,
        tooltip,
        is_default,
        value_format,
        lower_is_better,
    ) in metric_definitions:
        fields = [
            f"{sort_order} AS sort_order",
            f"{_sql_string(label)} AS metric",
            f"{_sql_string(tooltip) if tooltip else 'CAST(NULL AS STRING)'} AS tooltip",
            f"{'TRUE' if is_default else 'FALSE'} AS is_default",
            f"{_sql_string(value_format)} AS format",
            f"{'TRUE' if lower_is_better else 'FALSE'} AS lower_is_better",
            f"{metric_value(key, 'player', 's')} AS player",
            "s.count_player AS count_player",
            f"{tooltip_value(key, 'player', 's')} AS tooltip_player",
            "s.account_counts AS account_counts",
        ]
        for population in baseline_conditions:
            fields.extend(
                [
                    f"{metric_value(key, population, 'b')} AS {population}",
                    f"b.count_{population} AS count_{population}",
                    f"{tooltip_value(key, population, 'b')} "
                    f"AS tooltip_{population}",
                ]
            )
        metric_structs.append(
            "STRUCT(" + ", ".join(fields) + ")"
        )

    return f"""
    WITH scoped AS (
      SELECT f.*
      FROM `{source_table}` f
      WHERE {where_sql}
        AND {_completed_game_sql("f")}
        {identity_predicate}
    ),
    {account_cte},
    baseline_agg AS (
      {baseline_agg}
    ),
    selected_agg AS (
      {selected_agg}
    )
    SELECT metric_row.*
    FROM baseline_agg b
    CROSS JOIN selected_agg s
    CROSS JOIN UNNEST([
      {', '.join(metric_structs)}
    ]) AS metric_row
    ORDER BY metric_row.sort_order
    """


def _build_players_comparison_query(
    where_sql, source_table=PREPARED_PLAYERS_TABLE
):
    metric_definitions = _players_metric_definitions()
    money_fields = _players_money_fields()
    metric_config_sql = ",\n        ".join(
        "STRUCT("
        f"{_sql_string(key)} AS metric_key, {sort_order} AS sort_order, "
        f"{_sql_string(label)} AS metric, "
        f"{_sql_string(tooltip) if tooltip else 'CAST(NULL AS STRING)'} AS tooltip, "
        f"{'TRUE' if is_default else 'FALSE'} AS is_default, "
        f"{_sql_string(value_format)} AS format, "
        f"{'TRUE' if lower_is_better else 'FALSE'} AS lower_is_better"
        ")"
        for key, sort_order, label, tooltip, is_default, value_format, lower_is_better in metric_definitions
    )
    metric_keys_sql = ", ".join(item[0] for item in metric_definitions)
    ordinary_keys = [key for key, *_ in metric_definitions if key not in money_fields]
    ordinary_selects = ",\n        ".join(
        f"AVG({key}) AS {key}" for key in ordinary_keys
    )
    money_selects = ",\n        ".join(
        f"AVG({key}_raw) AS {key}_raw" for key in money_fields
    )
    use_recent = source_table == PREPARED_PLAYERS_RECENT_TABLE
    source_from_sql = f"`{source_table}` f"
    recent_parent_predicate = (
        "AND f.identity_bucket IN UNNEST(@players_identity_buckets)"
        if use_recent else ""
    )
    return f"""
    WITH ranked AS (
      SELECT f.*,
        ROW_NUMBER() OVER (
          PARTITION BY f.player_identity
          ORDER BY f.game_ended_at DESC, CAST(f.table_id AS STRING) DESC
        ) AS player_rank
      FROM {source_from_sql}
      WHERE {where_sql}
        AND {_completed_game_sql("f")}
        AND f.player_identity IN UNNEST(@players_identities)
        {recent_parent_predicate}
    ),
    scoped AS (
      SELECT *
      FROM ranked
      WHERE @last_x_games = 0 OR player_rank <= @last_x_games
    ),
    per_account_base AS (
      SELECT player_identity, player, COUNT(*) AS game_count
      FROM scoped
      GROUP BY player_identity, player
    ),
    account_summaries AS (
      SELECT
        player_identity,
        ARRAY_AGG(
          STRUCT(player AS name, game_count AS game_count)
          ORDER BY player
        ) AS account_counts
      FROM per_account_base
      GROUP BY player_identity
    ),
    per_player_base AS (
      SELECT
        player_identity,
        COUNT(*) AS game_count,
        {ordinary_selects},
        {money_selects}
      FROM scoped
      GROUP BY player_identity
    ),
    per_player AS (
      SELECT
        base.*,
        summaries.account_counts,
        100 * SAFE_DIVIDE(money_spent_animals_pct_raw,
          money_spent_animals_pct_raw + money_spent_build_pct_raw + money_spent_donations_pct_raw + money_spent_range_pct_raw
        ) AS money_spent_animals_pct,
        100 * SAFE_DIVIDE(money_spent_build_pct_raw,
          money_spent_animals_pct_raw + money_spent_build_pct_raw + money_spent_donations_pct_raw + money_spent_range_pct_raw
        ) AS money_spent_build_pct,
        100 * SAFE_DIVIDE(money_spent_donations_pct_raw,
          money_spent_animals_pct_raw + money_spent_build_pct_raw + money_spent_donations_pct_raw + money_spent_range_pct_raw
        ) AS money_spent_donations_pct,
        100 * SAFE_DIVIDE(money_spent_range_pct_raw,
          money_spent_animals_pct_raw + money_spent_build_pct_raw + money_spent_donations_pct_raw + money_spent_range_pct_raw
        ) AS money_spent_range_pct
      FROM per_player_base base
      JOIN account_summaries summaries USING(player_identity)
    ),
    metric_rows AS (
      SELECT
        player_identity,
        game_count,
        account_counts,
        metric_key,
        value,
        CASE metric_key
          WHEN 'money_spent_animals_pct' THEN money_spent_animals_pct_raw
          WHEN 'money_spent_build_pct' THEN money_spent_build_pct_raw
          WHEN 'money_spent_donations_pct' THEN money_spent_donations_pct_raw
          WHEN 'money_spent_range_pct' THEN money_spent_range_pct_raw
          ELSE NULL
        END AS tooltip_value
      FROM per_player
      UNPIVOT INCLUDE NULLS (value FOR metric_key IN ({metric_keys_sql}))
    ),
    metric_config AS (
      SELECT * FROM UNNEST([{metric_config_sql}])
    )
    SELECT
      c.sort_order,
      c.metric,
      c.tooltip,
      c.is_default,
      c.format,
      c.lower_is_better,
      ARRAY_AGG(STRUCT(
        r.player_identity AS player_identity,
        r.value AS value,
        r.tooltip_value AS tooltip_value,
        r.game_count AS game_count,
        r.account_counts AS account_counts
      ) ORDER BY r.player_identity) AS player_values
    FROM metric_rows r
    JOIN metric_config c USING(metric_key)
    GROUP BY c.sort_order, c.metric, c.tooltip, c.is_default, c.format, c.lower_is_better
    ORDER BY c.sort_order
    """


def _build_players_comparison_rollup_query(where_sql):
    """Build Comparison from identity/account daily moments without Last X."""
    metric_definitions = _players_metric_definitions()
    money_fields = _players_money_fields()
    ordinary_keys = [
        key for key, *_ in metric_definitions if key not in money_fields
    ]
    metric_config_sql = ",\n        ".join(
        "STRUCT("
        f"{_sql_string(key)} AS metric_key, {sort_order} AS sort_order, "
        f"{_sql_string(label)} AS metric, "
        f"{_sql_string(tooltip) if tooltip else 'CAST(NULL AS STRING)'} AS tooltip, "
        f"{'TRUE' if is_default else 'FALSE'} AS is_default, "
        f"{_sql_string(value_format)} AS format, "
        f"{'TRUE' if lower_is_better else 'FALSE'} AS lower_is_better"
        ")"
        for (
            key,
            sort_order,
            label,
            tooltip,
            is_default,
            value_format,
            lower_is_better,
        ) in metric_definitions
    )
    metric_keys_sql = ", ".join(item[0] for item in metric_definitions)
    ordinary_selects = ",\n        ".join(
        f"SAFE_DIVIDE(SUM({key}_sum), SUM({key}_count)) AS {key}"
        for key in ordinary_keys
    )
    money_selects = ",\n        ".join(
        f"SAFE_DIVIDE(SUM({key}_raw_sum), SUM({key}_raw_count)) "
        f"AS {key}_raw"
        for key in money_fields
    )
    return f"""
    WITH scoped AS (
      SELECT f.*
      FROM `{PREPARED_PLAYERS_IDENTITY_ROLLUP_TABLE}` f
      WHERE {where_sql}
        AND {_completed_game_sql("f")}
        AND f.player_identity IN UNNEST(@players_identities)
    ),
    per_account_base AS (
      SELECT
        player_identity,
        player,
        SUM(observation_count) AS game_count
      FROM scoped
      GROUP BY player_identity, player
    ),
    account_summaries AS (
      SELECT
        player_identity,
        ARRAY_AGG(
          STRUCT(player AS name, game_count AS game_count)
          ORDER BY player
        ) AS account_counts
      FROM per_account_base
      GROUP BY player_identity
    ),
    per_player_base AS (
      SELECT
        player_identity,
        SUM(observation_count) AS game_count,
        {ordinary_selects},
        {money_selects}
      FROM scoped
      GROUP BY player_identity
    ),
    per_player AS (
      SELECT
        base.*,
        summaries.account_counts,
        100 * SAFE_DIVIDE(money_spent_animals_pct_raw,
          money_spent_animals_pct_raw + money_spent_build_pct_raw
          + money_spent_donations_pct_raw + money_spent_range_pct_raw
        ) AS money_spent_animals_pct,
        100 * SAFE_DIVIDE(money_spent_build_pct_raw,
          money_spent_animals_pct_raw + money_spent_build_pct_raw
          + money_spent_donations_pct_raw + money_spent_range_pct_raw
        ) AS money_spent_build_pct,
        100 * SAFE_DIVIDE(money_spent_donations_pct_raw,
          money_spent_animals_pct_raw + money_spent_build_pct_raw
          + money_spent_donations_pct_raw + money_spent_range_pct_raw
        ) AS money_spent_donations_pct,
        100 * SAFE_DIVIDE(money_spent_range_pct_raw,
          money_spent_animals_pct_raw + money_spent_build_pct_raw
          + money_spent_donations_pct_raw + money_spent_range_pct_raw
        ) AS money_spent_range_pct
      FROM per_player_base base
      JOIN account_summaries summaries USING(player_identity)
    ),
    metric_rows AS (
      SELECT
        player_identity,
        game_count,
        account_counts,
        metric_key,
        value,
        CASE metric_key
          WHEN 'money_spent_animals_pct' THEN money_spent_animals_pct_raw
          WHEN 'money_spent_build_pct' THEN money_spent_build_pct_raw
          WHEN 'money_spent_donations_pct' THEN money_spent_donations_pct_raw
          WHEN 'money_spent_range_pct' THEN money_spent_range_pct_raw
          ELSE NULL
        END AS tooltip_value
      FROM per_player
      UNPIVOT INCLUDE NULLS (value FOR metric_key IN ({metric_keys_sql}))
    ),
    metric_config AS (
      SELECT * FROM UNNEST([{metric_config_sql}])
    )
    SELECT
      c.sort_order,
      c.metric,
      c.tooltip,
      c.is_default,
      c.format,
      c.lower_is_better,
      ARRAY_AGG(STRUCT(
        r.player_identity AS player_identity,
        r.value AS value,
        r.tooltip_value AS tooltip_value,
        r.game_count AS game_count,
        r.account_counts AS account_counts
      ) ORDER BY r.player_identity) AS player_values
    FROM metric_rows r
    JOIN metric_config c USING(metric_key)
    GROUP BY
      c.sort_order, c.metric, c.tooltip, c.is_default, c.format,
      c.lower_is_better
    ORDER BY c.sort_order
    """


def _build_players_performance_by_map_query(where_sql, use_last_x=False):
    """Average Elo delta per merged identity and map.

    The daily rollup serves ordinary filters. Last X deliberately ranks exact
    player-game rows separately inside every identity/map partition before
    null Elo deltas are removed from the statistical moments.
    """
    if use_last_x:
        source = f"""
        filtered_games AS (
          SELECT
            f.player_identity,
            f.Map,
            SAFE_CAST(f.elo_delta AS FLOAT64) AS elo_delta,
            ROW_NUMBER() OVER (
              PARTITION BY f.player_identity, f.Map
              ORDER BY f.game_ended_at DESC, CAST(f.table_id AS STRING) DESC
            ) AS recent_rank
          FROM `{PREPARED_PLAYERS_RECENT_TABLE}` f
          WHERE f.identity_bucket IN UNNEST(@players_identity_buckets)
            AND f.player_identity IN UNNEST(@players_identities)
            AND {where_sql}
        ),
        moments AS (
          SELECT
            player_identity,
            Map,
            COUNT(elo_delta) AS delta_count,
            SUM(elo_delta) AS delta_sum,
            SUM(POW(elo_delta, 2)) AS delta_sum_squares
          FROM filtered_games
          WHERE recent_rank <= @last_x_games
          GROUP BY player_identity, Map
        )
        """
    else:
        source = f"""
        moments AS (
          SELECT
            f.player_identity,
            f.Map,
            SUM(f.delta_count) AS delta_count,
            SUM(f.delta_sum) AS delta_sum,
            SUM(f.delta_sum_squares) AS delta_sum_squares
          FROM `{PREPARED_PLAYERS_MAP_ROLLUP_TABLE}` f
          WHERE f.player_identity IN UNNEST(@players_identities)
            AND {where_sql}
          GROUP BY f.player_identity, f.Map
        )
        """
    pivot_fields = []
    for map_meta in ALL_MAPS_FOR_METRICS:
        key = map_meta["key"]
        full = _sql_string(map_meta["full"])
        pivot_fields.extend([
            f"MAX(IF(s.Map = {full}, ROUND(s.delta_mean, 3), NULL)) AS {key}",
            f"MAX(IF(s.Map = {full}, s.delta_mean, NULL)) AS {key}_ci_mean",
            f"MAX(IF(s.Map = {full}, s.delta_sd, NULL)) AS {key}_ci_sd",
            f"MAX(IF(s.Map = {full}, s.delta_count, 0)) AS {key}_ci_n",
        ])
    return f"""
    WITH selected_players AS (
      SELECT
        identity AS player_identity,
        @players_players[SAFE_OFFSET(position)] AS player,
        position
      FROM UNNEST(@players_identities) AS identity WITH OFFSET position
    ),
    {source},
    map_stats AS (
      SELECT
        player_identity,
        Map,
        delta_count,
        SAFE_DIVIDE(delta_sum, delta_count) AS delta_mean,
        IF(
          delta_count > 1,
          SQRT(SAFE_DIVIDE(
            GREATEST(delta_sum_squares - SAFE_DIVIDE(POW(delta_sum, 2), delta_count), 0),
            delta_count - 1
          )),
          NULL
        ) AS delta_sd
      FROM moments
    )
    SELECT
      p.position AS sort_order,
      p.player,
      {', '.join(pivot_fields)}
    FROM selected_players p
    LEFT JOIN map_stats s USING(player_identity)
    GROUP BY p.position, p.player
    ORDER BY p.position
    """


def _account_counts_payload(raw_counts):
    counts = []
    for item in raw_counts or []:
        name = item.get("name") if isinstance(item, dict) else item.name
        game_count = (
            item.get("game_count") if isinstance(item, dict) else item.game_count
        )
        counts.append({"name": str(name), "game_count": int(game_count or 0)})
    return counts


def _selected_account_summary(selected_player, account_counts, metadata=None):
    """Split one merged population into selected-account and associate counts."""
    metadata = metadata or _load_merge_players_metadata()
    members = _player_merge_members(selected_player, metadata)
    counts_by_name = {
        str(item.get("name")): int(item.get("game_count") or 0)
        for item in account_counts or []
    }
    selected_exact = next(
        (
            member
            for member in members
            if member.casefold() == str(selected_player).casefold()
        ),
        str(selected_player),
    )
    selected_count = counts_by_name.get(selected_exact, 0)
    member_counts = [
        {"name": member, "game_count": counts_by_name.get(member, 0)}
        for member in members
    ]
    total_count = sum(item["game_count"] for item in member_counts)
    return {
        "name": str(selected_player),
        "game_count": total_count,
        "selected_game_count": selected_count,
        "associated_game_count": total_count - selected_count,
        "is_merged": len(members) > 1,
    }


def _decorate_comparison_rows(
    rows, selected_players, player_identities, metadata=None
):
    """Restore requested aliases and column order after identity aggregation."""
    metadata = metadata or _load_merge_players_metadata()
    summaries = []
    first_values = rows[0].get("values", []) if rows else []
    first_by_identity = {
        item.get("player_identity"): item for item in first_values
    }
    for player, identity in zip(selected_players, player_identities):
        source = first_by_identity.get(identity, {})
        summaries.append(
            _selected_account_summary(
                player, source.get("account_counts") or [], metadata
            )
        )
    for row in rows:
        by_identity = {
            item.get("player_identity"): item
            for item in row.get("values", [])
        }
        values = []
        for player, identity, summary in zip(
            selected_players, player_identities, summaries
        ):
            source = by_identity.get(identity, {})
            values.append({
                "player": player,
                "value": source.get("value"),
                "tooltip_value": source.get("tooltip_value"),
                "game_count": summary["game_count"],
            })
        row["values"] = values
    return summaries


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
    where_sql = where_sql.replace("f.game_ended_at", "f.game_date")
    return f"""
    WITH scoped AS (
      SELECT f.*
      FROM `{PREPARED_HOME_OBSERVATIONS_TABLE}` f
      WHERE {where_sql}
    ), metrics AS (
      SELECT
        COUNT(DISTINCT table_id) AS games_indexed,
        COUNT(DISTINCT IF(has_log, table_id, NULL)) AS games_logged,
        SUM(animals_played) AS animals_played,
        SUM(sponsors_played) AS sponsors_played,
        SUM(projects_supported) AS projects_supported,
        SUM(breaks_triggered) AS breaks_triggered,
        SUM(x_tokens_gained) AS x_tokens_gained,
        SUM(emus_played) AS emus_played,
        SUM(two_cp_workers_taken) AS two_cp_workers_taken,
        SUM(empty_petting_zoos_played) AS empty_petting_zoos_played,
        SUM(free_unis_and_partner_zoos) AS free_unis_and_partner_zoos,
        SUM(bignose_project_blocks) AS bignose_project_blocks
      FROM scoped
    )
    SELECT metric, value
    FROM metrics
    CROSS JOIN UNNEST([
      STRUCT('games_indexed' AS metric, games_indexed AS value),
      ('animals_played', animals_played), ('sponsors_played', sponsors_played),
      ('projects_supported', projects_supported), ('breaks_triggered', breaks_triggered),
      ('x_tokens_gained', x_tokens_gained), ('games_logged', games_logged),
      ('emus_played', emus_played), ('two_cp_workers_taken', two_cp_workers_taken),
      ('empty_petting_zoos_played', empty_petting_zoos_played),
      ('free_unis_and_partner_zoos', free_unis_and_partner_zoos),
      ('bignose_project_blocks', bignose_project_blocks)
    ])
    """


def _build_build_enclosures_query(where_sql):
    bucket_fields = [
        ("0", "enclosure_count = 0"),
        ("1", "enclosure_count = 1"),
        ("2", "enclosure_count = 2"),
        ("3", "enclosure_count = 3"),
        ("4", "enclosure_count = 4"),
        ("5_plus", "enclosure_count >= 5"),
    ]
    aggregates = []
    for suffix, condition in bucket_fields:
        aggregates.extend([
            f"ROUND(AVG(IF({condition}, elo_delta, NULL)), 3) AS delta_{suffix}",
            f"COUNTIF({condition}) AS count_{suffix}",
            f"AVG(IF({condition}, elo_delta, NULL)) AS delta_{suffix}_ci_mean",
            f"STDDEV_SAMP(IF({condition}, elo_delta, NULL)) AS delta_{suffix}_ci_sd",
            f"COUNTIF(({condition}) AND elo_delta IS NOT NULL) AS delta_{suffix}_ci_n",
        ])
    aggregate_sql = ",\n        ".join(aggregates)
    return f"""
    WITH log_filtered AS (
      SELECT *
      FROM `{PREPARED_LOGS_TABLE}`
      WHERE {where_sql}
    ),
    observations AS (
      SELECT
        l.table_id,
        l.player,
        l.elo_delta,
        l.played_sponsors,
        f.Petting_Zoo_icons,
        enclosure,
        category,
        CASE enclosure
          WHEN '1-size' THEN SAFE_CAST(l.one_size_enclosure_built AS INT64)
          WHEN '2-size' THEN SAFE_CAST(l.two_size_enclosure_built AS INT64)
          WHEN '3-size' THEN SAFE_CAST(l.three_size_enclosure_built AS INT64)
          WHEN '4-size' THEN SAFE_CAST(l.four_size_enclosure_built AS INT64)
          WHEN '5-size' THEN SAFE_CAST(l.five_size_enclosure_built AS INT64)
          WHEN 'Aviary' THEN SAFE_CAST(l.aviary_built AS INT64)
          WHEN 'Reptile House' THEN SAFE_CAST(l.reptile_house_built AS INT64)
          WHEN 'Petting Zoo' THEN SAFE_CAST(l.petting_zoo_built AS INT64)
          WHEN 'Large Aquarium' THEN SAFE_CAST(l.large_aquarium_built AS INT64)
          WHEN 'Small Aquarium' THEN SAFE_CAST(l.small_aquarium_built AS INT64)
        END AS enclosure_count
      FROM log_filtered l
      JOIN `{PREPARED_FULL_STATS_TABLE}` f
        ON l.table_id = f.table_id AND l.player = f.player
      CROSS JOIN UNNEST([
        STRUCT('1-size' AS enclosure, 'standard' AS category),
        STRUCT('2-size', 'standard'),
        STRUCT('3-size', 'standard'),
        STRUCT('4-size', 'standard'),
        STRUCT('5-size', 'standard'),
        STRUCT('Aviary', 'unique'),
        STRUCT('Reptile House', 'unique'),
        STRUCT('Petting Zoo', 'unique'),
        STRUCT('Large Aquarium', 'unique'),
        STRUCT('Small Aquarium', 'unique')
      ])
    ),
    aggregated AS (
      SELECT
        enclosure,
        category,
        COUNT(enclosure_count) AS n_total,
        {aggregate_sql},
        ROUND(AVG(IF(
          enclosure = 'Petting Zoo' AND enclosure_count = 1
            AND COALESCE(SAFE_CAST(Petting_Zoo_icons AS INT64), 0) = 0
            AND NOT EXISTS (
              SELECT 1
              FROM UNNEST(IFNULL(played_sponsors, [])) AS ps
              WHERE ps.sponsor = 'Horse Whisperer'
            ),
          elo_delta, NULL
        )), 3) AS delta_empty,
        COUNTIF(
          enclosure = 'Petting Zoo' AND enclosure_count = 1
            AND COALESCE(SAFE_CAST(Petting_Zoo_icons AS INT64), 0) = 0
            AND NOT EXISTS (
              SELECT 1
              FROM UNNEST(IFNULL(played_sponsors, [])) AS ps
              WHERE ps.sponsor = 'Horse Whisperer'
            )
        ) AS count_empty,
        COUNTIF(enclosure = 'Petting Zoo' AND enclosure_count = 1) AS empty_denominator,
        AVG(IF(
          enclosure = 'Petting Zoo' AND enclosure_count = 1
            AND COALESCE(SAFE_CAST(Petting_Zoo_icons AS INT64), 0) = 0
            AND NOT EXISTS (
              SELECT 1
              FROM UNNEST(IFNULL(played_sponsors, [])) AS ps
              WHERE ps.sponsor = 'Horse Whisperer'
            ),
          elo_delta, NULL
        )) AS delta_empty_ci_mean,
        STDDEV_SAMP(IF(
          enclosure = 'Petting Zoo' AND enclosure_count = 1
            AND COALESCE(SAFE_CAST(Petting_Zoo_icons AS INT64), 0) = 0
            AND NOT EXISTS (
              SELECT 1
              FROM UNNEST(IFNULL(played_sponsors, [])) AS ps
              WHERE ps.sponsor = 'Horse Whisperer'
            ),
          elo_delta, NULL
        )) AS delta_empty_ci_sd,
        COUNTIF(
          enclosure = 'Petting Zoo' AND enclosure_count = 1
            AND COALESCE(SAFE_CAST(Petting_Zoo_icons AS INT64), 0) = 0
            AND NOT EXISTS (
              SELECT 1
              FROM UNNEST(IFNULL(played_sponsors, [])) AS ps
              WHERE ps.sponsor = 'Horse Whisperer'
            )
            AND elo_delta IS NOT NULL
        ) AS delta_empty_ci_n
      FROM observations
      WHERE enclosure_count IS NOT NULL
      GROUP BY enclosure, category
    )
    SELECT *
    FROM aggregated
    ORDER BY IF(category = 'standard', 0, 1),
      CASE enclosure
        WHEN '1-size' THEN 1 WHEN '2-size' THEN 2 WHEN '3-size' THEN 3
        WHEN '4-size' THEN 4 WHEN '5-size' THEN 5 WHEN 'Aviary' THEN 6
        WHEN 'Reptile House' THEN 7 WHEN 'Petting Zoo' THEN 8
        WHEN 'Large Aquarium' THEN 9 ELSE 10
      END
    """


def _build_build_hexes_query(where_sql, expanded=False):
    """Build collapsed or exact empty-hex buckets from completed games."""
    buckets = (
        [
            (str(value), str(value), f"empty_hexes = {value}")
            for value in range(24)
        ]
        + [("24_plus", "24+", "empty_hexes >= 24")]
        if expanded
        else [
            ("0", "0", "empty_hexes = 0"),
            ("1_5", "1-5", "empty_hexes BETWEEN 1 AND 5"),
            ("6_11", "6-11", "empty_hexes BETWEEN 6 AND 11"),
            ("12_17", "12-17", "empty_hexes BETWEEN 12 AND 17"),
            ("18_23", "18-23", "empty_hexes BETWEEN 18 AND 23"),
            ("24_plus", "24+", "empty_hexes >= 24"),
        ]
    )
    map_selects = []
    for map_meta in ALL_MAPS_FOR_METRICS[:15]:
        key = map_meta["key"]
        full = _sql_string(map_meta["full"])
        map_selects.extend([
            f"ROUND(AVG(IF(Map = {full} AND bucket_condition, elo_delta, NULL)), 3) AS {key}",
            f"COUNTIF(Map = {full} AND bucket_condition) AS count_{key}",
            f"COUNTIF(Map = {full} AND empty_hexes IS NOT NULL) AS denom_{key}",
            f"AVG(IF(Map = {full} AND bucket_condition, elo_delta, NULL)) AS {key}_ci_mean",
            f"STDDEV_SAMP(IF(Map = {full} AND bucket_condition, elo_delta, NULL)) AS {key}_ci_sd",
            f"COUNTIF(Map = {full} AND bucket_condition AND elo_delta IS NOT NULL) AS {key}_ci_n",
        ])
    map_select_sql = ",\n        ".join(map_selects)
    bucket_structs = ",\n        ".join(
        f"STRUCT({_sql_string(key)} AS bucket_key, {_sql_string(label)} AS bucket_label, {order} AS sort_order)"
        for order, (key, label, _) in enumerate(buckets, 1)
    )
    condition_case = "\n          ".join(
        f"WHEN b.bucket_key = {_sql_string(key)} THEN {condition}"
        for key, _, condition in buckets
    )
    return f"""
    WITH filtered AS (
      SELECT
        f.Map,
        SAFE_CAST(f.Empty_hexes AS INT64) AS empty_hexes,
        SAFE_CAST(f.elo_delta AS FLOAT64) AS elo_delta
      FROM `{PREPARED_FULL_STATS_TABLE}` f
      WHERE {where_sql}
        AND {_completed_game_sql("f")}
    ),
    bucketed AS (
      SELECT
        filtered.*,
        b.bucket_key,
        b.bucket_label,
        b.sort_order,
        CASE
          {condition_case}
          ELSE FALSE
        END AS bucket_condition
      FROM filtered
      CROSS JOIN UNNEST([
        {bucket_structs}
      ]) AS b
    )
    SELECT
      bucket_key,
      bucket_label,
      sort_order,
      ROUND(AVG(IF(bucket_condition, elo_delta, NULL)), 3) AS avg,
      COUNTIF(bucket_condition) AS count_avg,
      COUNTIF(empty_hexes IS NOT NULL) AS denom_avg,
      AVG(IF(bucket_condition, elo_delta, NULL)) AS avg_ci_mean,
      STDDEV_SAMP(IF(bucket_condition, elo_delta, NULL)) AS avg_ci_sd,
      COUNTIF(bucket_condition AND elo_delta IS NOT NULL) AS avg_ci_n,
      {map_select_sql}
    FROM bucketed
    GROUP BY bucket_key, bucket_label, sort_order
    ORDER BY sort_order
    """


def _scoring_bucket_config(scoring_view, expanded=False):
    """Return source field, valid range, and fixed display buckets for Scoring."""
    if scoring_view == SCORING_VIEW_FINAL_SCORE:
        buckets = (
            [("under_100", "<100", "metric_value < 100")]
            + [(str(value), str(value), f"metric_value = {value}") for value in range(100, 150)]
            + [("150_plus", "150+", "metric_value >= 150")]
            if expanded
            else [
                ("under_100", "<100", "metric_value < 100"),
                ("100_109", "100–109", "metric_value BETWEEN 100 AND 109"),
                ("110_119", "110–119", "metric_value BETWEEN 110 AND 119"),
                ("120_129", "120–129", "metric_value BETWEEN 120 AND 129"),
                ("130_139", "130–139", "metric_value BETWEEN 130 AND 139"),
                ("140_149", "140–149", "metric_value BETWEEN 140 AND 149"),
                ("150_plus", "150+", "metric_value >= 150"),
            ]
        )
        return "Score", "metric_value IS NOT NULL", buckets
    if scoring_view == SCORING_VIEW_APPEAL:
        buckets = (
            [("under_40", "<40", "metric_value < 40")]
            + [(str(value), str(value), f"metric_value = {value}") for value in range(40, 114)]
            if expanded
            else [
                ("under_40", "<40", "metric_value < 40"),
                ("40_49", "40–49", "metric_value BETWEEN 40 AND 49"),
                ("50_59", "50–59", "metric_value BETWEEN 50 AND 59"),
                ("60_69", "60–69", "metric_value BETWEEN 60 AND 69"),
                ("70_79", "70–79", "metric_value BETWEEN 70 AND 79"),
                ("80_89", "80–89", "metric_value BETWEEN 80 AND 89"),
                ("90_99", "90–99", "metric_value BETWEEN 90 AND 99"),
                ("100_112", "100–112", "metric_value BETWEEN 100 AND 112"),
                ("113", "113", "metric_value = 113"),
            ]
        )
        return "Appeal", "metric_value BETWEEN 0 AND 113", buckets
    if scoring_view == SCORING_VIEW_CONSERVATION_POINTS:
        buckets = (
            [(str(value), str(value), f"metric_value = {value}") for value in range(42)]
            if expanded
            else [
                ("0_10", "0–10", "metric_value BETWEEN 0 AND 10"),
                ("11_15", "11–15", "metric_value BETWEEN 11 AND 15"),
                ("16_20", "16–20", "metric_value BETWEEN 16 AND 20"),
                ("21_25", "21–25", "metric_value BETWEEN 21 AND 25"),
                ("26_30", "26–30", "metric_value BETWEEN 26 AND 30"),
                ("31_35", "31–35", "metric_value BETWEEN 31 AND 35"),
                ("36_40", "36–40", "metric_value BETWEEN 36 AND 40"),
                ("41", "41", "metric_value = 41"),
            ]
        )
        return "Conservation", "metric_value BETWEEN 0 AND 41", buckets
    buckets = [(str(value), str(value), f"metric_value = {value}") for value in range(1, 16)]
    return "Reputation", "metric_value BETWEEN 1 AND 15", buckets


def _build_scoring_query(where_sql, scoring_view, expanded=False):
    """Aggregate one Scoring distribution; both modes travel in one API payload."""
    source_field, valid_condition, buckets = _scoring_bucket_config(scoring_view, expanded)
    map_selects = []
    for map_meta in ALL_MAPS_FOR_METRICS[:15]:
        key = map_meta["key"]
        full = _sql_string(map_meta["full"])
        map_selects.extend([
            f"ROUND(AVG(IF(Map = {full} AND bucket_condition, elo_delta, NULL)), 3) AS {key}",
            f"COUNTIF(Map = {full} AND bucket_condition) AS count_{key}",
            f"COUNTIF(Map = {full}) AS denom_{key}",
            f"AVG(IF(Map = {full} AND bucket_condition, elo_delta, NULL)) AS {key}_ci_mean",
            f"STDDEV_SAMP(IF(Map = {full} AND bucket_condition, elo_delta, NULL)) AS {key}_ci_sd",
            f"COUNTIF(Map = {full} AND bucket_condition AND elo_delta IS NOT NULL) AS {key}_ci_n",
        ])
    bucket_structs = ",\n        ".join(
        f"STRUCT({_sql_string(key)} AS bucket_key, {_sql_string(label)} AS bucket_label, {order} AS sort_order)"
        for order, (key, label, _) in enumerate(buckets, 1)
    )
    condition_case = "\n          ".join(
        f"WHEN b.bucket_key = {_sql_string(key)} THEN {condition}"
        for key, _, condition in buckets
    )
    return f"""
    WITH filtered AS (
      SELECT
        f.Map,
        SAFE_CAST(f.{source_field} AS INT64) AS metric_value,
        SAFE_CAST(f.elo_delta AS FLOAT64) AS elo_delta
      FROM `{PREPARED_FULL_STATS_TABLE}` f
      WHERE {where_sql}
        AND {_completed_game_sql("f")}
    ),
    valid AS (
      -- Only gameplay-valid values own denominator observations. Score keeps
      -- open tails, while the three bounded tracks reject theoretical values.
      SELECT * FROM filtered WHERE {valid_condition}
    ),
    bucketed AS (
      SELECT
        valid.*,
        b.bucket_key,
        b.bucket_label,
        b.sort_order,
        CASE
          {condition_case}
          ELSE FALSE
        END AS bucket_condition
      FROM valid
      CROSS JOIN UNNEST([
        {bucket_structs}
      ]) AS b
    )
    SELECT
      bucket_key,
      bucket_label,
      sort_order,
      ROUND(AVG(IF(bucket_condition, elo_delta, NULL)), 3) AS avg,
      COUNTIF(bucket_condition) AS count_avg,
      COUNT(*) AS denom_avg,
      AVG(IF(bucket_condition, elo_delta, NULL)) AS avg_ci_mean,
      STDDEV_SAMP(IF(bucket_condition, elo_delta, NULL)) AS avg_ci_sd,
      COUNTIF(bucket_condition AND elo_delta IS NOT NULL) AS avg_ci_n,
      {', '.join(map_selects)}
    FROM bucketed
    GROUP BY bucket_key, bucket_label, sort_order
    ORDER BY sort_order
    """


PREDICTOR_GENERAL_FIELDS = [
    ("More conservation", "Conservation"),
    ("More appeal", "Appeal"),
    ("More reputation", "Reputation"),
    ("More conservation projects", "Conservation_project_association_tasks"),
    ("More release projects", "Released_animals"),
    ("More money gained", "Money_gained"),
    ("More money gained through income", "Money_gained_through_income"),
    ("More money spent on animals", "Money_spent_on_animals"),
    ("More money spent on enclosures", "Money_spent_on_enclosures"),
    ("More money spent on donations", "Money_spent_on_donations"),
    ("More money spent on playing from range", "Money_spent_for_playing_cards_from_reputation_range"),
    ("More breaks triggered", "Number_of_breaks_triggered"),
    ("More sponsors played", "Played_sponsors"),
    ("More animals played", "Played_animals"),
    ("More cards drawn", "Cards_drawn_from_deck"),
    ("More cards snapped", "Snapped_cards"),
    ("More cards discarded", "Discarded_cards"),
    ("More Animals actions", "Animals_actions"),
    ("More Association actions", "Association_actions"),
    ("More Build actions", "Build_actions"),
    ("More Cards actions", "Cards_actions"),
    ("More Sponsors actions", "Sponsors_actions"),
    ("More determinations", "determinations"),
    ("More X-backs", "X_Tokens_gained_instead_of_action"),
    ("More X-tokens gained", "X_Tokens_gained"),
    ("More X-tokens used", "X_Tokens_used"),
    ("More empty hexes", "Empty_hexes"),
    ("More pavilions built", "Built_pavilions"),
    ("More kiosks built", "Built_kiosks"),
    ("More special buildings", "Built_unique_buildings"),
]

PREDICTOR_SPECIFIC_CONDITIONS = [
    ("More endgame points", "more_endgame_points", False),
    ("More endgame CP", "more_endgame_cp", False),
    ("More ingame CP", "more_ingame_cp", False),
    ("More reefers", "more_reefers", True),
    ("More small animals", "more_small_animals", False),
    ("More medium animals", "more_medium_animals", False),
    ("More large animals", "more_large_animals", False),
    ("Round 1: Upgrade", "round_1_upgrade", False),
    ("Round 1: Project", "round_1_project", False),
    ("Round 1: Release", "round_1_release", False),
    ("Round 1: 2+ association actions", "round_1_two_association", False),
    ("Round 1: Humphead Wrasse", "round_1_humphead", True),
    ("Round 1/2: New Zealand Fur Seal", "round_1_2_fur_seal", False),
    ("First to 5 CP", "first_to_5", False),
    ("First to 5 CP (with exactly one university/partner zoo bonus)", "first_to_5_bonus", False),
    ("First to 8 CP", "first_to_8", False),
    ("First to 8 CP (with exactly one university/partner zoo bonus)", "first_to_8_bonus", False),
    ("No project in starting hand", "no_project_opening", False),
    ("No sponsor in starting hand", "no_sponsor_opening", False),
    ("No sponsor in starting hand and Sponsors at 5", "no_sponsor_sponsors_5", False),
    (
        "No sponsor in starting hand and second player and Association at 2 and Sponsors at 5",
        "no_sponsor_second_assoc_2_sponsors_5",
        False,
    ),
]


def _build_predictors_specific_query(where_sql, observations_only=False):
    metadata = _load_card_attribute_groups()
    configs = ",\n        ".join(
        (
            f"STRUCT({idx} AS sort_order, {_sql_string(label)} AS condition, "
            f"{_sql_string(key)} AS condition_key, {'TRUE' if mw_only else 'FALSE'} AS mw_only)"
        )
        for idx, (label, key, mw_only) in enumerate(PREDICTOR_SPECIFIC_CONDITIONS, 1)
    )
    reefer_sql = _sql_string_list(metadata["reefer_animals"])
    small_sql = _sql_string_list(metadata["small_animals"])
    medium_sql = _sql_string_list(metadata["medium_animals"])
    large_sql = _sql_string_list(metadata["large_animals"])
    project_sql = _sql_string_list(metadata["project_cards"])
    sponsor_sql = _sql_string_list(metadata["sponsor_cards"])
    sponsor_cp_sql = _sql_string_list(sorted(name.lower() for name in SPONSOR_CP_CARDS))
    sponsor_appeal_sql = _sql_string_list(sorted(name.lower() for name in SPONSOR_APPEAL_CARDS))
    first_to_5 = (
        "me.first_5_move IS NOT NULL AND "
        "(opp.first_5_move IS NULL OR me.first_5_move < opp.first_5_move)"
    )
    first_to_8 = (
        "me.first_8_move IS NOT NULL AND "
        "(opp.first_8_move IS NULL OR me.first_8_move < opp.first_8_move)"
    )
    final_select = (
        """
    SELECT
      is_mw, Map, game_date, table_conceded, end_game_triggered,
      arena_season, is_tournament, table_id, player, starting_position,
      pre_match_elo, opponent_pre_match_elo,
      elo_delta, sort_order, condition, mw_only, condition_met
    FROM observations
        """
        if observations_only else
        """
    SELECT
      sort_order,
      condition,
      ROUND(AVG(IF(condition_met, elo_delta, NULL)), 3) AS delta,
      COUNTIF(condition_met) AS count,
      COUNT(*) AS denominator,
      AVG(IF(condition_met, elo_delta, NULL)) AS delta_ci_mean,
      STDDEV_SAMP(IF(condition_met, elo_delta, NULL)) AS delta_ci_sd,
      COUNTIF(condition_met AND elo_delta IS NOT NULL) AS delta_ci_n
    FROM observations
    WHERE NOT mw_only OR @is_mw = 1
    GROUP BY sort_order, condition
    ORDER BY sort_order
        """
    )
    return f"""
    WITH scoped_full AS (
      SELECT f.*
      FROM `{PREPARED_FULL_STATS_TABLE}` f
      WHERE {where_sql}
        AND {_completed_game_sql("f")}
    ),
    scoped AS (
      SELECT
        f.table_id,
        f.player,
        SAFE_CAST(f.is_mw AS INT64) AS is_mw,
        f.Map,
        f.game_date,
        f.table_conceded,
        f.end_game_triggered,
        f.arena_season,
        f.is_tournament,
        SAFE_CAST(f.pre_match_elo AS FLOAT64) AS pre_match_elo,
        SAFE_CAST(f.opponent_pre_match_elo AS FLOAT64) AS opponent_pre_match_elo,
        SAFE_CAST(f.elo_delta AS FLOAT64) AS elo_delta,
        SAFE_CAST(f.Conservation AS FLOAT64) AS conservation,
        f.starting_position,
        l.played_animals,
        l.opening_cards,
        l.endgame_scores,
        l.endgame_from_sponsors,
        l.association_action_history,
        l.cp_history,
        COALESCE(l.has_round_1_upgrade, FALSE) AS has_round_1_upgrade,
        COALESCE(l.has_round_1_release, FALSE) AS has_round_1_release,
        l.chosen_5cp_bonus,
        l.chosen_8cp_bonus,
        SAFE_CAST(l.association_starting_strength AS INT64) AS association_starting_strength,
        SAFE_CAST(l.sponsors_starting_strength AS INT64) AS sponsors_starting_strength
      FROM scoped_full f
      JOIN `{PREPARED_LOGS_TABLE}` l
        ON f.table_id = l.table_id
       AND f.player = l.player
    ),
    sponsor_per_card AS (
      SELECT
        s.table_id,
        s.player,
        LOWER(TRIM(event.sponsor)) AS sponsor,
        MAX(COALESCE(SAFE_CAST(event.cp AS FLOAT64), 0)) AS cp,
        MAX(COALESCE(SAFE_CAST(event.appeal AS FLOAT64), 0)) AS appeal
      FROM scoped s
      CROSS JOIN UNNEST(IFNULL(s.endgame_from_sponsors, [])) AS event
      GROUP BY s.table_id, s.player, sponsor
    ),
    sponsor_totals AS (
      SELECT
        table_id,
        player,
        SUM(IF(sponsor IN ({sponsor_cp_sql}), cp, 0)) AS sponsor_cp,
        SUM(IF(sponsor IN ({sponsor_appeal_sql}), appeal, 0)) AS sponsor_appeal
      FROM sponsor_per_card
      GROUP BY table_id, player
    ),
    endgame_card_totals AS (
      SELECT
        s.table_id,
        s.player,
        SUM(COALESCE(SAFE_CAST(score.cp AS FLOAT64), 0)) AS endgame_card_cp
      FROM scoped s
      CROSS JOIN UNNEST(IFNULL(s.endgame_scores, [])) AS score
      GROUP BY s.table_id, s.player
    ),
    player_values AS (
      SELECT
        s.*,
        COALESCE(st.sponsor_cp, 0) AS sponsor_cp,
        COALESCE(st.sponsor_appeal, 0) AS sponsor_appeal,
        COALESCE(et.endgame_card_cp, 0) AS endgame_card_cp,
        COALESCE(st.sponsor_cp, 0) + COALESCE(et.endgame_card_cp, 0) AS endgame_cp,
        3 * (COALESCE(st.sponsor_cp, 0) + COALESCE(et.endgame_card_cp, 0))
          + COALESCE(st.sponsor_appeal, 0) AS endgame_points,
        s.conservation - COALESCE(st.sponsor_cp, 0) - COALESCE(et.endgame_card_cp, 0) AS ingame_cp,
        (SELECT COUNTIF(LOWER(TRIM(animal.animal)) IN ({reefer_sql}))
          FROM UNNEST(IFNULL(s.played_animals, [])) AS animal) AS reefer_count,
        (SELECT COUNTIF(LOWER(TRIM(animal.animal)) IN ({small_sql}))
          FROM UNNEST(IFNULL(s.played_animals, [])) AS animal) AS small_animal_count,
        (SELECT COUNTIF(LOWER(TRIM(animal.animal)) IN ({medium_sql}))
          FROM UNNEST(IFNULL(s.played_animals, [])) AS animal) AS medium_animal_count,
        (SELECT COUNTIF(LOWER(TRIM(animal.animal)) IN ({large_sql}))
          FROM UNNEST(IFNULL(s.played_animals, [])) AS animal) AS large_animal_count,
        EXISTS(
          SELECT 1 FROM UNNEST(IFNULL(s.association_action_history, [])) AS action
          WHERE SAFE_CAST(action.round AS INT64) = 1 AND action.project IS NOT NULL
        ) AS round_1_project,
        (SELECT COUNT(*) FROM UNNEST(IFNULL(s.association_action_history, [])) AS action
          WHERE SAFE_CAST(action.round AS INT64) = 1) >= 2 AS round_1_two_association,
        EXISTS(
          SELECT 1 FROM UNNEST(IFNULL(s.played_animals, [])) AS animal
          WHERE LOWER(TRIM(animal.animal)) = 'humphead wrasse'
            AND SAFE_CAST(animal.round AS INT64) = 1
        ) AS round_1_humphead,
        EXISTS(
          SELECT 1 FROM UNNEST(IFNULL(s.played_animals, [])) AS animal
          WHERE LOWER(TRIM(animal.animal)) = 'new zealand fur seal'
            AND SAFE_CAST(animal.round AS INT64) IN (1, 2)
        ) AS round_1_2_fur_seal,
        (SELECT MIN(SAFE_CAST(history.move AS INT64))
          FROM UNNEST(IFNULL(s.cp_history, [])) AS history
          WHERE SAFE_CAST(history.cp AS INT64) >= 5) AS first_5_move,
        (SELECT MIN(SAFE_CAST(history.move AS INT64))
          FROM UNNEST(IFNULL(s.cp_history, [])) AS history
          WHERE SAFE_CAST(history.cp AS INT64) >= 8) AS first_8_move,
        (SELECT COUNTIF(LOWER(TRIM(card)) IN ({project_sql}))
          FROM UNNEST(IFNULL(s.opening_cards, [])) AS card) = 0 AS no_project_opening,
        (SELECT COUNTIF(LOWER(TRIM(card)) IN ({sponsor_sql}))
          FROM UNNEST(IFNULL(s.opening_cards, [])) AS card) = 0 AS no_sponsor_opening
      FROM scoped s
      LEFT JOIN sponsor_totals st USING(table_id, player)
      LEFT JOIN endgame_card_totals et USING(table_id, player)
    ),
    configured AS (
      SELECT *
      FROM UNNEST([
        {configs}
      ])
    ),
    observations AS (
      SELECT
        config.sort_order,
        config.condition,
        config.mw_only,
        me.is_mw,
        me.Map,
        me.game_date,
        me.table_conceded,
        me.end_game_triggered,
        me.arena_season,
        me.is_tournament,
        me.table_id,
        me.player,
        me.starting_position,
        me.pre_match_elo,
        me.opponent_pre_match_elo,
        me.elo_delta,
        CASE config.condition_key
          WHEN 'more_endgame_points' THEN me.endgame_points > opp.endgame_points
          WHEN 'more_endgame_cp' THEN me.endgame_cp > opp.endgame_cp
          WHEN 'more_ingame_cp' THEN me.ingame_cp > opp.ingame_cp
          WHEN 'more_reefers' THEN me.reefer_count > opp.reefer_count
          WHEN 'more_small_animals' THEN me.small_animal_count > opp.small_animal_count
          WHEN 'more_medium_animals' THEN me.medium_animal_count > opp.medium_animal_count
          WHEN 'more_large_animals' THEN me.large_animal_count > opp.large_animal_count
          WHEN 'round_1_upgrade' THEN me.has_round_1_upgrade
          WHEN 'round_1_project' THEN me.round_1_project
          WHEN 'round_1_release' THEN me.has_round_1_release
          WHEN 'round_1_two_association' THEN me.round_1_two_association
          WHEN 'round_1_humphead' THEN me.round_1_humphead
          WHEN 'round_1_2_fur_seal' THEN me.round_1_2_fur_seal
          WHEN 'first_to_5' THEN {first_to_5}
          WHEN 'first_to_5_bonus' THEN ({first_to_5})
            AND LOWER(TRIM(COALESCE(me.chosen_5cp_bonus, ''))) IN ('1 university', '1 partner-zoo')
            AND LOWER(TRIM(COALESCE(opp.chosen_5cp_bonus, ''))) NOT IN ('1 university', '1 partner-zoo')
          WHEN 'first_to_8' THEN {first_to_8}
          WHEN 'first_to_8_bonus' THEN ({first_to_8})
            AND LOWER(TRIM(COALESCE(me.chosen_8cp_bonus, ''))) IN ('1 university', '1 partner-zoo')
            AND LOWER(TRIM(COALESCE(opp.chosen_8cp_bonus, ''))) NOT IN ('1 university', '1 partner-zoo')
          WHEN 'no_project_opening' THEN me.no_project_opening
          WHEN 'no_sponsor_opening' THEN me.no_sponsor_opening
          WHEN 'no_sponsor_sponsors_5' THEN
            me.no_sponsor_opening AND me.sponsors_starting_strength = 5
          WHEN 'no_sponsor_second_assoc_2_sponsors_5' THEN
            me.no_sponsor_opening
            AND me.starting_position = 'Second player'
            AND me.association_starting_strength = 2
            AND me.sponsors_starting_strength = 5
          ELSE FALSE
        END AS condition_met
      FROM player_values me
      JOIN player_values opp
        ON me.table_id = opp.table_id
       AND me.player != opp.player
      CROSS JOIN configured config
    )
    {final_select}
    """


def _build_predictors_query(where_sql, predictors_view, starting_positions=None):
    if predictors_view == PREDICTORS_VIEW_SPECIFIC:
        where_sql = where_sql.replace("f.game_ended_at", "f.game_date")
        return f"""
        SELECT
          sort_order,
          ANY_VALUE(condition) AS condition,
          ROUND(AVG(IF(condition_met, elo_delta, NULL)), 3) AS delta,
          COUNTIF(condition_met) AS count,
          COUNT(*) AS denominator,
          AVG(IF(condition_met, elo_delta, NULL)) AS delta_ci_mean,
          STDDEV_SAMP(IF(condition_met, elo_delta, NULL)) AS delta_ci_sd,
          COUNTIF(condition_met AND elo_delta IS NOT NULL) AS delta_ci_n
        FROM `{PREPARED_PREDICTOR_SPECIFIC_TABLE}` AS f
        WHERE {where_sql}
          AND (NOT mw_only OR @is_mw = 1)
        GROUP BY sort_order
        ORDER BY sort_order
        """
    # General/Icon compare the focal row with its opponent. Applying FPA inside
    # the shared `scoped` CTE would require both rows to have the same starting
    # position and empty every valid two-player table. Keep the opponent row in
    # scope and orient the restriction on `me` after the self-join instead.
    focal_position_sql = ""
    if starting_positions:
        where_sql = where_sql.replace(
            "f.starting_position IN UNNEST(@starting_positions)",
            "TRUE",
        )
        focal_position_sql = (
            "WHERE me.starting_position IN UNNEST(@starting_positions)"
        )
    fields = ICON_FIELDS if predictors_view == PREDICTORS_VIEW_ICON else PREDICTOR_GENERAL_FIELDS
    condition_structs = ",\n        ".join(
        f"STRUCT({idx} AS sort_order, {_sql_string(label)} AS condition, {_sql_string(field)} AS field_name)"
        for idx, (label, field) in enumerate(fields, 1)
    )
    return f"""
    WITH scoped AS (
      SELECT f.*
      FROM `{PREPARED_FULL_STATS_TABLE}` f
      WHERE {where_sql}
        AND {_completed_game_sql("f")}
    ),
    paired AS (
      SELECT
        me.table_id,
        me.player,
        me.elo_delta,
        config.sort_order,
        config.condition,
        CASE config.field_name
          {" ".join(f"WHEN {_sql_string(field)} THEN SAFE_CAST(me.{field} AS FLOAT64) > SAFE_CAST(opp.{field} AS FLOAT64)" for _, field in fields)}
          ELSE FALSE
        END AS condition_met
      FROM scoped me
      JOIN scoped opp
        ON me.table_id = opp.table_id
       AND me.player != opp.player
      CROSS JOIN UNNEST([
        {condition_structs}
      ]) AS config
      {focal_position_sql}
    )
    SELECT
      sort_order,
      condition,
      ROUND(AVG(IF(condition_met, elo_delta, NULL)), 3) AS delta,
      COUNTIF(condition_met) AS count,
      AVG(IF(condition_met, elo_delta, NULL)) AS delta_ci_mean,
      STDDEV_SAMP(IF(condition_met, elo_delta, NULL)) AS delta_ci_sd,
      COUNTIF(condition_met AND elo_delta IS NOT NULL) AS delta_ci_n
    FROM paired
    GROUP BY sort_order, condition
    ORDER BY sort_order
    """


def _build_actions_starting_position_query(where_sql):
    return f"""
    WITH observations AS (
      SELECT *
      FROM `{PREPARED_ACTION_STARTING_TABLE}`
      WHERE {where_sql}
    ),
    strength AS (
      SELECT
        section, sort_order, label,
        ROUND(AVG(IF(bucket = 2, elo_delta, NULL)), 3) AS delta_2,
        COUNTIF(bucket = 2) AS count_2,
        AVG(IF(bucket = 2, elo_delta, NULL)) AS delta_2_ci_mean,
        STDDEV_SAMP(IF(bucket = 2, elo_delta, NULL)) AS delta_2_ci_sd,
        COUNTIF(bucket = 2 AND elo_delta IS NOT NULL) AS delta_2_ci_n,
        ROUND(AVG(IF(bucket = 3, elo_delta, NULL)), 3) AS delta_3,
        COUNTIF(bucket = 3) AS count_3,
        AVG(IF(bucket = 3, elo_delta, NULL)) AS delta_3_ci_mean,
        STDDEV_SAMP(IF(bucket = 3, elo_delta, NULL)) AS delta_3_ci_sd,
        COUNTIF(bucket = 3 AND elo_delta IS NOT NULL) AS delta_3_ci_n,
        ROUND(AVG(IF(bucket = 4, elo_delta, NULL)), 3) AS delta_4,
        COUNTIF(bucket = 4) AS count_4,
        AVG(IF(bucket = 4, elo_delta, NULL)) AS delta_4_ci_mean,
        STDDEV_SAMP(IF(bucket = 4, elo_delta, NULL)) AS delta_4_ci_sd,
        COUNTIF(bucket = 4 AND elo_delta IS NOT NULL) AS delta_4_ci_n,
        ROUND(AVG(IF(bucket = 5, elo_delta, NULL)), 3) AS delta_5,
        COUNTIF(bucket = 5) AS count_5,
        AVG(IF(bucket = 5, elo_delta, NULL)) AS delta_5_ci_mean,
        STDDEV_SAMP(IF(bucket = 5, elo_delta, NULL)) AS delta_5_ci_sd,
        COUNTIF(bucket = 5 AND elo_delta IS NOT NULL) AS delta_5_ci_n
      FROM observations
      WHERE section = 'strength'
      GROUP BY section, sort_order, label
    ),
    comparison AS (
      SELECT
        'comparison' AS section,
        sort_order,
        label,
        ROUND(AVG(IF(condition_met, elo_delta, NULL)), 3) AS delta,
        COUNTIF(condition_met) AS count,
        AVG(IF(condition_met, elo_delta, NULL)) AS delta_ci_mean,
        STDDEV_SAMP(IF(condition_met, elo_delta, NULL)) AS delta_ci_sd,
        COUNTIF(condition_met AND elo_delta IS NOT NULL) AS delta_ci_n
      FROM observations
      WHERE section = 'comparison'
      GROUP BY sort_order, label
    )
    SELECT * FROM strength
    UNION ALL
    SELECT
      section, sort_order, label,
      delta AS delta_2, count AS count_2, delta_ci_mean AS delta_2_ci_mean,
      delta_ci_sd AS delta_2_ci_sd, delta_ci_n AS delta_2_ci_n,
      NULL AS delta_3, NULL AS count_3, NULL AS delta_3_ci_mean, NULL AS delta_3_ci_sd, NULL AS delta_3_ci_n,
      NULL AS delta_4, NULL AS count_4, NULL AS delta_4_ci_mean, NULL AS delta_4_ci_sd, NULL AS delta_4_ci_n,
      NULL AS delta_5, NULL AS count_5, NULL AS delta_5_ci_mean, NULL AS delta_5_ci_sd, NULL AS delta_5_ci_n
    FROM comparison
    ORDER BY section DESC, sort_order
    """


def _build_actions_upgrades_query(where_sql):
    return f"""
    WITH scoped AS (
      SELECT f.*
      FROM `{PREPARED_FULL_STATS_TABLE}` f
      WHERE {where_sql}
        AND {_completed_game_sql("f")}
    ),
    number_rows AS (
      SELECT
        'number' AS section,
        SAFE_CAST(count_value AS INT64) + 1 AS sort_order,
        CAST(count_value AS STRING) AS label,
        ROUND(AVG(IF(SAFE_CAST(Upgraded_action_cards AS INT64) = count_value, elo_delta, NULL)), 3) AS delta,
        COUNTIF(SAFE_CAST(Upgraded_action_cards AS INT64) = count_value) AS count,
        COUNT(Upgraded_action_cards) AS denominator,
        AVG(IF(SAFE_CAST(Upgraded_action_cards AS INT64) = count_value, elo_delta, NULL)) AS delta_ci_mean,
        STDDEV_SAMP(IF(SAFE_CAST(Upgraded_action_cards AS INT64) = count_value, elo_delta, NULL)) AS delta_ci_sd,
        COUNTIF(SAFE_CAST(Upgraded_action_cards AS INT64) = count_value AND elo_delta IS NOT NULL) AS delta_ci_n
      FROM scoped
      CROSS JOIN UNNEST([0, 1, 2, 3, 4, 5]) AS count_value
      GROUP BY count_value
    ),
    upgrade_config AS (
      SELECT * FROM UNNEST([
        STRUCT(1 AS sort_order, 'Animals' AS label, 'Upgraded_Animals_action_card' AS field_name),
        STRUCT(2, 'Association', 'Upgraded_Association_action_card'),
        STRUCT(3, 'Build', 'Upgraded_Build_action_card'),
        STRUCT(4, 'Cards', 'Upgraded_Cards_action_card'),
        STRUCT(5, 'Sponsors', 'Upgraded_Sponsors_action_card')
      ])
    ),
    upgrade_rows AS (
      SELECT
        'upgrade' AS section,
        c.sort_order,
        c.label,
        ROUND(AVG(IF(
          CASE c.field_name
            WHEN 'Upgraded_Animals_action_card' THEN COALESCE(Upgraded_Animals_action_card, FALSE)
            WHEN 'Upgraded_Association_action_card' THEN COALESCE(Upgraded_Association_action_card, FALSE)
            WHEN 'Upgraded_Build_action_card' THEN COALESCE(Upgraded_Build_action_card, FALSE)
            WHEN 'Upgraded_Cards_action_card' THEN COALESCE(Upgraded_Cards_action_card, FALSE)
            WHEN 'Upgraded_Sponsors_action_card' THEN COALESCE(Upgraded_Sponsors_action_card, FALSE)
            ELSE FALSE
          END, elo_delta, NULL
        )), 3) AS delta,
        COUNTIF(
          CASE c.field_name
            WHEN 'Upgraded_Animals_action_card' THEN COALESCE(Upgraded_Animals_action_card, FALSE)
            WHEN 'Upgraded_Association_action_card' THEN COALESCE(Upgraded_Association_action_card, FALSE)
            WHEN 'Upgraded_Build_action_card' THEN COALESCE(Upgraded_Build_action_card, FALSE)
            WHEN 'Upgraded_Cards_action_card' THEN COALESCE(Upgraded_Cards_action_card, FALSE)
            WHEN 'Upgraded_Sponsors_action_card' THEN COALESCE(Upgraded_Sponsors_action_card, FALSE)
            ELSE FALSE
          END
        ) AS count,
        COUNT(*) AS denominator,
        AVG(IF(
          CASE c.field_name
            WHEN 'Upgraded_Animals_action_card' THEN COALESCE(Upgraded_Animals_action_card, FALSE)
            WHEN 'Upgraded_Association_action_card' THEN COALESCE(Upgraded_Association_action_card, FALSE)
            WHEN 'Upgraded_Build_action_card' THEN COALESCE(Upgraded_Build_action_card, FALSE)
            WHEN 'Upgraded_Cards_action_card' THEN COALESCE(Upgraded_Cards_action_card, FALSE)
            WHEN 'Upgraded_Sponsors_action_card' THEN COALESCE(Upgraded_Sponsors_action_card, FALSE)
            ELSE FALSE
          END, elo_delta, NULL
        )) AS delta_ci_mean,
        STDDEV_SAMP(IF(
          CASE c.field_name
            WHEN 'Upgraded_Animals_action_card' THEN COALESCE(Upgraded_Animals_action_card, FALSE)
            WHEN 'Upgraded_Association_action_card' THEN COALESCE(Upgraded_Association_action_card, FALSE)
            WHEN 'Upgraded_Build_action_card' THEN COALESCE(Upgraded_Build_action_card, FALSE)
            WHEN 'Upgraded_Cards_action_card' THEN COALESCE(Upgraded_Cards_action_card, FALSE)
            WHEN 'Upgraded_Sponsors_action_card' THEN COALESCE(Upgraded_Sponsors_action_card, FALSE)
            ELSE FALSE
          END, elo_delta, NULL
        )) AS delta_ci_sd,
        COUNTIF(
          CASE c.field_name
            WHEN 'Upgraded_Animals_action_card' THEN COALESCE(Upgraded_Animals_action_card, FALSE)
            WHEN 'Upgraded_Association_action_card' THEN COALESCE(Upgraded_Association_action_card, FALSE)
            WHEN 'Upgraded_Build_action_card' THEN COALESCE(Upgraded_Build_action_card, FALSE)
            WHEN 'Upgraded_Cards_action_card' THEN COALESCE(Upgraded_Cards_action_card, FALSE)
            WHEN 'Upgraded_Sponsors_action_card' THEN COALESCE(Upgraded_Sponsors_action_card, FALSE)
            ELSE FALSE
          END AND elo_delta IS NOT NULL
        ) AS delta_ci_n
      FROM scoped
      CROSS JOIN upgrade_config c
      GROUP BY c.sort_order, c.label
    )
    SELECT * FROM number_rows
    UNION ALL SELECT * FROM upgrade_rows
    ORDER BY section, sort_order
    """


def _build_actions_upgrade_order_query(where_sql):
    order_slots = [("1", "first_upgrade"), ("2", "second_upgrade"), ("3", "third_upgrade"), ("4", "fourth_upgrade")]
    actions = ["Animals", "Association", "Build", "Cards", "Sponsors"]
    aggregates = []
    for suffix, field in order_slots:
        aggregates.extend([
            f"ROUND(AVG(IF({field} = action_name, elo_delta, NULL)), 3) AS delta_{suffix}",
            f"COUNTIF({field} = action_name) AS count_{suffix}",
            f"AVG(IF({field} = action_name, elo_delta, NULL)) AS delta_{suffix}_ci_mean",
            f"STDDEV_SAMP(IF({field} = action_name, elo_delta, NULL)) AS delta_{suffix}_ci_sd",
            f"COUNTIF({field} = action_name AND elo_delta IS NOT NULL) AS delta_{suffix}_ci_n",
        ])
    aggregate_sql = ",\n        ".join(aggregates)
    action_structs = ",\n        ".join(
        f"STRUCT({idx} AS sort_order, {_sql_string(action)} AS action_name)"
        for idx, action in enumerate(actions, 1)
    )
    return f"""
    WITH base_logs AS (
      SELECT *
      FROM `{PREPARED_LOGS_TABLE}`
      WHERE {where_sql}
    ),
    scoped AS (
      SELECT l.*, f.table_conceded, f.end_game_triggered
      FROM base_logs l
      JOIN `{PREPARED_FULL_STATS_TABLE}` f
        ON l.table_id = f.table_id AND l.player = f.player
      WHERE {_completed_game_sql("f")}
    ),
    action_rows AS (
      SELECT *
      FROM scoped
      CROSS JOIN UNNEST([
        {action_structs}
      ])
    )
    SELECT
      sort_order,
      action_name AS label,
      COUNTIF(first_upgrade = action_name OR second_upgrade = action_name OR third_upgrade = action_name OR fourth_upgrade = action_name) AS denominator,
      {aggregate_sql}
    FROM action_rows
    GROUP BY sort_order, action_name
    ORDER BY sort_order
    """


def _build_actions_upgrades_by_map_query(where_sql):
    map_selects = []
    for map_meta in ALL_MAPS_FOR_METRICS[:15]:
        key = map_meta["key"]
        full = _sql_string(map_meta["full"])
        map_selects.extend([
            f"ROUND(AVG(IF(Map = {full} AND upgraded, elo_delta, NULL)), 3) AS {key}",
            f"COUNTIF(Map = {full} AND upgraded) AS count_{key}",
            f"COUNTIF(Map = {full}) AS denom_{key}",
            f"AVG(IF(Map = {full} AND upgraded, elo_delta, NULL)) AS {key}_ci_mean",
            f"STDDEV_SAMP(IF(Map = {full} AND upgraded, elo_delta, NULL)) AS {key}_ci_sd",
            f"COUNTIF(Map = {full} AND upgraded AND elo_delta IS NOT NULL) AS {key}_ci_n",
        ])
    map_select_sql = ",\n        ".join(map_selects)
    return f"""
    WITH scoped AS (
      SELECT f.*
      FROM `{PREPARED_FULL_STATS_TABLE}` f
      WHERE {where_sql}
        AND {_completed_game_sql("f")}
    ),
    observations AS (
      SELECT 1 AS sort_order, 'Animals' AS label, Map, elo_delta, COALESCE(Upgraded_Animals_action_card, FALSE) AS upgraded FROM scoped
      UNION ALL SELECT 2, 'Association', Map, elo_delta, COALESCE(Upgraded_Association_action_card, FALSE) FROM scoped
      UNION ALL SELECT 3, 'Build', Map, elo_delta, COALESCE(Upgraded_Build_action_card, FALSE) FROM scoped
      UNION ALL SELECT 4, 'Cards', Map, elo_delta, COALESCE(Upgraded_Cards_action_card, FALSE) FROM scoped
      UNION ALL SELECT 5, 'Sponsors', Map, elo_delta, COALESCE(Upgraded_Sponsors_action_card, FALSE) FROM scoped
    )
    SELECT
      sort_order,
      label,
      ROUND(AVG(IF(upgraded, elo_delta, NULL)), 3) AS avg,
      COUNTIF(upgraded) AS count_avg,
      COUNT(*) AS denom_avg,
      AVG(IF(upgraded, elo_delta, NULL)) AS avg_ci_mean,
      STDDEV_SAMP(IF(upgraded, elo_delta, NULL)) AS avg_ci_sd,
      COUNTIF(upgraded AND elo_delta IS NOT NULL) AS avg_ci_n,
      {map_select_sql}
    FROM observations
    GROUP BY sort_order, label
    ORDER BY sort_order
    """


def _build_actions_query(where_sql, actions_view):
    if actions_view == ACTIONS_VIEW_UPGRADES:
        return _build_actions_upgrades_query(where_sql)
    if actions_view == ACTIONS_VIEW_UPGRADE_ORDER:
        return _build_actions_upgrade_order_query(where_sql)
    if actions_view == ACTIONS_VIEW_UPGRADES_BY_MAP:
        return _build_actions_upgrades_by_map_query(where_sql)
    return _build_actions_starting_position_query(where_sql)


def _build_workers_query(where_sql, workers_view):
    """Return fixed-order worker rows using the Actions map-grid schema.

    General reads Full Sample's Association_workers and is always restricted to
    completed tables. The 2 CP Worker choice is stored in Logs; its optional
    completion predicate is supplied through where_sql, while null choices are
    excluded so incomplete early logs cannot become a false Upgrade/Worker row.
    """
    if workers_view == WORKERS_VIEW_GENERAL:
        source_table = PREPARED_FULL_STATS_TABLE
        source_alias = "f"
        valid_sql = (
            "SAFE_CAST(f.Association_workers AS INT64) IN (1, 2, 3, 4) "
            f"AND {_completed_game_sql('f')}"
        )
        bucket_expr = "SAFE_CAST(f.Association_workers AS INT64)"
        config_sql = ",\n        ".join(
            f"STRUCT({value} AS sort_order, {value} AS bucket, CAST({value} AS STRING) AS label)"
            for value in range(1, 5)
        )
    else:
        source_table = PREPARED_LOGS_TABLE
        source_alias = "l"
        valid_sql = "l.two_cp_worker IS TRUE OR l.two_cp_worker IS FALSE"
        bucket_expr = "IF(l.two_cp_worker, 2, 1)"
        config_sql = (
            "STRUCT(1 AS sort_order, 1 AS bucket, 'Upgrade' AS label),\n        "
            "STRUCT(2 AS sort_order, 2 AS bucket, 'Worker' AS label)"
        )

    def moments(condition):
        n = f"SUM(IF({condition}, s.delta_count, 0))"
        total = f"SUM(IF({condition}, s.delta_sum, 0))"
        squares = f"SUM(IF({condition}, s.delta_sum_squares, 0))"
        mean = f"SAFE_DIVIDE({total}, {n})"
        sd = (
            "SQRT(GREATEST(0, SAFE_DIVIDE("
            f"{squares} - SAFE_DIVIDE(POW({total}, 2), {n}), {n} - 1)))"
        )
        return mean, sd, n

    worker_average_selects = []
    if workers_view == WORKERS_VIEW_GENERAL:
        worker_average_selects.append(
            "SAFE_DIVIDE(SUM(s.worker_sum), SUM(s.observation_count)) AS worker_avg_avg"
        )
        worker_average_selects.extend(
            "SAFE_DIVIDE("
            f"SUM(IF(s.Map = {_sql_string(map_meta['full'])}, s.worker_sum, 0)), "
            f"SUM(IF(s.Map = {_sql_string(map_meta['full'])}, s.observation_count, 0))) "
            f"AS worker_avg_{map_meta['key']}"
            for map_meta in ALL_MAPS_FOR_METRICS[:15]
        )

    map_selects = []
    for map_meta in ALL_MAPS_FOR_METRICS[:15]:
        key = map_meta["key"]
        full = _sql_string(map_meta["full"])
        condition = f"s.Map = {full} AND s.bucket = c.bucket"
        mean, sd, n = moments(condition)
        map_selects.extend([
            f"ROUND({mean}, 3) AS {key}",
            f"SUM(IF({condition}, s.observation_count, 0)) AS count_{key}",
            f"SUM(IF(s.Map = {full}, s.observation_count, 0)) AS denom_{key}",
            f"{mean} AS {key}_ci_mean",
            f"{sd} AS {key}_ci_sd",
            f"{n} AS {key}_ci_n",
        ])

    avg_condition = "s.bucket = c.bucket"
    avg_mean, avg_sd, avg_n = moments(avg_condition)

    return f"""
    WITH scoped AS (
        SELECT
        {source_alias}.Map,
        {bucket_expr} AS bucket,
        COUNT(*) AS observation_count,
        COUNT({source_alias}.elo_delta) AS delta_count,
        SUM(SAFE_CAST({source_alias}.elo_delta AS FLOAT64)) AS delta_sum,
        SUM(POW(SAFE_CAST({source_alias}.elo_delta AS FLOAT64), 2)) AS delta_sum_squares
        {', SUM(SAFE_CAST(f.Association_workers AS FLOAT64)) AS worker_sum' if workers_view == WORKERS_VIEW_GENERAL else ', CAST(NULL AS FLOAT64) AS worker_sum'}
      FROM `{source_table}` {source_alias}
      WHERE {where_sql}
        AND ({valid_sql})
      GROUP BY {source_alias}.Map, bucket
    ),
    config AS (
      SELECT * FROM UNNEST([
        {config_sql}
      ])
    )
    SELECT
      c.sort_order,
      c.label,
      ROUND({avg_mean}, 3) AS avg,
      SUM(IF({avg_condition}, s.observation_count, 0)) AS count_avg,
      SUM(s.observation_count) AS denom_avg,
      {avg_mean} AS avg_ci_mean,
      {avg_sd} AS avg_ci_sd,
      {avg_n} AS avg_ci_n,
      {', '.join(worker_average_selects) if worker_average_selects else 'CAST(NULL AS FLOAT64) AS worker_avg_avg'},
      {", ".join(map_selects)}
    FROM config c
    LEFT JOIN scoped s ON TRUE
    GROUP BY c.sort_order, c.label
    ORDER BY c.sort_order
    """


def _project_reward_config_sql():
    return ",\n        ".join(
        "STRUCT("
        f"{sort_order} AS sort_order, {_sql_string(label)} AS label, "
        f"{_sql_string(raw_value)} AS raw_value, "
        f"{_sql_string(map_name) if map_name else 'CAST(NULL AS STRING)'} AS map_name, "
        f"{_sql_string(group_name)} AS group_name)"
        for sort_order, label, raw_value, map_name, group_name in PROJECT_REWARD_CONFIG
    )


def _cp_reward_config_sql():
    return ",\n        ".join(
        "STRUCT("
        f"{sort_order} AS sort_order, {_sql_string(label)} AS label, "
        f"{_sql_string(raw_value)} AS raw_value, {str(mw_only).upper()} AS mw_only)"
        for sort_order, label, raw_value, mw_only in CP_REWARD_CONFIG
    )


def _build_conservation_projects_query(where_sql):
    where_sql = where_sql.replace("f.game_ended_at", "f.game_date")

    def moments(condition):
        n = f"SUM(IF({condition}, delta_count, 0))"
        total = f"SUM(IF({condition}, delta_sum, 0))"
        squares = f"SUM(IF({condition}, delta_sum_squares, 0))"
        mean = f"SAFE_DIVIDE({total}, {n})"
        sd = (
            "SQRT(GREATEST(0, SAFE_DIVIDE("
            f"{squares} - SAFE_DIVIDE(POW({total}, 2), {n}), {n} - 1)))"
        )
        return mean, sd, n

    map_selects = []
    for map_meta in ALL_MAPS_FOR_METRICS[:15]:
        key = map_meta["key"]
        full = _sql_string(map_meta["full"])
        condition = f"Map = {full} AND subject_count = count_value"
        mean, sd, n = moments(condition)
        map_selects.extend([
            f"ROUND({mean}, 3) AS {key}",
            f"SUM(IF({condition}, observation_count, 0)) AS count_{key}",
            f"SUM(IF(Map = {full}, observation_count, 0)) AS denom_{key}",
            f"{mean} AS {key}_ci_mean",
            f"{sd} AS {key}_ci_sd",
            f"{n} AS {key}_ci_n",
        ])
    map_select_sql = ",\n      ".join(map_selects)
    avg_condition = "s.subject_count = c.count_value"
    avg_mean, avg_sd, avg_n = moments(avg_condition)
    return f"""
    WITH configured AS (
      SELECT subject, count_value, count_value + 1 AS sort_order
      FROM UNNEST(['projects', 'releases']) AS subject
      CROSS JOIN UNNEST(GENERATE_ARRAY(0, 7)) AS count_value
    ),
    scoped AS (
      SELECT
        Map,
        subject,
        subject_count,
        COUNT(*) AS observation_count,
        COUNT(elo_delta) AS delta_count,
        SUM(SAFE_CAST(elo_delta AS FLOAT64)) AS delta_sum,
        SUM(POW(SAFE_CAST(elo_delta AS FLOAT64), 2)) AS delta_sum_squares
      FROM `{PREPARED_CONSERVATION_COUNTS_TABLE}` AS f
      WHERE {where_sql}
      GROUP BY Map, subject, subject_count
    )
    SELECT
      c.sort_order,
      c.subject,
      c.count_value,
      ROUND({avg_mean}, 3) AS avg,
      SUM(IF({avg_condition}, s.observation_count, 0)) AS count_avg,
      SUM(s.observation_count) AS denom_avg,
      {avg_mean} AS avg_ci_mean,
      {avg_sd} AS avg_ci_sd,
      {avg_n} AS avg_ci_n,
      {map_select_sql}
    FROM configured c
    LEFT JOIN scoped s ON s.subject = c.subject
    GROUP BY c.sort_order, c.subject, c.count_value
    ORDER BY c.subject, c.sort_order
    """


def _build_conservation_project_rewards_query(where_sql):
    delta_fields = []
    for key, condition in [("overall", "TRUE")] + [
        (f"order_{order}", f"reward_order = {order}") for order in range(1, 8)
    ]:
        delta_fields.extend([
            f"ROUND(AVG(IF({condition}, elo_delta, NULL)), 3) AS delta_{key}",
            f"COUNTIF({condition}) AS count_delta_{key}",
            f"AVG(IF({condition}, elo_delta, NULL)) AS delta_{key}_ci_mean",
            f"STDDEV_SAMP(IF({condition}, elo_delta, NULL)) AS delta_{key}_ci_sd",
            f"COUNTIF(({condition}) AND elo_delta IS NOT NULL) AS delta_{key}_ci_n",
        ])
    completed_event = _completed_game_sql()
    frequency_fields = [
        f"COUNT(DISTINCT IF({completed_event}, "
        "CONCAT(CAST(table_id AS STRING), '\\x1f', player), NULL)) "
        "AS freq_overall_numer",
    ]
    for order in range(1, 8):
        frequency_fields.extend([
            f"COUNTIF(({completed_event}) AND reward_order = {order}) AS freq_order_{order}_numer",
            f"COUNTIF({completed_event}) AS freq_order_{order}_denom",
        ])
    config_sql = _project_reward_config_sql()
    delta_select_sql = ",\n        ".join(delta_fields)
    frequency_select_sql = ",\n        ".join(frequency_fields)
    return f"""
    WITH configured AS (
      SELECT * FROM UNNEST([
        {config_sql}
      ])
    ),
    scoped AS (
      SELECT *
      FROM `{PREPARED_PROJECT_REWARD_TABLE}`
      WHERE {where_sql}
    ),
    reward_events AS (
      SELECT
        s.table_id,
        s.player,
        s.Map,
        s.table_conceded,
        s.end_game_triggered,
        s.elo_delta,
        raw_value,
        reward_order
      FROM scoped s
      WHERE event_kind = 'reward'
      GROUP BY
        s.table_id, s.player, s.Map, s.table_conceded,
        s.end_game_triggered, s.elo_delta, raw_value, reward_order
    ),
    matched_events AS (
      SELECT c.sort_order, e.*
      FROM configured c
      JOIN reward_events e ON e.raw_value = LOWER(c.raw_value)
        AND (c.map_name IS NULL OR e.Map = c.map_name)
    ),
    event_aggregates AS (
      SELECT
        sort_order,
        {delta_select_sql},
        {frequency_select_sql}
      FROM matched_events
      GROUP BY sort_order
    ),
    game_denominators AS (
      SELECT
        c.sort_order,
        COUNTIF(({_completed_game_sql("s")})
          AND (c.map_name IS NULL OR s.Map = c.map_name)) AS freq_overall_denom,
        COUNTIF(
          (c.map_name IS NULL OR s.Map = c.map_name)
          AND NOT (c.raw_value = '2-size' AND s.Map = 'Map 13: Drawing Board')
          AND NOT (c.raw_value = 'Snapping' AND s.Map = 'Map T1: Tournament 1')
        ) > 0 AS available
      FROM configured c
      LEFT JOIN scoped s ON s.event_kind = 'base'
      GROUP BY c.sort_order
    )
    SELECT
      c.sort_order,
      c.label,
      c.group_name,
      c.map_name AS applicable_map,
      COALESCE(g.available, FALSE) AS available,
      e.* EXCEPT(sort_order),
      g.freq_overall_denom
    FROM configured c
    LEFT JOIN event_aggregates e USING(sort_order)
    LEFT JOIN game_denominators g USING(sort_order)
    ORDER BY c.sort_order
    """


def _build_conservation_cp_rewards_query(where_sql):
    config_sql = _cp_reward_config_sql()
    delta_selects = []
    frequency_selects = []
    for key, map_name in [("overall", None)] + [
        (item["key"], item["full"]) for item in ALL_MAPS_FOR_METRICS[:15]
    ]:
        map_condition = "TRUE" if map_name is None else f"Map = {_sql_string(map_name)}"
        observed_condition = f"table_id IS NOT NULL AND ({map_condition})"
        delta_selects.extend([
            f"ROUND(AVG(IF({observed_condition}, elo_delta, NULL)), 3) AS delta_{key}",
            f"COUNTIF({observed_condition}) AS count_delta_{key}",
            f"AVG(IF({observed_condition}, elo_delta, NULL)) AS delta_{key}_ci_mean",
            f"STDDEV_SAMP(IF({observed_condition}, elo_delta, NULL)) AS delta_{key}_ci_sd",
            f"COUNTIF(({observed_condition}) AND elo_delta IS NOT NULL) AS delta_{key}_ci_n",
        ])
        frequency_selects.extend([
            f"COUNTIF(({observed_condition}) AND chosen) AS freq_{key}_numer",
            f"COUNTIF({observed_condition}) AS freq_{key}_denom",
        ])
    delta_select_sql = ", ".join(delta_selects)
    frequency_select_sql = ", ".join(frequency_selects)
    return f"""
    WITH configured AS (
      SELECT * FROM UNNEST([
        {config_sql}
      ])
      WHERE @is_mw = 1 OR NOT mw_only
    ),
    scopes AS (SELECT scope FROM UNNEST(['5', '8', 'combined']) scope),
    chosen_scoped AS (
      SELECT * FROM `{PREPARED_CP_REWARD_TABLE}`
      WHERE {where_sql} AND event_kind = 'chosen'
    ),
    opportunity_scoped AS (
      SELECT * FROM `{PREPARED_CP_REWARD_TABLE}`
      WHERE {where_sql} AND event_kind = 'opportunity'
    ),
    delta_aggregates AS (
      SELECT c.sort_order, s.scope, {delta_select_sql}
      FROM configured c
      CROSS JOIN scopes s
      LEFT JOIN chosen_scoped d
        ON d.scope = s.scope AND d.raw_value = LOWER(c.raw_value)
      GROUP BY c.sort_order, s.scope
    ),
    frequency_aggregates AS (
      SELECT c.sort_order, s.scope, {frequency_select_sql}
      FROM configured c
      CROSS JOIN scopes s
      LEFT JOIN opportunity_scoped o
        ON o.scope = s.scope AND o.raw_value = LOWER(c.raw_value)
      GROUP BY c.sort_order, s.scope
    )
    SELECT c.sort_order, c.label, c.mw_only, s.scope,
      d.* EXCEPT(sort_order, scope), f.* EXCEPT(sort_order, scope)
    FROM configured c
    CROSS JOIN scopes s
    LEFT JOIN delta_aggregates d USING(sort_order, scope)
    LEFT JOIN frequency_aggregates f USING(sort_order, scope)
    ORDER BY s.scope, c.sort_order
    """

    return f"""
    WITH configured AS (
      SELECT * FROM UNNEST([
        {config_sql}
      ])
      WHERE @is_mw = 1 OR NOT mw_only
    ),
    scoped AS (
      SELECT *
      FROM `{PREPARED_LOGS_TABLE}`
      WHERE {where_sql}
    ),
    paired AS (
      SELECT
        me.*,
        (SELECT MIN(SAFE_CAST(h.move AS INT64)) FROM UNNEST(IFNULL(me.cp_history, [])) h WHERE SAFE_CAST(h.cp AS INT64) >= 5) AS my_5_move,
        (SELECT MIN(SAFE_CAST(h.move AS INT64)) FROM UNNEST(IFNULL(opp.cp_history, [])) h WHERE SAFE_CAST(h.cp AS INT64) >= 5) AS opp_5_move,
        (SELECT MIN(SAFE_CAST(h.move AS INT64)) FROM UNNEST(IFNULL(me.cp_history, [])) h WHERE SAFE_CAST(h.cp AS INT64) >= 8) AS my_8_move,
        (SELECT MIN(SAFE_CAST(h.move AS INT64)) FROM UNNEST(IFNULL(opp.cp_history, [])) h WHERE SAFE_CAST(h.cp AS INT64) >= 8) AS opp_8_move
      FROM scoped me
      LEFT JOIN scoped opp ON me.table_id = opp.table_id AND me.player != opp.player
    ),
    chosen_base AS (
      SELECT table_id, player, Map, elo_delta, 5 AS threshold, LOWER(TRIM(chosen_5cp_bonus)) AS raw_value
      FROM paired WHERE chosen_5cp_bonus IS NOT NULL
      UNION ALL
      SELECT table_id, player, Map, elo_delta, 8, LOWER(TRIM(chosen_8cp_bonus))
      FROM paired WHERE chosen_8cp_bonus IS NOT NULL
    ),
    chosen_scoped AS (
      SELECT CAST(threshold AS STRING) AS scope, * EXCEPT(threshold) FROM chosen_base
      UNION ALL
      SELECT 'combined' AS scope, table_id, player, Map, ANY_VALUE(elo_delta), raw_value
      FROM chosen_base
      GROUP BY table_id, player, Map, raw_value
    ),
    opportunity_raw AS (
      SELECT
        p.table_id, p.player, p.Map, 5 AS threshold,
        LOWER(TRIM(available_reward)) AS raw_value,
        LOWER(TRIM(p.chosen_5cp_bonus)) = LOWER(TRIM(available_reward)) AS chosen
      FROM paired p
      CROSS JOIN UNNEST(IFNULL(p.five_cp_bonus, [])) AS available_reward
      WHERE p.my_5_move IS NOT NULL AND (p.opp_5_move IS NULL OR p.my_5_move < p.opp_5_move)
      UNION ALL
      SELECT
        p.table_id, p.player, p.Map, 8,
        LOWER(TRIM(available_reward)),
        LOWER(TRIM(p.chosen_8cp_bonus)) = LOWER(TRIM(available_reward))
      FROM paired p
      CROSS JOIN UNNEST(IFNULL(p.eight_cp_bonus, [])) AS available_reward
      WHERE p.my_8_move IS NOT NULL AND (p.opp_8_move IS NULL OR p.my_8_move < p.opp_8_move)
      UNION ALL
      -- Five money is the fixed third option and is not present in the arrays
      -- that store the two random alternatives.
      SELECT
        p.table_id, p.player, p.Map, 5, '5 money',
        LOWER(TRIM(p.chosen_5cp_bonus)) = '5 money'
      FROM paired p
      WHERE p.my_5_move IS NOT NULL AND (p.opp_5_move IS NULL OR p.my_5_move < p.opp_5_move)
      UNION ALL
      SELECT
        p.table_id, p.player, p.Map, 8, '5 money',
        LOWER(TRIM(p.chosen_8cp_bonus)) = '5 money'
      FROM paired p
      WHERE p.my_8_move IS NOT NULL AND (p.opp_8_move IS NULL OR p.my_8_move < p.opp_8_move)
    ),
    opportunity_base AS (
      SELECT table_id, player, Map, threshold, raw_value, LOGICAL_OR(chosen) AS chosen
      FROM opportunity_raw
      GROUP BY table_id, player, Map, threshold, raw_value
    ),
    opportunity_scoped AS (
      SELECT CAST(threshold AS STRING) AS scope, * EXCEPT(threshold) FROM opportunity_base
      UNION ALL
      -- Keep threshold opportunities separate in combined mode. In particular,
      -- always-offered 5 money can contribute one denominator observation at
      -- each threshold in the same player-game.
      SELECT 'combined' AS scope, * EXCEPT(threshold) FROM opportunity_base
    ),
    scopes AS (SELECT scope FROM UNNEST(['5', '8', 'combined']) AS scope),
    delta_aggregates AS (
      SELECT c.sort_order, s.scope, {delta_select_sql}
      FROM configured c
      CROSS JOIN scopes s
      LEFT JOIN chosen_scoped d ON d.scope = s.scope AND d.raw_value = LOWER(c.raw_value)
      GROUP BY c.sort_order, s.scope
    ),
    frequency_aggregates AS (
      SELECT c.sort_order, s.scope, {frequency_select_sql}
      FROM configured c
      CROSS JOIN scopes s
      LEFT JOIN opportunity_scoped o ON o.scope = s.scope AND o.raw_value = LOWER(c.raw_value)
      GROUP BY c.sort_order, s.scope
    )
    SELECT c.sort_order, c.label, c.mw_only, s.scope,
      d.* EXCEPT(sort_order, scope), f.* EXCEPT(sort_order, scope)
    FROM configured c
    CROSS JOIN scopes s
    LEFT JOIN delta_aggregates d USING(sort_order, scope)
    LEFT JOIN frequency_aggregates f USING(sort_order, scope)
    ORDER BY s.scope, c.sort_order
    """


def _build_conservation_query(where_sql, conservation_view):
    if conservation_view == CONSERVATION_VIEW_PROJECT_REWARDS:
        return _build_conservation_project_rewards_query(where_sql)
    if conservation_view == CONSERVATION_VIEW_CP_REWARDS:
        return _build_conservation_cp_rewards_query(where_sql)
    return _build_conservation_projects_query(where_sql)


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


ICON_FIELDS = [
    ("Birds", "Bird_icons"),
    ("Herbivores", "Herbivore_icons"),
    ("Predators", "Predator_icons"),
    ("Primates", "Primate_icons"),
    ("Reptiles", "Reptile_icons"),
    ("Sea Animals", "Sea_Animal_icons"),
    ("Bears", "Bear_icons"),
    ("Petting Zoo Animals", "Petting_Zoo_icons"),
    ("Africa", "Africa_icons"),
    ("Americas", "Americas_icons"),
    ("Asia", "Asia_icons"),
    ("Australia", "Australia_icons"),
    ("Europe", "Europe_icons"),
    ("Rock", "Rock_icons"),
    ("Water", "Water_icons"),
    ("Science", "Science_icons"),
]


RECORD_ICON_FIELDS = [item for item in ICON_FIELDS if item[0] not in {"Bears", "Petting Zoo Animals"}]


def _build_records_query(where_sql, records_view, records_player=None,
                         records_arena_only=False, records_tournament_only=False):
    """Return the record rows from the read-only prepared Full Sample.

    Records are deliberately hard-filtered to completed tables. Arena status is
    stricter than merely having a rating delta: the prepared Arena season CASE
    also enforces the configured UTC window and the MW/Base mode.
    """
    if records_view == RECORDS_VIEW_ELO_LEADERBOARD:
        raise ValueError("Elo Leaderboard is static and must be served from its snapshot")

    # Scope predicates are shared with the manually maintained derived rows.
    # Completion/winner predicates are attached only to automatic Records;
    # spreadsheet Fastest rows are explicit extrapolated exceptions. Missing
    # enrichment remains NULL in storage but follows the dashboard-wide Elo
    # range rule and is evaluated as zero by `where_sql`.
    manual_where_sql = where_sql
    scope_predicates = [where_sql]
    manual_scope_predicates = [manual_where_sql]
    if records_player:
        scope_predicates.append("CAST(f.player AS STRING) = @records_player")
        manual_scope_predicates.append("CAST(f.player AS STRING) = @records_player")
    if records_arena_only:
        arena_case = _arena_season_case_sql(_load_arena_metadata())
        scope_predicates.append(f"({arena_case}) IS NOT NULL")
        manual_scope_predicates.append(f"({arena_case}) IS NOT NULL")
    if records_tournament_only:
        tournament_predicate = (
            "CAST(f.table_id AS STRING) IN ("
            f"SELECT DISTINCT CAST(table_id AS STRING) FROM `{TOURNAMENT_TABLES_CACHE_TABLE}` "
            "WHERE table_id IS NOT NULL)"
        )
        scope_predicates.append(tournament_predicate)
        manual_scope_predicates.append(tournament_predicate)
    scope_sql = " AND ".join(scope_predicates)
    manual_scope_sql = " AND ".join(manual_scope_predicates)
    automatic_sql = " AND ".join([
        scope_sql,
        _completed_game_sql("f"),
    ])

    # Full Sample contains one player row per table.  Record eligibility and
    # result labels therefore use a table-level outcome aggregate instead of
    # relying on the sidebar-filtered row set (which may exclude the opponent).
    table_outcomes = f"""
    table_outcomes AS (
      SELECT
        CAST(table_id AS STRING) AS table_id,
        COUNT(*) AS result_row_count,
        COUNTIF(SAFE_CAST(Game_result AS INT64) = 1) AS result_one_count,
        COUNTIF(SAFE_CAST(Game_result AS INT64) = 2) AS result_two_count
      FROM `{PREPARED_FULL_STATS_TABLE}`
      GROUP BY table_id
    )
    """
    result_code = """
      CASE
        WHEN o.result_row_count = 2
          AND SAFE_CAST(f.Game_result AS INT64) = 1
          AND o.result_two_count = 1 THEN 'W'
        WHEN o.result_row_count = 2
          AND SAFE_CAST(f.Game_result AS INT64) = 1
          AND o.result_one_count = 2 THEN 'D'
        WHEN o.result_row_count = 2
          AND SAFE_CAST(f.Game_result AS INT64) = 2
          AND o.result_one_count = 1 THEN 'L'
        ELSE NULL
      END AS result_code
    """
    arena_case = _arena_season_case_sql(_load_arena_metadata())
    tournament_flag = (
        "EXISTS (SELECT 1 "
        f"FROM `{TOURNAMENT_TABLES_CACHE_TABLE}` tournament "
        "WHERE tournament.table_id IS NOT NULL "
        "AND CAST(tournament.table_id AS STRING) = CAST(f.table_id AS STRING))"
    )
    # Complete Records snapshots carry the small amount of row-level metadata
    # needed by the browser. This keeps every Records filter local and avoids a
    # BigQuery request for static, bounded record populations.
    automatic_metadata = f"""
      SAFE_CAST(f.opponent_pre_match_elo AS FLOAT64) AS opponent_pre_match_elo,
      CAST(f.starting_position AS STRING) AS starting_position,
      TRUE AS source_enriched,
      ({arena_case}) IS NOT NULL AS is_arena,
      {tournament_flag} AS is_tournament,
      CAST(NULL AS INT64) AS source_row
    """
    manual_metadata = f"""
      SAFE_CAST(f.opponent_pre_match_elo AS FLOAT64) AS opponent_pre_match_elo,
      CAST(f.starting_position AS STRING) AS starting_position,
      COALESCE(f.source_enriched, FALSE) AS source_enriched,
      ({arena_case}) IS NOT NULL AS is_arena,
      {tournament_flag} AS is_tournament,
      CAST(f.source_row AS INT64) AS source_row
    """
    common = f"""
      CAST(f.table_id AS STRING) AS table_id,
      CAST(f.player AS STRING) AS player,
      SAFE_CAST(f.Score AS FLOAT64) AS score,
      SAFE_CAST(f.Number_of_turns AS FLOAT64) AS turns,
      CAST(f.Map AS STRING) AS map_name,
      FORMAT_TIMESTAMP('%Y-%m-%d', SAFE_CAST(f.game_ended_at AS TIMESTAMP)) AS game_date,
      {result_code},
      0 AS ept,
      {automatic_metadata}
    """
    if records_view == RECORDS_VIEW_FASTEST_GAMES:
        return f"""
        WITH {table_outcomes},
        automatic_records AS (
          SELECT {common}
          FROM `{PREPARED_FULL_STATS_TABLE}` f
          JOIN table_outcomes o ON o.table_id = CAST(f.table_id AS STRING)
          WHERE {automatic_sql}
            AND o.result_row_count = 2
            AND SAFE_CAST(f.Game_result AS INT64) = 1
            AND o.result_two_count = 1
            AND SAFE_CAST(f.Number_of_turns AS INT64) <= 23
            AND NOT EXISTS (
              SELECT 1
              FROM `{PREPARED_RECORDS_MANUAL_TABLE}` manual
              WHERE manual.record_view = {_sql_string(RECORDS_VIEW_FASTEST_GAMES)}
                AND manual.table_id = CAST(f.table_id AS STRING)
                AND manual.player = CAST(f.player AS STRING)
            )
        ),
        manual_records AS (
          SELECT
            f.table_id,
            f.player,
            CAST(f.score AS FLOAT64) AS score,
            CAST(f.turns AS FLOAT64) AS turns,
            f.Map AS map_name,
            FORMAT_DATE('%Y-%m-%d', f.game_date) AS game_date,
            CAST(NULL AS STRING) AS result_code,
            CAST(f.ept AS INT64) AS ept,
            {manual_metadata}
          FROM `{PREPARED_RECORDS_MANUAL_TABLE}` f
          WHERE f.record_view = {_sql_string(RECORDS_VIEW_FASTEST_GAMES)}
            AND {manual_scope_sql}
        )
        SELECT * FROM automatic_records
        UNION ALL
        SELECT * FROM manual_records
        ORDER BY turns ASC, score DESC NULLS LAST, player ASC, table_id ASC
        """
    if records_view == RECORDS_VIEW_BIGGEST_TURNS:
        return f"""
        SELECT
          CAST(f.turns AS FLOAT64) AS turns,
          CAST(f.score AS FLOAT64) AS score,
          f.player,
          f.Map AS map_name,
          f.table_id,
          FORMAT_DATE('%Y-%m-%d', f.game_date) AS game_date,
          f.result_code,
          CAST(f.ept AS INT64) AS ept,
          CAST(f.flat AS INT64) AS flat,
          CAST(f.`end` AS INT64) AS `end`,
          CAST(f.total AS INT64) AS total,
          CAST(f.move AS INT64) AS move,
           CAST(f.actions AS INT64) AS actions,
           {manual_metadata}
        FROM `{PREPARED_RECORDS_MANUAL_TABLE}` f
        WHERE f.record_view = {_sql_string(RECORDS_VIEW_BIGGEST_TURNS)}
          AND {manual_scope_sql}
         ORDER BY f.total DESC, f.source_row ASC
        """
    if records_view == RECORDS_VIEW_HIGHEST_SCORES:
        return f"""
        WITH {table_outcomes}
        SELECT {common}
        FROM `{PREPARED_FULL_STATS_TABLE}` f
        JOIN table_outcomes o ON o.table_id = CAST(f.table_id AS STRING)
        WHERE {automatic_sql}
          AND o.result_row_count = 2
          AND SAFE_CAST(f.Game_result AS INT64) = 1
          AND o.result_two_count = 1
          AND SAFE_CAST(f.Score AS INT64) >= 170
          AND SAFE_CAST(f.Number_of_turns AS INT64) <= 100
        ORDER BY score DESC, turns ASC NULLS LAST, player ASC, table_id ASC
        """

    icon_selects = []
    for display_name, field_name in RECORD_ICON_FIELDS:
        icon_selects.append(f"""
          SELECT
            SAFE_CAST(f.{field_name} AS INT64) AS n,
            {_sql_string(display_name)} AS icon,
            CAST(f.player AS STRING) AS player,
            SAFE_CAST(f.Number_of_turns AS FLOAT64) AS turns,
            SAFE_CAST(f.Score AS FLOAT64) AS score,
            CAST(f.Map AS STRING) AS map_name,
            CAST(f.table_id AS STRING) AS table_id,
             FORMAT_TIMESTAMP('%Y-%m-%d', SAFE_CAST(f.game_ended_at AS TIMESTAMP)) AS game_date,
             {result_code},
             {automatic_metadata}
          FROM `{PREPARED_FULL_STATS_TABLE}` f
          JOIN table_outcomes o ON o.table_id = CAST(f.table_id AS STRING)
          WHERE {automatic_sql}
            AND SAFE_CAST(f.{field_name} AS INT64) >= 10
        """)
    return f"""
    WITH {table_outcomes}, icon_records AS (
      %s
    )
    SELECT n, icon, player, turns, score, map_name, table_id, game_date,
           result_code, 0 AS ept, opponent_pre_match_elo, starting_position,
           source_enriched, is_arena,
           is_tournament, source_row
    FROM icon_records
    ORDER BY n DESC, turns ASC NULLS LAST, player ASC, table_id ASC
    """ % "\nUNION ALL\n".join(icon_selects)


def _build_icons_query(where_sql):
    observation_selects = "\n      UNION ALL\n      ".join(
        (
            f"SELECT '{display_name}' AS icon, "
            f"SAFE_CAST(f.{field_name} AS FLOAT64) AS amount, "
            "SAFE_CAST(f.elo_delta AS FLOAT64) AS elo_delta "
            f"FROM `{PREPARED_FULL_STATS_TABLE}` f WHERE {where_sql} "
            f"AND {_completed_game_sql('f')}"
        )
        for display_name, field_name in ICON_FIELDS
    )
    bucket_conditions = [
        (f"delta_{value}", f"amount = {value}")
        for value in range(7)
    ] + [("delta_7_plus", "amount >= 7")]
    delta_selects = ",\n      ".join(
        f"ROUND(AVG(IF({condition}, elo_delta, NULL)), 3) AS {field}"
        for field, condition in bucket_conditions
    )
    count_selects = ",\n      ".join(
        f"COUNTIF({condition}) AS {field.replace('delta_', 'count_')}"
        for field, condition in bucket_conditions
    )
    ci_selects = ",\n      ".join(
        (
            f"AVG(IF({condition}, elo_delta, NULL)) AS {field}_ci_mean,\n"
            f"      STDDEV_SAMP(IF({condition}, elo_delta, NULL)) AS {field}_ci_sd,\n"
            f"      COUNTIF(({condition}) AND elo_delta IS NOT NULL) AS {field}_ci_n"
        )
        for field, condition in bucket_conditions
    )
    return f"""
    WITH observations AS (
      {observation_selects}
    )
    SELECT
      icon,
      ROUND(AVG(amount), 2) AS amount,
      COUNT(amount) AS n_total,
      {delta_selects},
      {count_selects},
      {ci_selects}
    FROM observations
    GROUP BY icon
    ORDER BY amount DESC NULLS LAST, icon
    """


def _build_sponsor_endgames_query(where_sql, sponsor_endgames_view):
    if sponsor_endgames_view == SPONSOR_ENDGAMES_VIEW_APPEAL:
        config_sql = _sponsor_appeal_config_sql()
        value_expr = "SAFE_CAST(event.appeal AS INT64)"
        avg_alias = "avg_appeal"
        bucket_conditions = [
            (f"delta_{value}", f"value = {value} AND {value} IN UNNEST(possible_values)")
            for value in range(7)
        ]
    else:
        config_sql = _sponsor_cp_config_sql()
        value_expr = "SAFE_CAST(event.cp AS INT64)"
        avg_alias = "avg_cp"
        bucket_conditions = [
            ("delta_0", "value = 0 AND 0 IN UNNEST(possible_values)"),
            ("delta_1", "value = 1 AND 1 IN UNNEST(possible_values)"),
            ("delta_2", "value = 2 AND 2 IN UNNEST(possible_values)"),
            ("delta_3_plus", "value >= 3 AND 3 IN UNNEST(possible_values)"),
        ]

    delta_selects = ",\n      ".join(
        f"ROUND(AVG(IF({condition}, elo_delta, NULL)), 3) AS {field}"
        for field, condition in bucket_conditions
    )
    count_selects = ",\n      ".join(
        f"COUNTIF({condition}) AS {field.replace('delta_', 'count_')}"
        for field, condition in bucket_conditions
    )
    ci_selects = ",\n      ".join(
        (
            f"AVG(IF({condition}, elo_delta, NULL)) AS {field}_ci_mean,\n"
            f"      STDDEV_SAMP(IF({condition}, elo_delta, NULL)) AS {field}_ci_sd,\n"
            f"      COUNTIF(({condition}) AND elo_delta IS NOT NULL) AS {field}_ci_n"
        )
        for field, condition in bucket_conditions
    )

    return f"""
    WITH configured AS (
      SELECT *
      FROM UNNEST([
        {config_sql}
      ])
    ),
    observations AS (
      SELECT
        sponsor,
        {'appeal' if sponsor_endgames_view == SPONSOR_ENDGAMES_VIEW_APPEAL else 'cp'} AS value,
        elo_delta
      FROM `{PREPARED_SPONSOR_ENDGAME_TABLE}`
      WHERE {where_sql}
    ),
    aggregated AS (
      SELECT
        c.sponsor,
        c.possible_values,
        ROUND(AVG(o.value), 2) AS {avg_alias},
        COUNT(o.sponsor) AS n_played,
        {delta_selects},
        {count_selects},
        {ci_selects}
      FROM configured c
      LEFT JOIN observations o
        ON c.sponsor = o.sponsor
      GROUP BY c.sponsor, c.possible_values
    )
    SELECT *
    FROM aggregated
    ORDER BY {avg_alias} DESC NULLS LAST, n_played DESC, sponsor
    """


def _synergy_ci_row_key(stats_page, view, row):
    """Return a stable, non-public key for one requested Synergy row."""
    if stats_page == STATS_PAGE_MW_ACTION_CARDS:
        card_1 = str(row.get("card_1_key") or "").strip()
        card_2 = str(row.get("card_2_key") or "").strip()
        if not card_1 or not card_2:
            raise ValueError("MW Synergy CI rows require card_1_key and card_2_key")
        values = [card_1, card_2]
    elif view == COMBINATIONS_VIEW_CARD_CARD:
        card_1 = str(row.get("card_1") or "").strip()
        card_2 = str(row.get("card_2") or "").strip()
        if not card_1 or not card_2:
            raise ValueError("Card + Card CI rows require card_1 and card_2")
        values = [card_1, card_2]
    elif view == COMBINATIONS_VIEW_CARD_MAP:
        card = str(row.get("card_name") or "").strip()
        context = str(row.get("map_name") or "").strip()
        if not card or context not in VALID_MAPS:
            raise ValueError("Card + Map CI rows require a valid card_name and map_name")
        values = [card, context]
    elif view == COMBINATIONS_VIEW_CARD_ROUND:
        card = str(row.get("card_name") or "").strip()
        context = str(row.get("round_name") or "").strip()
        if not card or context not in VALID_ROUNDS:
            raise ValueError("Card + Round CI rows require a valid card_name and round_name")
        values = [card, context]
    elif view == COMBINATIONS_VIEW_CARD_ENDGAME:
        card = str(row.get("card_name") or "").strip()
        context = str(row.get("endgame_name") or "").strip()
        if not card or not context:
            raise ValueError("Card + Endgame CI rows require card_name and endgame_name")
        values = [card, context]
    elif view == COMBINATIONS_VIEW_CARD_ACTION_CARD:
        card = str(row.get("card_name") or "").strip()
        action_card = str(row.get("action_card_key") or "").strip()
        if not card or not action_card:
            raise ValueError(
                "Card + Action Card CI rows require card_name and action_card_key"
            )
        values = [card, action_card]
    else:
        raise ValueError("Synergy confidence intervals are unavailable for this view")
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def _parse_synergy_ci_rows(raw_rows, stats_page, view, limit=100):
    if not isinstance(raw_rows, list):
        raise ValueError("synergy_ci_rows must be an array")
    if len(raw_rows) > limit:
        raise ValueError(f"synergy_ci_rows may contain at most {limit} rows")
    parsed = []
    seen = set()
    for raw in raw_rows:
        if not isinstance(raw, dict):
            raise ValueError("Each synergy_ci_rows item must be an object")
        item = dict(raw)
        item["row_key"] = _synergy_ci_row_key(stats_page, view, item)
        if item["row_key"] in seen:
            continue
        seen.add(item["row_key"])
        parsed.append(item)
    return parsed


def _synergy_round_predicates(selected_rounds):
    if not selected_rounds:
        return "", ""
    exact = sorted(int(value) for value in selected_rounds if value != "6+")
    play_parts = []
    pair_parts_1 = []
    pair_parts_2 = []
    if exact:
        values = ", ".join(str(value) for value in exact)
        play_parts.append(f"played_round IN ({values})")
        pair_parts_1.append(
            f"EXISTS (SELECT 1 FROM UNNEST(IFNULL(played_rounds_1, [])) r WHERE r IN ({values}))"
        )
        pair_parts_2.append(
            f"EXISTS (SELECT 1 FROM UNNEST(IFNULL(played_rounds_2, [])) r WHERE r IN ({values}))"
        )
    if "6+" in selected_rounds:
        play_parts.append("played_round >= 6")
        pair_parts_1.append(
            "EXISTS (SELECT 1 FROM UNNEST(IFNULL(played_rounds_1, [])) r WHERE r >= 6)"
        )
        pair_parts_2.append(
            "EXISTS (SELECT 1 FROM UNNEST(IFNULL(played_rounds_2, [])) r WHERE r >= 6)"
        )
    play_sql = " AND (" + " OR ".join(play_parts) + ")"
    pair_sql = (
        " AND (" + " OR ".join(pair_parts_1) + ")"
        " AND (" + " OR ".join(pair_parts_2) + ")"
    )
    return play_sql, pair_sql


def _component_ci_projection(component_aliases):
    """Render clustered 95% CI fields for the displayed standalone components."""
    fields = []
    for source, alias in component_aliases:
        source_sql = _sql_string(source)
        fields.extend([
            f"MAX(IF(cs.component = {source_sql}, cs.component_mean, NULL)) AS {alias}_mean",
            f"MAX(IF(cs.component = {source_sql} AND cs.cluster_n >= 2, cs.component_mean - 1.96 * cs.standard_error, NULL)) AS {alias}_ci95_low",
            f"MAX(IF(cs.component = {source_sql} AND cs.cluster_n >= 2, cs.component_mean + 1.96 * cs.standard_error, NULL)) AS {alias}_ci95_high",
            f"MAX(IF(cs.component = {source_sql}, cs.standard_error, NULL)) AS {alias}_ci95_se",
            f"MAX(IF(cs.component = {source_sql}, cs.total_n, 0)) AS {alias}_ci95_n",
        ])
    return ",\n      ".join(fields)


def _build_synergy_ci_query(
    where_sql,
    stats_page,
    view,
    selected_rounds=None,
    requested_rows=None,
):
    """Build a table-clustered sandwich CI query for visible Synergy rows.

    Fast aggregate tables continue to provide the table values. This separate
    query reads only the requested row keys from table-level prepared sources,
    retaining covariance between the Actual and baseline component means.
    """
    selected_rounds = selected_rounds or []
    requested_rows = requested_rows or []
    play_round_sql, pair_round_sql = _synergy_round_predicates(selected_rounds)
    action_pair_round_sql = ""
    if selected_rounds:
        exact = sorted(int(value) for value in selected_rounds if value != "6+")
        action_parts = []
        if exact:
            values = ", ".join(str(value) for value in exact)
            action_parts.append(
                "EXISTS (SELECT 1 FROM UNNEST(JSON_VALUE_ARRAY(played_rounds_json)) r "
                f"WHERE SAFE_CAST(r AS INT64) IN ({values}))"
            )
        if "6+" in selected_rounds:
            action_parts.append(
                "EXISTS (SELECT 1 FROM UNNEST(JSON_VALUE_ARRAY(played_rounds_json)) r "
                "WHERE SAFE_CAST(r AS INT64) >= 6)"
            )
        action_pair_round_sql = " AND (" + " OR ".join(action_parts) + ")"
    if (
        stats_page == STATS_PAGE_MW_ACTION_CARDS
        or view in (COMBINATIONS_VIEW_CARD_CARD, COMBINATIONS_VIEW_CARD_ACTION_CARD)
    ):
        component_aliases = [('first', 'component_1'), ('second', 'component_2')]
    elif view in (COMBINATIONS_VIEW_CARD_MAP, COMBINATIONS_VIEW_CARD_ROUND):
        component_aliases = [('general', 'component_1'), ('context', 'component_2')]
    elif view == COMBINATIONS_VIEW_CARD_ENDGAME:
        component_aliases = [('card', 'component_1'), ('endgame', 'component_2')]
    else:
        raise ValueError("Synergy confidence intervals are unavailable for this view")

    # Source pruning is expressed against the parameterized request CTE rather
    # than interpolated string literals. Besides keeping the scans compact,
    # this safely handles card and endgame names containing apostrophes.
    play_filter_sql = """
      AND card_name IN (
        SELECT card_1 FROM request_rows WHERE card_1 IS NOT NULL
        UNION DISTINCT
        SELECT card_2 FROM request_rows WHERE card_2 IS NOT NULL
        UNION DISTINCT
        SELECT card_name FROM request_rows WHERE card_name IS NOT NULL
      )
    """
    mw_filter_sql = """
      AND card_key IN (
        SELECT card_1_key FROM request_rows WHERE card_1_key IS NOT NULL
        UNION DISTINCT
        SELECT card_2_key FROM request_rows WHERE card_2_key IS NOT NULL
      )
    """
    pair_filter_sql = """
      AND EXISTS (
        SELECT 1 FROM request_rows r
        WHERE r.card_1 = card_1 AND r.card_2 = card_2
      )
    """
    card_endgame_filter_sql = """
      AND EXISTS (
        SELECT 1 FROM request_rows r
        WHERE r.card_name = card_name AND r.endgame_name = endgame_name
      )
    """
    endgame_filter_sql = """
      AND card_name IN (
        SELECT endgame_name FROM request_rows WHERE endgame_name IS NOT NULL
      )
    """
    request_cte = """
    request_rows AS (
      SELECT
        JSON_VALUE(item, '$.row_key') AS row_key,
        JSON_VALUE(item, '$.card_1') AS card_1,
        JSON_VALUE(item, '$.card_2') AS card_2,
        JSON_VALUE(item, '$.card_1_key') AS card_1_key,
        JSON_VALUE(item, '$.card_2_key') AS card_2_key,
        JSON_VALUE(item, '$.card_name') AS card_name,
        JSON_VALUE(item, '$.map_name') AS map_name,
        JSON_VALUE(item, '$.round_name') AS round_name,
        JSON_VALUE(item, '$.endgame_name') AS endgame_name
        ,JSON_VALUE(item, '$.action_card_key') AS action_card_key
      FROM UNNEST(JSON_QUERY_ARRAY(@synergy_ci_rows_json)) AS item
    )
    """

    if stats_page == STATS_PAGE_MW_ACTION_CARDS:
        source_ctes = f"""
        filtered_mw AS (
          SELECT * FROM `{PREPARED_MW_ACTION_CARD_PLAYERS_TABLE}`
          WHERE {where_sql}{mw_filter_sql}
        ),
        mw_pairs AS (
          SELECT
            table_id, player, ANY_VALUE(elo_delta) AS elo_delta,
            ARRAY_AGG(card_key ORDER BY card_order) AS cards
          FROM filtered_mw
          GROUP BY table_id, player
          HAVING COUNT(*) = 2 AND COUNT(DISTINCT card_type) = 2
        )
        """
        component_sql = """
          SELECT r.row_key, 'actual' AS component, 1.0 AS coefficient,
                 p.table_id, COUNTIF(p.elo_delta IS NOT NULL) AS n,
                 SUM(p.elo_delta) AS value_sum
          FROM request_rows r
          JOIN mw_pairs p
            ON p.cards[SAFE_OFFSET(0)] = r.card_1_key
           AND p.cards[SAFE_OFFSET(1)] = r.card_2_key
          GROUP BY r.row_key, p.table_id
          UNION ALL
          SELECT r.row_key, 'first', -1.0, p.table_id,
                 COUNTIF(p.elo_delta IS NOT NULL), SUM(p.elo_delta)
          FROM request_rows r
          JOIN filtered_mw p ON p.card_key = r.card_1_key
          GROUP BY r.row_key, p.table_id
          UNION ALL
          SELECT r.row_key, 'second', -1.0, p.table_id,
                 COUNTIF(p.elo_delta IS NOT NULL), SUM(p.elo_delta)
          FROM request_rows r
          JOIN filtered_mw p ON p.card_key = r.card_2_key
          GROUP BY r.row_key, p.table_id
        """
        expected_components = 3
    else:
        source_ctes = f"""
        filtered_plays AS (
          SELECT * FROM `{PREPARED_CARD_PLAYS_TABLE}`
          WHERE {where_sql}{play_round_sql}{play_filter_sql}
        )
        """
        if view == COMBINATIONS_VIEW_CARD_CARD:
            source_ctes += f""",
            filtered_pairs AS (
              SELECT * FROM `{PREPARED_CARD_PAIRS_TABLE}`
              WHERE {where_sql}{pair_round_sql}{pair_filter_sql}
            )
            """
            component_sql = """
              SELECT r.row_key, 'actual' AS component, 1.0 AS coefficient,
                     p.table_id, COUNTIF(p.elo_delta IS NOT NULL) AS n,
                     SUM(p.elo_delta) AS value_sum
              FROM request_rows r
              JOIN filtered_pairs p ON p.card_1 = r.card_1 AND p.card_2 = r.card_2
              GROUP BY r.row_key, p.table_id
              UNION ALL
              SELECT r.row_key, 'first', -1.0, p.table_id,
                     COUNTIF(p.elo_delta IS NOT NULL), SUM(p.elo_delta)
              FROM request_rows r JOIN filtered_plays p ON p.card_name = r.card_1
              GROUP BY r.row_key, p.table_id
              UNION ALL
              SELECT r.row_key, 'second', -1.0, p.table_id,
                     COUNTIF(p.elo_delta IS NOT NULL), SUM(p.elo_delta)
              FROM request_rows r JOIN filtered_plays p ON p.card_name = r.card_2
              GROUP BY r.row_key, p.table_id
            """
            expected_components = 3
        elif view == COMBINATIONS_VIEW_CARD_ACTION_CARD:
            source_ctes += f""",
            filtered_actions AS (
              SELECT * FROM `{PREPARED_MW_ACTION_CARD_PLAYERS_TABLE}`
              WHERE {where_sql}
                AND card_key IN (
                  SELECT action_card_key FROM request_rows
                  WHERE action_card_key IS NOT NULL
                )
            ),
            filtered_card_actions AS (
              SELECT * FROM `{PREPARED_CARD_ACTION_CARD_TABLE}`
              WHERE {where_sql}{action_pair_round_sql}
                AND EXISTS (
                  SELECT 1 FROM request_rows r
                  WHERE r.card_name = card_name
                    AND r.action_card_key = action_card_key
                )
            ),
            filtered_eligible_cards AS (
              SELECT DISTINCT table_id, player, card_name, elo_delta
              FROM `{PREPARED_CARD_ACTION_CARD_TABLE}`
              WHERE {where_sql}{action_pair_round_sql}
                AND card_name IN (
                  SELECT card_name FROM request_rows WHERE card_name IS NOT NULL
                )
            )
            """
            component_sql = """
              SELECT r.row_key, 'actual' AS component, 1.0 AS coefficient,
                     p.table_id, COUNTIF(p.elo_delta IS NOT NULL) AS n,
                     SUM(p.elo_delta) AS value_sum
              FROM request_rows r
              JOIN filtered_card_actions p
                ON p.card_name = r.card_name
               AND p.action_card_key = r.action_card_key
              GROUP BY r.row_key, p.table_id
              UNION ALL
              SELECT r.row_key, 'first', -1.0, p.table_id,
                     COUNTIF(p.elo_delta IS NOT NULL), SUM(p.elo_delta)
              FROM request_rows r
              JOIN filtered_eligible_cards p ON p.card_name = r.card_name
              GROUP BY r.row_key, p.table_id
              UNION ALL
              SELECT r.row_key, 'second', -1.0, p.table_id,
                     COUNTIF(p.elo_delta IS NOT NULL), SUM(p.elo_delta)
              FROM request_rows r
              JOIN filtered_actions p ON p.card_key = r.action_card_key
              GROUP BY r.row_key, p.table_id
            """
            expected_components = 3
        elif view == COMBINATIONS_VIEW_CARD_MAP:
            component_sql = """
              SELECT r.row_key, 'context' AS component, 1.0 AS coefficient,
                     p.table_id, COUNTIF(p.elo_delta IS NOT NULL) AS n,
                     SUM(p.elo_delta) AS value_sum
              FROM request_rows r
              JOIN filtered_plays p ON p.card_name = r.card_name AND p.Map = r.map_name
              GROUP BY r.row_key, p.table_id
              UNION ALL
              SELECT r.row_key, 'general', -1.0, p.table_id,
                     COUNTIF(p.elo_delta IS NOT NULL), SUM(p.elo_delta)
              FROM request_rows r JOIN filtered_plays p ON p.card_name = r.card_name
              GROUP BY r.row_key, p.table_id
            """
            expected_components = 2
        elif view == COMBINATIONS_VIEW_CARD_ROUND:
            component_sql = """
              SELECT r.row_key, 'context' AS component, 1.0 AS coefficient,
                     p.table_id, COUNTIF(p.elo_delta IS NOT NULL) AS n,
                     SUM(p.elo_delta) AS value_sum
              FROM request_rows r
              JOIN filtered_plays p
                ON p.card_name = r.card_name
               AND IF(p.played_round >= 6, '6+', CAST(p.played_round AS STRING)) = r.round_name
              GROUP BY r.row_key, p.table_id
              UNION ALL
              SELECT r.row_key, 'general', -1.0, p.table_id,
                     COUNTIF(p.elo_delta IS NOT NULL), SUM(p.elo_delta)
              FROM request_rows r JOIN filtered_plays p ON p.card_name = r.card_name
              GROUP BY r.row_key, p.table_id
            """
            expected_components = 2
        elif view == COMBINATIONS_VIEW_CARD_ENDGAME:
            source_ctes += f""",
            filtered_card_endgames AS (
              SELECT * FROM `{PREPARED_CARD_ENDGAME_TABLE}`
              WHERE {where_sql}{play_round_sql}{card_endgame_filter_sql}
            ),
            filtered_endgames AS (
              SELECT * FROM `{PREPARED_ENDGAME_EVENTS_TABLE}`
              WHERE {where_sql} AND event_role = 'scored'{endgame_filter_sql}
            )
            """
            component_sql = """
              SELECT r.row_key, 'actual' AS component, 1.0 AS coefficient,
                     p.table_id, COUNTIF(p.elo_delta IS NOT NULL) AS n,
                     SUM(p.elo_delta) AS value_sum
              FROM request_rows r
              JOIN filtered_card_endgames p
                ON p.card_name = r.card_name AND p.endgame_name = r.endgame_name
              GROUP BY r.row_key, p.table_id
              UNION ALL
              SELECT r.row_key, 'card', -1.0, p.table_id,
                     COUNTIF(p.elo_delta IS NOT NULL), SUM(p.elo_delta)
              FROM request_rows r JOIN filtered_plays p ON p.card_name = r.card_name
              GROUP BY r.row_key, p.table_id
              UNION ALL
              SELECT r.row_key, 'endgame', -1.0, p.table_id,
                     COUNTIF(p.elo_delta IS NOT NULL), SUM(p.elo_delta)
              FROM request_rows r
              JOIN filtered_endgames p ON p.card_name = r.endgame_name
              GROUP BY r.row_key, p.table_id
            """
            expected_components = 3
        else:
            raise ValueError("Synergy confidence intervals are unavailable for this view")

    return f"""
    WITH
    {request_cte},
    {source_ctes},
    raw_components AS (
      {component_sql}
    ),
    cluster_components AS (
      SELECT row_key, component, ANY_VALUE(coefficient) AS coefficient,
             table_id, SUM(n) AS n, SUM(value_sum) AS value_sum
      FROM raw_components
      WHERE n > 0
      GROUP BY row_key, component, table_id
    ),
    component_means AS (
      SELECT row_key, component, ANY_VALUE(coefficient) AS coefficient,
             SUM(n) AS total_n,
             SAFE_DIVIDE(SUM(value_sum), SUM(n)) AS component_mean
      FROM cluster_components
      GROUP BY row_key, component
    ),
    valid_rows AS (
      SELECT row_key,
             SUM(coefficient * component_mean) AS interaction,
             COUNT(*) AS component_count
      FROM component_means
      GROUP BY row_key
      HAVING component_count = {expected_components}
    ),
    cluster_influences AS (
      SELECT c.row_key, c.table_id,
             SUM(
               m.coefficient * (c.value_sum - c.n * m.component_mean) / m.total_n
             ) AS influence
      FROM cluster_components c
      JOIN component_means m USING(row_key, component)
      JOIN valid_rows v USING(row_key)
      GROUP BY c.row_key, c.table_id
    ),
    variance AS (
      SELECT row_key, COUNT(*) AS cluster_n,
             IF(
               COUNT(*) >= 2,
               SQRT(COUNT(*) / (COUNT(*) - 1) * SUM(POW(influence, 2))),
               CAST(NULL AS FLOAT64)
             ) AS standard_error
      FROM cluster_influences
      GROUP BY row_key
    ),
    component_stats AS (
      SELECT m.row_key, m.component, m.total_n, m.component_mean,
             COUNT(c.table_id) AS cluster_n,
             IF(
               COUNT(c.table_id) >= 2,
               SQRT(
                 COUNT(c.table_id) / (COUNT(c.table_id) - 1)
                 * SUM(POW((c.value_sum - c.n * m.component_mean) / m.total_n, 2))
               ),
               CAST(NULL AS FLOAT64)
             ) AS standard_error
      FROM component_means m
      JOIN cluster_components c USING(row_key, component)
      GROUP BY m.row_key, m.component, m.total_n, m.component_mean
    )
    SELECT
      r.row_key,
      v.interaction,
      variance.standard_error AS interaction_ci95_se,
      IF(variance.cluster_n >= 2,
         v.interaction - 1.96 * variance.standard_error, NULL) AS interaction_ci95_low,
      IF(variance.cluster_n >= 2,
         v.interaction + 1.96 * variance.standard_error, NULL) AS interaction_ci95_high,
      COALESCE(variance.cluster_n, 0) AS interaction_ci95_cluster_n,
      'table_cluster_delta' AS interaction_ci95_method,
      {_component_ci_projection(component_aliases)}
    FROM request_rows r
    LEFT JOIN valid_rows v USING(row_key)
    LEFT JOIN variance USING(row_key)
    LEFT JOIN component_stats cs USING(row_key)
    GROUP BY r.row_key, v.interaction, variance.standard_error,
             variance.cluster_n
    ORDER BY r.row_key
    """


def _synergy_ci_cache_blob_name(
    data_version,
    stats_page,
    view,
    is_mw,
    selected_maps,
    selected_rounds,
    player_elo_min,
    player_elo_max,
    opponent_elo_min,
    opponent_elo_max,
    date_from,
    date_to,
    completed_only,
    arena_only,
    tournament_only,
    starting_positions,
    rows,
):
    scope = {
        "schema": 3,
        "data_version": data_version,
        "stats_page": stats_page,
        "view": view,
        "is_mw": int(is_mw),
        "maps": sorted(selected_maps),
        "rounds": sorted(selected_rounds or []),
        "player_elo_min": player_elo_min,
        "player_elo_max": player_elo_max,
        "opponent_elo_min": opponent_elo_min,
        "opponent_elo_max": opponent_elo_max,
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "completed_only": completed_only,
        "arena_only": bool(arena_only),
        "tournament_only": bool(tournament_only),
        "starting_positions": sorted(starting_positions or []),
        "rows": sorted(item["row_key"] for item in rows),
    }
    digest = hashlib.sha256(
        json.dumps(scope, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:40]
    return f"{CACHE_PREFIX}/filters/synergy-ci/{digest}.json"


def _load_synergy_ci(
    data_version,
    stats_page,
    view,
    rows,
    is_mw,
    selected_maps,
    selected_rounds,
    player_elo_min,
    player_elo_max,
    opponent_elo_min,
    opponent_elo_max,
    date_from,
    date_to,
    completed_only,
    arena_only=False,
    tournament_only=False,
    starting_positions=None,
    force_refresh=False,
    persist_synchronously=False,
    row_limit=100,
):
    parsed_rows = _parse_synergy_ci_rows(rows, stats_page, view, limit=row_limit)
    if not parsed_rows:
        return {"status": "ok", "data": [], "source": "synergy_ci_empty"}
    blob_name = _synergy_ci_cache_blob_name(
        data_version, stats_page, view, is_mw, selected_maps, selected_rounds,
        player_elo_min, player_elo_max, opponent_elo_min, opponent_elo_max,
        date_from, date_to, completed_only, arena_only, tournament_only,
        starting_positions,
        parsed_rows,
    )
    if not force_refresh:
        cached = _read_cache_blob(blob_name, "synergy_ci_hit")
        if cached is not None:
            return cached

    where_sql, parameters = _build_where_sql(
        is_mw, selected_maps, player_elo_min, player_elo_max,
        opponent_elo_min, opponent_elo_max, date_from, date_to,
        completed_only, arena_only=arena_only, tournament_only=tournament_only,
        starting_positions=starting_positions,
    )
    query = _build_synergy_ci_query(
        where_sql, stats_page, view, selected_rounds=selected_rounds,
        requested_rows=parsed_rows,
    )
    parameters.append(bigquery.ScalarQueryParameter(
        "synergy_ci_rows_json", "STRING",
        json.dumps(parsed_rows, ensure_ascii=False, separators=(",", ":")),
    ))
    client = bigquery.Client(project=BIGQUERY_JOB_PROJECT)
    started_at = time.perf_counter()
    job = client.query(
        query,
        job_config=bigquery.QueryJobConfig(
            query_parameters=parameters,
            use_query_cache=not force_refresh,
        ),
        location=BIGQUERY_LOCATION,
    )
    result = []
    for row in job.result():
        item = dict(row.items())
        for field, value in list(item.items()):
            if field == "interaction" or field.endswith("_ci95_low") or field.endswith("_ci95_high") or field.endswith("_ci95_se"):
                item[field] = float(value) if value is not None else None
            elif field.endswith("_ci95_n") or field.endswith("_ci95_cluster_n"):
                item[field] = int(value or 0)
        result.append(item)
    payload = {
        "status": "ok",
        "stats_page": stats_page,
        "combinations_view": view if stats_page == STATS_PAGE_COMBINATIONS else None,
        "mw_action_cards_view": view if stats_page == STATS_PAGE_MW_ACTION_CARDS else None,
        "data": result,
        "source": "synergy_ci_query",
        "total_ms": _ms_since(started_at),
        "job_id": job.job_id,
    }
    # Make exact repeats instant on this instance. Interactive CI batches do
    # not wait for Cloud Storage; snapshot generation keeps the synchronous
    # write so atomic publication never references a CI payload that was not
    # durably cached.
    _memory_cache_put(blob_name, payload)
    if force_refresh or persist_synchronously:
        if not _write_cache_blob(
            blob_name, payload, "synergy_ci_refreshed", compresslevel=1
        ):
            logging.warning("Could not persist Synergy CI cache %s", blob_name)
    else:
        _enqueue_cache_blob_write(
            blob_name, payload, "synergy_ci_refreshed", compresslevel=1
        )
    return payload


def _build_combinations_query(
    where_sql,
    combinations_view,
    round_filter_active=False,
    selected_rounds=None,
    apply_interaction_filters=False,
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
    action_pair_round_sql = ""
    if apply_round_filter:
        pair_conditions_1 = []
        pair_conditions_2 = []
        if exact_rounds:
            exact_values = ", ".join(str(value) for value in exact_rounds)
            pair_conditions_1.append(
                "EXISTS (SELECT 1 FROM UNNEST(JSON_VALUE_ARRAY(played_rounds_1_json)) AS r "
                f"WHERE SAFE_CAST(r AS INT64) IN ({exact_values}))"
            )
            pair_conditions_2.append(
                "EXISTS (SELECT 1 FROM UNNEST(JSON_VALUE_ARRAY(played_rounds_2_json)) AS r "
                f"WHERE SAFE_CAST(r AS INT64) IN ({exact_values}))"
            )
        if "6+" in selected_rounds:
            pair_conditions_1.append(
                "EXISTS (SELECT 1 FROM UNNEST(JSON_VALUE_ARRAY(played_rounds_1_json)) AS r "
                "WHERE SAFE_CAST(r AS INT64) >= 6)"
            )
            pair_conditions_2.append(
                "EXISTS (SELECT 1 FROM UNNEST(JSON_VALUE_ARRAY(played_rounds_2_json)) AS r "
                "WHERE SAFE_CAST(r AS INT64) >= 6)"
            )
        pair_round_sql = (
            f" AND ({' OR '.join(pair_conditions_1)})"
            f" AND ({' OR '.join(pair_conditions_2)})"
        )
        action_pair_round_sql = (
            f" AND ({' OR '.join(pair_conditions_1)})"
        ).replace("played_rounds_1_json", "played_rounds_json")
    if combinations_view == COMBINATIONS_VIEW_CARD_CARD:
        common_ctes = f"""
        filtered AS (
          SELECT
            card_name, card_type, played_round,
            observation_count, delta_count, delta_sum
          FROM `{PREPARED_CARD_PLAY_AGGREGATES_TABLE}`
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
            SAFE_DIVIDE(SUM(delta_sum), SUM(delta_count)) AS individual_delta
          FROM played
          GROUP BY card_name
        )
        """
    else:
        common_ctes = f"""
        filtered AS (
          SELECT
            table_id, player, Map, pre_match_elo, opponent_pre_match_elo, elo_delta,
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

    if combinations_view == COMBINATIONS_VIEW_CARD_ACTION_CARD:
        return f"""
        WITH
        card_individual AS (
          SELECT card_name, ANY_VALUE(card_type) AS card_type,
                 SAFE_DIVIDE(SUM(delta_sum), SUM(delta_count)) AS individual_delta
          FROM `{PREPARED_CARD_ACTION_CARD_AGGREGATES_TABLE}`
          WHERE {where_sql}{action_pair_round_sql}
          GROUP BY card_name
        ),
        action_individual AS (
          SELECT card_key, ANY_VALUE(card_name) AS card_name,
                 ANY_VALUE(card_type) AS card_type,
                 AVG(elo_delta) AS individual_delta
          FROM `{PREPARED_MW_ACTION_CARD_PLAYERS_TABLE}`
          WHERE {where_sql}
          GROUP BY card_key
        ),
        pair_observations AS (
          SELECT *
          FROM `{PREPARED_CARD_ACTION_CARD_AGGREGATES_TABLE}`
          WHERE {where_sql}{action_pair_round_sql}
        ),
        pair_agg AS (
          SELECT
            card_name, ANY_VALUE(card_type) AS card_type,
            action_card_key, ANY_VALUE(action_card_name) AS action_card_name,
            ANY_VALUE(action_card_type) AS action_card_type,
            ANY_VALUE(action_card_number) AS action_card_number,
            SAFE_DIVIDE(SUM(delta_sum), SUM(delta_count)) AS delta_actual,
            SQRT(GREATEST(0, SAFE_DIVIDE(
              SUM(delta_sum_squares) - SAFE_DIVIDE(POW(SUM(delta_sum), 2), SUM(delta_count)),
              SUM(delta_count) - 1
            ))) AS delta_actual_ci_sd,
            SUM(delta_count) AS delta_actual_ci_n,
            SAFE_DIVIDE(SUM(elo_sum), SUM(elo_count)) AS avg_elo,
            SUM(observation_count) AS n_played
          FROM pair_observations
          GROUP BY card_name, action_card_key
        )
        SELECT
          p.card_name, p.card_type,
          ROUND(c.individual_delta, 3) AS delta_card,
          p.action_card_key, p.action_card_name, p.action_card_type, p.action_card_number,
          ROUND(a.individual_delta, 3) AS delta_action,
          ROUND(c.individual_delta + a.individual_delta, 3) AS delta_combined,
          ROUND(p.delta_actual, 3) AS delta_actual,
          p.delta_actual AS delta_actual_ci_mean,
          p.delta_actual_ci_sd, p.delta_actual_ci_n,
          ROUND(p.delta_actual - (c.individual_delta + a.individual_delta), 3) AS interaction,
          ROUND(p.avg_elo, 0) AS avg_elo,
          p.n_played,
          CONCAT(
            UPPER(SUBSTR(p.card_type, 1, 1)), SUBSTR(p.card_type, 2),
            ' + ', p.action_card_type
          ) AS pair_type
        FROM pair_agg p
        JOIN card_individual c USING(card_name)
        JOIN action_individual a ON a.card_key = p.action_card_key
        ORDER BY interaction DESC, n_played DESC, card_name, action_card_key
        """

    if combinations_view == COMBINATIONS_VIEW_CARD_ENDGAME:
        return f"""
        WITH
        {common_ctes},
        scored AS (
          SELECT DISTINCT
            table_id, player, card_name AS endgame_name, elo_delta, pre_match_elo
          FROM `{PREPARED_ENDGAME_EVENTS_TABLE}`
          WHERE {where_sql} AND event_role = 'scored'
        ),
        individual_endgames AS (
          SELECT endgame_name, AVG(elo_delta) AS endgame_delta
          FROM scored
          GROUP BY endgame_name
        ),
        pair_observations AS (
          SELECT card_name, card_type, endgame_name,
            observation_count, delta_count, delta_sum, delta_sum_squares,
            elo_count, elo_sum
          FROM `{PREPARED_CARD_ENDGAME_AGGREGATES_TABLE}`
          WHERE {where_sql}{round_sql}
        ),
        pair_agg AS (
          SELECT
            card_name,
            ANY_VALUE(card_type) AS card_type,
            endgame_name,
            SAFE_DIVIDE(SUM(delta_sum), SUM(delta_count)) AS delta_actual,
            SQRT(GREATEST(0, SAFE_DIVIDE(
              SUM(delta_sum_squares)
                - SAFE_DIVIDE(POW(SUM(delta_sum), 2), SUM(delta_count)),
              SUM(delta_count) - 1
            ))) AS delta_actual_ci_sd,
            SUM(delta_count) AS delta_actual_ci_n,
            SAFE_DIVIDE(SUM(elo_sum), SUM(elo_count)) AS avg_elo,
            SUM(observation_count) AS n_played
          FROM pair_observations
          GROUP BY card_name, endgame_name
        )
        SELECT
          p.card_name,
          p.card_type,
          ROUND(c.individual_delta, 3) AS delta_card,
          p.endgame_name,
          ROUND(e.endgame_delta, 3) AS delta_endgame,
          ROUND(c.individual_delta + e.endgame_delta, 3) AS delta_combined,
          ROUND(p.delta_actual, 3) AS delta_actual,
          p.delta_actual AS delta_actual_ci_mean,
          p.delta_actual_ci_sd,
          p.delta_actual_ci_n,
          ROUND(p.delta_actual - (c.individual_delta + e.endgame_delta), 3) AS interaction,
          ROUND(p.avg_elo, 0) AS avg_elo,
          p.n_played
        FROM pair_agg p
        JOIN individual c USING(card_name)
        JOIN individual_endgames e USING(endgame_name)
        ORDER BY interaction DESC, n_played DESC, card_name, endgame_name
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
            STDDEV_SAMP(elo_delta) AS map_delta_ci_sd,
            COUNT(elo_delta) AS map_delta_ci_n,
            AVG(pre_match_elo) AS avg_elo,
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
          p.map_delta AS delta_map_ci_mean,
          p.map_delta_ci_sd AS delta_map_ci_sd,
          p.map_delta_ci_n AS delta_map_ci_n,
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
            STDDEV_SAMP(elo_delta) AS round_delta_ci_sd,
            COUNT(elo_delta) AS round_delta_ci_n,
            AVG(pre_match_elo) AS avg_elo,
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
          p.round_delta AS delta_round_ci_mean,
          p.round_delta_ci_sd AS delta_round_ci_sd,
          p.round_delta_ci_n AS delta_round_ci_n,
          ROUND(p.round_delta - i.individual_delta, 3) AS interaction,
          ROUND(p.avg_elo, 0) AS avg_elo,
          p.n_played
        FROM per_round p
        JOIN individual i USING(card_name)
        ORDER BY interaction DESC, n_played DESC, card_name, round_name
        """

    pair_interaction_filter = ""
    if apply_interaction_filters:
        pair_interaction_filter = f"""
        AND {pair_type_sql.replace('type_a', 'type_1').replace('type_b', 'type_2')}
          IN UNNEST(@combination_pair_types)
        AND (
          (@combination_primary = '' AND @combination_secondary = '')
          OR (
            @combination_primary != '' AND @combination_secondary = ''
            AND (card_1 = @combination_primary OR card_2 = @combination_primary)
          )
          OR (
            @combination_primary = '' AND @combination_secondary != ''
            AND (card_1 = @combination_secondary OR card_2 = @combination_secondary)
          )
          OR (
            @combination_primary != '' AND @combination_secondary != ''
            AND ((card_1 = @combination_primary AND card_2 = @combination_secondary)
              OR (card_1 = @combination_secondary AND card_2 = @combination_primary))
          )
        )
        """

    pair_source_table = (
        PREPARED_CARD_PAIR_AGGREGATES_TABLE
        if round_filter_active
        else PREPARED_CARD_PAIR_SCOPE_AGGREGATES_TABLE
    )
    return f"""
    WITH
    {common_ctes},
    pair_observations AS (
      SELECT
        card_1, type_1, card_2, type_2,
        observation_count, delta_count, delta_sum, delta_sum_squares,
        elo_count, elo_sum
      FROM `{pair_source_table}`
      WHERE {where_sql}
        {pair_round_sql}
        {pair_interaction_filter}
    ),
    pair_agg AS (
      SELECT
        card_1,
        ANY_VALUE(type_1) AS type_1,
        card_2,
        ANY_VALUE(type_2) AS type_2,
        SAFE_DIVIDE(SUM(delta_sum), SUM(delta_count)) AS delta_actual,
        SQRT(GREATEST(0, SAFE_DIVIDE(
          SUM(delta_sum_squares)
            - SAFE_DIVIDE(POW(SUM(delta_sum), 2), SUM(delta_count)),
          SUM(delta_count) - 1
        ))) AS delta_actual_ci_sd,
        SUM(delta_count) AS delta_actual_ci_n,
        SAFE_DIVIDE(SUM(elo_sum), SUM(elo_count)) AS avg_elo,
        SUM(observation_count) AS n_played
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
      p.delta_actual AS delta_actual_ci_mean,
      p.delta_actual_ci_sd AS delta_actual_ci_sd,
      p.delta_actual_ci_n AS delta_actual_ci_n,
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


def _build_combinations_paged_query(
    where_sql,
    combinations_view,
    round_filter_active=False,
    selected_rounds=None,
    sort_field="interaction",
    sort_direction="desc",
):
    """Wrap the existing combination aggregate in a small server-paged result."""
    base_query = _build_combinations_query(
        where_sql,
        combinations_view,
        round_filter_active,
        selected_rounds,
        apply_interaction_filters=(combinations_view == COMBINATIONS_VIEW_CARD_CARD),
    )
    final_order = base_query.rfind("ORDER BY")
    if final_order >= 0:
        base_query = base_query[:final_order]

    projected_card_one = (
        "CASE WHEN (@combination_primary != '' AND card_2 = @combination_primary) "
        "OR (@combination_primary = '' AND @combination_secondary != '' "
        "AND card_1 = @combination_secondary) THEN card_2 ELSE card_1 END"
    )
    projected_card_two = (
        "CASE WHEN (@combination_primary != '' AND card_2 = @combination_primary) "
        "OR (@combination_primary = '' AND @combination_secondary != '' "
        "AND card_1 = @combination_secondary) THEN card_1 ELSE card_2 END"
    )

    if combinations_view == COMBINATIONS_VIEW_CARD_CARD:
        sort_expressions = {
            "card_1": projected_card_one,
            "card_2": projected_card_two,
        }
        stable_fields = [projected_card_one, projected_card_two, "pair_type"]
        visible_filter = """
        pair_type IN UNNEST(@combination_pair_types)
        AND (
          (@combination_primary = '' AND @combination_secondary = '')
          OR (
            @combination_primary != '' AND @combination_secondary = ''
            AND (card_1 = @combination_primary OR card_2 = @combination_primary)
          )
          OR (
            @combination_primary = '' AND @combination_secondary != ''
            AND (card_1 = @combination_secondary OR card_2 = @combination_secondary)
          )
          OR (
            @combination_primary != '' AND @combination_secondary != ''
            AND ((card_1 = @combination_primary AND card_2 = @combination_secondary)
              OR (card_1 = @combination_secondary AND card_2 = @combination_primary))
          )
        )
        """
        range_fields = ["avg_elo", "interaction", "delta_1", "delta_2", "delta_combined", "delta_actual"]
        card_options_sql = "ARRAY<STRING>[]"
        endgame_options_sql = "ARRAY<STRING>[]"
        action_card_options_sql = "ARRAY<STRING>[]"
    elif combinations_view == COMBINATIONS_VIEW_CARD_ACTION_CARD:
        sort_expressions = {}
        stable_fields = ["card_name", "action_card_key", "pair_type"]
        visible_filter = """
        pair_type IN UNNEST(@combination_pair_types)
        AND (@combination_primary = '' OR card_name = @combination_primary)
        AND (@combination_secondary = '' OR action_card_key = @combination_secondary)
        """
        range_fields = ["avg_elo", "interaction", "delta_card", "delta_action", "delta_combined", "delta_actual"]
        card_options_sql = "ARRAY_AGG(DISTINCT card_name IGNORE NULLS ORDER BY card_name)"
        endgame_options_sql = "ARRAY<STRING>[]"
        action_card_options_sql = "ARRAY_AGG(DISTINCT action_card_key IGNORE NULLS ORDER BY action_card_key)"
    else:
        context_field = {
            COMBINATIONS_VIEW_CARD_MAP: "map_name",
            COMBINATIONS_VIEW_CARD_ROUND: "round_name",
            COMBINATIONS_VIEW_CARD_ENDGAME: "endgame_name",
        }[combinations_view]
        sort_expressions = {}
        stable_fields = ["card_name", context_field, "card_type"]
        visible_filter = """
        card_type IN UNNEST(@combination_card_types)
        AND (@combination_primary = '' OR card_name = @combination_primary)
        """
        if combinations_view == COMBINATIONS_VIEW_CARD_MAP:
            visible_filter += " AND map_name IN UNNEST(@combination_header_maps)"
            range_fields = ["avg_elo", "interaction", "delta_general", "delta_map"]
            card_options_sql = "ARRAY_AGG(DISTINCT card_name IGNORE NULLS ORDER BY card_name)"
            endgame_options_sql = "ARRAY<STRING>[]"
            action_card_options_sql = "ARRAY<STRING>[]"
        elif combinations_view == COMBINATIONS_VIEW_CARD_ROUND:
            visible_filter += " AND round_name IN UNNEST(@combination_header_rounds)"
            range_fields = ["avg_elo", "interaction", "delta_general", "delta_round"]
            card_options_sql = "ARRAY_AGG(DISTINCT card_name IGNORE NULLS ORDER BY card_name)"
            endgame_options_sql = "ARRAY<STRING>[]"
            action_card_options_sql = "ARRAY<STRING>[]"
        else:
            visible_filter += (
                " AND (@combination_secondary = '' OR endgame_name = @combination_secondary)"
            )
            range_fields = ["avg_elo", "interaction", "delta_card", "delta_endgame", "delta_combined", "delta_actual"]
            card_options_sql = "ARRAY_AGG(DISTINCT card_name IGNORE NULLS ORDER BY card_name)"
            endgame_options_sql = "ARRAY_AGG(DISTINCT endgame_name IGNORE NULLS ORDER BY endgame_name)"
            action_card_options_sql = "ARRAY<STRING>[]"

    direct_sort_fields = {
        "delta_combined", "delta_actual", "delta_general", "delta_map", "delta_round",
        "delta_card", "delta_action", "delta_endgame", "interaction", "avg_elo", "n_played",
        "pair_type", "card_name", "action_card_name", "action_card_key", "map_name", "round_name", "endgame_name", "card_type",
    }
    if sort_field not in COMBINATION_SORT_FIELDS[combinations_view]:
        sort_field = "interaction"
    sort_expression = sort_expressions.get(sort_field, sort_field if sort_field in direct_sort_fields else "interaction")
    sort_direction = "asc" if sort_direction == "asc" else "desc"
    order_sql = f"{sort_expression} {sort_direction.upper()} NULLS LAST"
    for stable_field in stable_fields:
        order_sql += f", {stable_field} ASC NULLS LAST"

    range_selects = ",\n          ".join(
        f"MIN({field}) AS range_{field}_min, MAX({field}) AS range_{field}_max"
        for field in range_fields
    )
    return f"""
    WITH base AS (
      {base_query}
    ),
    ranges AS (
      SELECT
        {range_selects}
      FROM base
    ),
    candidates AS (
      SELECT *
      FROM base
      WHERE {visible_filter}
    ),
    candidate_summary AS (
      SELECT
        COUNT(*) AS candidate_count,
        MAX(n_played) AS highest_matching_play_count
      FROM candidates
    ),
    ranked AS (
      SELECT
        b.*,
        ROW_NUMBER() OVER (ORDER BY {order_sql}) AS global_rank
      FROM candidates b
      WHERE n_played >= @combination_min_plays
    ),
    visible AS (
      SELECT * FROM ranked
    ),
    options AS (
      SELECT
        {card_options_sql} AS card_options,
        {endgame_options_sql} AS endgame_options,
        {action_card_options_sql} AS action_card_options
      FROM base
    )
    SELECT
      (SELECT COUNT(*) FROM visible) AS total_rows,
      candidate_summary.candidate_count,
      candidate_summary.highest_matching_play_count,
      ranges.*,
      options.card_options,
      options.endgame_options,
      options.action_card_options,
      ARRAY(
        SELECT AS STRUCT *
        FROM visible
        ORDER BY {order_sql}
        LIMIT @combination_page_size
        OFFSET @combination_offset
      ) AS page_rows
    FROM ranges
    CROSS JOIN candidate_summary
    CROSS JOIN options
    """


def _build_mw_action_cards_query(
    selected_maps,
    player_elo_min,
    player_elo_max,
    opponent_elo_min,
    opponent_elo_max,
    date_from,
    date_to,
    completed_only,
    arena_only,
    tournament_only,
    starting_positions=None,
    mw_action_cards_view=MW_ACTION_CARDS_VIEW_GENERAL,
):
    parameters = []
    if mw_action_cards_view != MW_ACTION_CARDS_VIEW_BY_MAP:
        parameters.append(bigquery.ArrayQueryParameter("selected_maps", "STRING", selected_maps))
    for name, value in (
        ("player_elo_min", player_elo_min),
        ("player_elo_max", player_elo_max),
        ("opponent_elo_min", opponent_elo_min),
        ("opponent_elo_max", opponent_elo_max),
    ):
        if value is not None:
            parameters.append(bigquery.ScalarQueryParameter(name, "INT64", value))
    if date_from is not None:
        parameters.append(bigquery.ScalarQueryParameter("date_from", "DATE", date_from))
    if date_to is not None:
        parameters.append(bigquery.ScalarQueryParameter("date_to", "DATE", date_to))
    if starting_positions:
        parameters.append(bigquery.ArrayQueryParameter(
            "starting_positions", "STRING", starting_positions
        ))

    def rating_bounds(alias):
        clauses = []
        for field, name, value, operator in (
            ("pre_match_elo", "player_elo_min", player_elo_min, ">="),
            ("pre_match_elo", "player_elo_max", player_elo_max, "<="),
            ("opponent_pre_match_elo", "opponent_elo_min", opponent_elo_min, ">="),
            ("opponent_pre_match_elo", "opponent_elo_max", opponent_elo_max, "<="),
        ):
            if value is not None:
                clauses.append(f"COALESCE({alias}.{field}, 0) {operator} @{name}")
        return clauses

    def common_where(alias, map_mode="own"):
        clauses = rating_bounds(alias)
        if map_mode in ("own", "both"):
            clauses.append(f"{alias}.Map IN UNNEST(@selected_maps)")
        if map_mode == "both":
            clauses.append(f"{alias}.opponent_map IN UNNEST(@selected_maps)")
        if date_from is not None:
            clauses.append(f"{alias}.game_date >= @date_from")
        if date_to is not None:
            clauses.append(f"{alias}.game_date <= @date_to")
        if completed_only:
            clauses.append(f"({_completed_game_sql(alias)})")
        if arena_only:
            clauses.append(f"{alias}.arena_season IS NOT NULL")
        if tournament_only:
            clauses.append(f"COALESCE({alias}.is_tournament, FALSE) = TRUE")
        if starting_positions:
            clauses.append(f"{alias}.starting_position IN UNNEST(@starting_positions)")
        return clauses or ["TRUE"]

    if mw_action_cards_view == MW_ACTION_CARDS_VIEW_BY_MAP:
        where_sql = " AND ".join(common_where("a", map_mode="none"))
        map_columns = []
        for map_item in ALL_MAPS_FOR_METRICS[:15]:
            key = map_item["key"]
            full = map_item["full"].replace("'", "''")
            map_columns.extend([
                f"ROUND(MAX(IF(m.Map = '{full}', m.delta_mean, NULL)), 3) AS {key}",
                f"MAX(IF(m.Map = '{full}', m.delta_mean, NULL)) AS {key}_ci_mean",
                f"MAX(IF(m.Map = '{full}', m.delta_sd, NULL)) AS {key}_ci_sd",
                f"COALESCE(MAX(IF(m.Map = '{full}', m.delta_n, NULL)), 0) AS {key}_ci_n",
            ])
        return f"""
        WITH filtered AS (
          SELECT *
          FROM `{PREPARED_MW_ACTION_CARD_MAP_AGGREGATES_TABLE}` a
          WHERE {where_sql}
        ), per_map AS (
          SELECT
            card_key, Map,
            SAFE_DIVIDE(SUM(delta_sum), SUM(delta_count)) AS delta_mean,
            SQRT(GREATEST(0, SAFE_DIVIDE(
              SUM(delta_sum_squares)
                - SAFE_DIVIDE(POW(SUM(delta_sum), 2), SUM(delta_count)),
              SUM(delta_count) - 1
            ))) AS delta_sd,
            SUM(delta_count) AS delta_n
          FROM filtered
          GROUP BY card_key, Map
        ), overall AS (
          SELECT
            card_key,
            SAFE_DIVIDE(SUM(delta_sum), SUM(delta_count)) AS delta_mean,
            SQRT(GREATEST(0, SAFE_DIVIDE(
              SUM(delta_sum_squares)
                - SAFE_DIVIDE(POW(SUM(delta_sum), 2), SUM(delta_count)),
              SUM(delta_count) - 1
            ))) AS delta_sd,
            SUM(delta_count) AS delta_n
          FROM filtered
          GROUP BY card_key
        ), catalog AS ({_mw_action_card_catalog_sql()})
        SELECT
          c.card_order, c.card_type AS type, c.card_number, c.card_name,
          {', '.join(map_columns)},
          ROUND(o.delta_mean, 3) AS delta_overall,
          o.delta_mean AS delta_overall_ci_mean,
          o.delta_sd AS delta_overall_ci_sd,
          COALESCE(o.delta_n, 0) AS delta_overall_ci_n
        FROM catalog c
        LEFT JOIN per_map m USING(card_key)
        LEFT JOIN overall o USING(card_key)
        GROUP BY
          c.card_order, c.card_type, c.card_number, c.card_name,
          o.delta_mean, o.delta_sd, o.delta_n
        ORDER BY c.card_order
        """, parameters

    if mw_action_cards_view == MW_ACTION_CARDS_VIEW_SYNERGIES:
        pair_where = " AND ".join(common_where("p", map_mode="own"))
        standalone_where = " AND ".join(common_where("s", map_mode="own"))
        return f"""
        WITH standalone AS (
          SELECT card_key, AVG(elo_delta) AS individual_delta
          FROM `{PREPARED_MW_ACTION_CARD_PLAYERS_TABLE}` s
          WHERE {standalone_where}
          GROUP BY card_key
        ), pair_agg AS (
          SELECT
            card_1_order, card_1_key, card_1_type, card_1_number, card_1_name,
            card_2_order, card_2_key, card_2_type, card_2_number, card_2_name,
            SAFE_DIVIDE(SUM(delta_sum), SUM(delta_count)) AS delta_actual,
            SQRT(GREATEST(0, SAFE_DIVIDE(
              SUM(delta_sum_squares)
                - SAFE_DIVIDE(POW(SUM(delta_sum), 2), SUM(delta_count)),
              SUM(delta_count) - 1
            ))) AS delta_actual_ci_sd,
            SUM(delta_count) AS delta_actual_ci_n,
            SAFE_DIVIDE(SUM(elo_sum), SUM(elo_count)) AS avg_elo,
            SUM(observation_count) AS n_picked
          FROM `{PREPARED_MW_ACTION_CARD_SYNERGY_AGGREGATES_TABLE}` p
          WHERE {pair_where}
          GROUP BY
            card_1_order, card_1_key, card_1_type, card_1_number, card_1_name,
            card_2_order, card_2_key, card_2_type, card_2_number, card_2_name
        )
        SELECT
          p.card_1_order, p.card_1_key, p.card_1_type, p.card_1_number, p.card_1_name,
          ROUND(s1.individual_delta, 3) AS delta_1,
          p.card_2_order, p.card_2_key, p.card_2_type, p.card_2_number, p.card_2_name,
          ROUND(s2.individual_delta, 3) AS delta_2,
          ROUND(s1.individual_delta + s2.individual_delta, 3) AS delta_combined,
          ROUND(p.delta_actual, 3) AS delta_actual,
          p.delta_actual AS delta_actual_ci_mean,
          p.delta_actual_ci_sd,
          p.delta_actual_ci_n,
          ROUND(
            p.delta_actual - (s1.individual_delta + s2.individual_delta), 3
          ) AS interaction,
          ROUND(p.avg_elo, 0) AS avg_elo,
          p.n_picked,
          CONCAT(p.card_1_type, ' + ', p.card_2_type) AS pair_type
        FROM pair_agg p
        JOIN standalone s1 ON p.card_1_key = s1.card_key
        JOIN standalone s2 ON p.card_2_key = s2.card_key
        ORDER BY interaction DESC, n_picked DESC,
          p.card_1_order, p.card_2_order
        """, parameters

    player_where = common_where("p", map_mode="own")
    table_where = [
        "d.p1_map IN UNNEST(@selected_maps)",
        "d.p2_map IN UNNEST(@selected_maps)",
    ]
    # Draft percentages are table-level observations, so neither stored player
    # owns the Player/Opponent role. Match the requested Elo pairing in either
    # orientation: p1 as Player and p2 as Opponent, or the reverse. The player-
    # level Delta/Elo query above keeps its natural selected-player orientation.
    def role_bounds(field, role):
        values = (
            (f"{role}_elo_min", player_elo_min if role == "player" else opponent_elo_min, ">="),
            (f"{role}_elo_max", player_elo_max if role == "player" else opponent_elo_max, "<="),
        )
        return [
            f"COALESCE({field}, 0) {operator} @{parameter_name}"
            for parameter_name, value, operator in values
            if value is not None
        ]

    if any(value is not None for value in (
        player_elo_min, player_elo_max, opponent_elo_min, opponent_elo_max,
    )):
        p1_as_player = (
            role_bounds("d.p1_pre_match_elo", "player")
            + role_bounds("d.p2_pre_match_elo", "opponent")
        )
        p2_as_player = (
            role_bounds("d.p2_pre_match_elo", "player")
            + role_bounds("d.p1_pre_match_elo", "opponent")
        )
        if starting_positions == ["First player"]:
            table_where.append("(" + " AND ".join(p1_as_player) + ")")
        elif starting_positions == ["Second player"]:
            table_where.append("(" + " AND ".join(p2_as_player) + ")")
        else:
            table_where.append(
                "((" + " AND ".join(p1_as_player) + ") OR ("
                + " AND ".join(p2_as_player) + "))"
            )
    if date_from is not None:
        table_where.append("d.game_date >= @date_from")
    if date_to is not None:
        table_where.append("d.game_date <= @date_to")
    if completed_only:
        table_where.append(f"({_completed_game_sql('d')})")
    if arena_only:
        table_where.append("d.arena_season IS NOT NULL")
    if tournament_only:
        table_where.append("COALESCE(d.is_tournament, FALSE) = TRUE")

    catalog_sql = _mw_action_card_catalog_sql()
    query = f"""
    WITH
    catalog AS ({catalog_sql}),
    player_stats AS (
      SELECT
        p.card_key,
        ROUND(AVG(p.elo_delta), 3) AS delta_picked,
        AVG(p.elo_delta) AS delta_picked_ci_mean,
        STDDEV_SAMP(p.elo_delta) AS delta_picked_ci_sd,
        COUNT(p.elo_delta) AS delta_picked_ci_n,
        ROUND(AVG(IF(p.upgraded, p.elo_delta, NULL)), 3) AS delta_picked_upgraded,
        AVG(IF(p.upgraded, p.elo_delta, NULL)) AS delta_picked_upgraded_ci_mean,
        STDDEV_SAMP(IF(p.upgraded, p.elo_delta, NULL)) AS delta_picked_upgraded_ci_sd,
        COUNTIF(p.upgraded AND p.elo_delta IS NOT NULL) AS delta_picked_upgraded_ci_n,
        ROUND(AVG(IF(NOT p.upgraded, p.elo_delta, NULL)), 3) AS delta_picked_basic,
        AVG(IF(NOT p.upgraded, p.elo_delta, NULL)) AS delta_picked_basic_ci_mean,
        STDDEV_SAMP(IF(NOT p.upgraded, p.elo_delta, NULL)) AS delta_picked_basic_ci_sd,
        COUNTIF(NOT p.upgraded AND p.elo_delta IS NOT NULL) AS delta_picked_basic_ci_n,
        ROUND(AVG(p.pre_match_elo), 0) AS elo_picked
      FROM `{PREPARED_MW_ACTION_CARD_PLAYERS_TABLE}` p
       WHERE {' AND '.join(player_where)}
      GROUP BY p.card_key
    ),
    draft_stats AS (
      SELECT
        d.card_key,
        COUNT(*) AS available_n,
        COUNTIF(d.picked) AS picked_n,
        COUNTIF(d.drafted_first) AS drafted_first_n,
        COUNTIF(d.drafted_second) AS drafted_second_n,
        COUNTIF(d.undrafted) AS undrafted_n
      FROM `{PREPARED_MW_ACTION_CARD_DRAFTS_TABLE}` d
      WHERE {' AND '.join(table_where)}
      GROUP BY d.card_key
    )
    SELECT
      c.card_order, c.card_type AS type, c.card_number, c.card_name,
      p.delta_picked, p.delta_picked_ci_mean, p.delta_picked_ci_sd,
      COALESCE(p.delta_picked_ci_n, 0) AS delta_picked_ci_n,
      p.delta_picked_upgraded,
      p.delta_picked_upgraded_ci_mean,
      p.delta_picked_upgraded_ci_sd,
      COALESCE(p.delta_picked_upgraded_ci_n, 0) AS delta_picked_upgraded_ci_n,
      p.delta_picked_basic,
      p.delta_picked_basic_ci_mean,
      p.delta_picked_basic_ci_sd,
      COALESCE(p.delta_picked_basic_ci_n, 0) AS delta_picked_basic_ci_n,
      p.elo_picked,
      COALESCE(d.available_n, 0) AS available_n,
      COALESCE(d.picked_n, 0) AS picked_n,
      ROUND(100 * SAFE_DIVIDE(d.picked_n, d.available_n), 4) AS picked_pct,
      COALESCE(d.drafted_first_n, 0) AS drafted_first_n,
      ROUND(100 * SAFE_DIVIDE(d.drafted_first_n, d.available_n), 4) AS drafted_first_pct,
      COALESCE(d.drafted_second_n, 0) AS drafted_second_n,
      ROUND(100 * SAFE_DIVIDE(d.drafted_second_n, d.available_n), 4) AS drafted_second_pct,
      COALESCE(d.undrafted_n, 0) AS undrafted_n,
      ROUND(100 * SAFE_DIVIDE(d.undrafted_n, d.available_n), 4) AS undrafted_pct
    FROM catalog c
    LEFT JOIN player_stats p USING(card_key)
    LEFT JOIN draft_stats d USING(card_key)
    ORDER BY c.card_order
    """
    return query, parameters


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
    completed_only,
    arena_only=False,
    tournament_only=False,
    starting_positions=None,
    endgames_view=ENDGAMES_VIEW_GENERAL,
    maps_view=MAPS_VIEW_METRICS,
    sponsor_endgames_view=SPONSOR_ENDGAMES_VIEW_CP,
    combinations_view=COMBINATIONS_VIEW_CARD_CARD,
    build_view=BUILD_VIEW_ENCLOSURES,
    predictors_view=PREDICTORS_VIEW_GENERAL,
    actions_view=ACTIONS_VIEW_STARTING_POSITION,
    conservation_view=CONSERVATION_VIEW_PROJECTS,
    scoring_view=SCORING_VIEW_FINAL_SCORE,
    workers_view=WORKERS_VIEW_GENERAL,
    players_view=PLAYERS_VIEW_GENERAL,
    players_player=None,
    players_players=None,
    players_identity=None,
    players_identities=None,
    last_x_games=None,
    players_arena_only=False,
    players_arena_seasons=None,
    records_view=RECORDS_VIEW_ELO_LEADERBOARD,
    mw_action_cards_view=MW_ACTION_CARDS_VIEW_GENERAL,
    records_player=None,
    records_arena_only=False,
    records_tournament_only=False,
    players_component="combined",
    hexes_expanded=False,
    scoring_expanded=False,
    combination_paged=False,
    combination_page=COMBINATION_PAGE_DEFAULT,
    combination_page_size=COMBINATION_PAGE_SIZE_DEFAULT,
    combination_min_plays=COMBINATION_DEFAULT_MIN_PLAYS,
    combination_sort="interaction",
    combination_sort_direction="desc",
    combination_pair_types=None,
    combination_card_types=None,
    combination_primary="",
    combination_secondary="",
    combination_header_maps=None,
    combination_header_rounds=None,
    combination_scope_compact=False,
    use_query_cache=True,
    query_priority=bigquery.QueryPriority.INTERACTIVE,
):
    if stats_page == STATS_PAGE_MW_ACTION_CARDS:
        if int(is_mw) != 1:
            raise ValueError("MW Action Cards is only available for Marine Worlds")
        query, query_parameters = _build_mw_action_cards_query(
            selected_maps,
            player_elo_min,
            player_elo_max,
            opponent_elo_min,
            opponent_elo_max,
            date_from,
            date_to,
            completed_only,
            arena_only,
            tournament_only,
            starting_positions,
            mw_action_cards_view,
        )
    elif stats_page == STATS_PAGE_HOME:
        # Home is the deliberate all-map exception: Maps 1-8, A, and 0 remain
        # eligible because the Home filter bar exposes them as active defaults.
        where_sql, query_parameters = _build_full_sample_where_sql(
            is_mw,
            selected_maps,
            player_elo_min,
            player_elo_max,
            opponent_elo_min,
            opponent_elo_max,
            date_from,
            date_to,
            completed_only,
            exclude_invalid_maps=False,
            arena_only=arena_only,
            tournament_only=tournament_only,
            starting_positions=starting_positions,
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
                arena_only,
                tournament_only,
                starting_positions,
            )
            query = _build_maps_metrics_query(where_sql)
    elif stats_page == STATS_PAGE_ICONS:
        where_sql, query_parameters = _build_full_sample_where_sql(
            is_mw,
            selected_maps,
            player_elo_min,
            player_elo_max,
            opponent_elo_min,
            opponent_elo_max,
            date_from,
            date_to,
            None,
            arena_only=arena_only,
            tournament_only=tournament_only,
            starting_positions=starting_positions,
        )
        query = _build_icons_query(where_sql)
    elif stats_page == STATS_PAGE_BUILD and build_view == BUILD_VIEW_HEXES:
        where_sql, query_parameters = _build_full_sample_where_sql(
            is_mw,
            selected_maps,
            player_elo_min,
            player_elo_max,
            opponent_elo_min,
            opponent_elo_max,
            date_from,
            date_to,
            None,
            arena_only=arena_only,
            tournament_only=tournament_only,
            starting_positions=starting_positions,
        )
        query = _build_build_hexes_query(where_sql, expanded=hexes_expanded)
    elif stats_page == STATS_PAGE_PREDICTORS:
        where_sql, query_parameters = _build_full_sample_where_sql(
            is_mw,
            selected_maps,
            player_elo_min,
            player_elo_max,
            opponent_elo_min,
            opponent_elo_max,
            date_from,
            date_to,
            completed_only,
            arena_only=arena_only,
            tournament_only=tournament_only,
            starting_positions=starting_positions,
        )
        query = _build_predictors_query(
            where_sql, predictors_view, starting_positions=starting_positions
        )
    elif stats_page == STATS_PAGE_ACTIONS and actions_view in (
        ACTIONS_VIEW_UPGRADES,
        ACTIONS_VIEW_UPGRADES_BY_MAP,
    ):
        where_sql, query_parameters = _build_full_sample_where_sql(
            is_mw,
            selected_maps,
            player_elo_min,
            player_elo_max,
            opponent_elo_min,
            opponent_elo_max,
            date_from,
            date_to,
            completed_only,
            arena_only=arena_only,
            tournament_only=tournament_only,
            starting_positions=starting_positions,
        )
        query = _build_actions_query(where_sql, actions_view)
    elif stats_page == STATS_PAGE_CONSERVATION and conservation_view == CONSERVATION_VIEW_PROJECTS:
        where_sql, query_parameters = _build_full_sample_where_sql(
            is_mw,
            selected_maps,
            player_elo_min,
            player_elo_max,
            opponent_elo_min,
            opponent_elo_max,
            date_from,
            date_to,
            None,
            arena_only=arena_only,
            tournament_only=tournament_only,
            starting_positions=starting_positions,
        )
        query = _build_conservation_query(where_sql, conservation_view)
    elif stats_page == STATS_PAGE_SCORING:
        where_sql, query_parameters = _build_full_sample_where_sql(
            is_mw,
            selected_maps,
            player_elo_min,
            player_elo_max,
            opponent_elo_min,
            opponent_elo_max,
            date_from,
            date_to,
            None,
            arena_only=arena_only,
            tournament_only=tournament_only,
            starting_positions=starting_positions,
        )
        query = _build_scoring_query(where_sql, scoring_view, expanded=scoring_expanded)
    elif stats_page == STATS_PAGE_WORKERS and workers_view == WORKERS_VIEW_GENERAL:
        where_sql, query_parameters = _build_full_sample_where_sql(
            is_mw,
            selected_maps,
            player_elo_min,
            player_elo_max,
            opponent_elo_min,
            opponent_elo_max,
            date_from,
            date_to,
            None,
            arena_only=arena_only,
            tournament_only=tournament_only,
            starting_positions=starting_positions,
        )
        query = _build_workers_query(where_sql, workers_view)
    elif stats_page == STATS_PAGE_WORKERS:
        where_sql, query_parameters = _build_where_sql(
            is_mw,
            selected_maps,
            player_elo_min,
            player_elo_max,
            opponent_elo_min,
            opponent_elo_max,
            date_from,
            date_to,
            completed_only,
            arena_only=arena_only,
            tournament_only=tournament_only,
            starting_positions=starting_positions,
        )
        query = _build_workers_query(where_sql, workers_view)
    elif stats_page == STATS_PAGE_PLAYERS:
        players_completion_filter = (
            completed_only
            if players_view == PLAYERS_VIEW_PERFORMANCE_BY_MAP
            else True
        )
        where_sql, query_parameters = _build_full_sample_where_sql(
            is_mw,
            selected_maps,
            None,
            None,
            opponent_elo_min,
            opponent_elo_max,
            date_from,
            date_to,
            players_completion_filter,
            exclude_invalid_maps=False,
            arena_only=False,
            tournament_only=tournament_only,
            starting_positions=starting_positions,
        )
        if players_arena_only:
            where_sql += " AND f.arena_season IN UNNEST(@players_arena_seasons)"
            query_parameters.append(bigquery.ArrayQueryParameter(
                "players_arena_seasons", "STRING", players_arena_seasons or []
            ))
            if players_arena_seasons:
                metadata_by_season = {
                    item["season"]: item for item in _load_arena_metadata().get("seasons", [])
                }
                selected_metadata = [
                    metadata_by_season[item] for item in players_arena_seasons
                    if item in metadata_by_season
                ]
                arena_start = min(
                    datetime.fromisoformat(item["start_utc"].replace("Z", "+00:00")).date()
                    for item in selected_metadata
                )
                arena_end = max(
                    datetime.fromisoformat(
                        item["effective_end_utc"].replace("Z", "+00:00")
                    ).date()
                    for item in selected_metadata
                )
                # arena_season remains the exact semantic predicate; these
                # bounds exist solely to prune the prepared table's date
                # partitions before the selected seasons are aggregated.
                where_sql += " AND f.game_date BETWEEN @arena_start_date AND @arena_end_date"
                query_parameters.extend([
                    bigquery.ScalarQueryParameter("arena_start_date", "DATE", arena_start),
                    bigquery.ScalarQueryParameter("arena_end_date", "DATE", arena_end),
                ])
        query_parameters.extend([
            bigquery.ScalarQueryParameter("players_player", "STRING", players_player or ""),
            bigquery.ArrayQueryParameter("players_players", "STRING", players_players or []),
            bigquery.ScalarQueryParameter(
                "players_identity", "STRING", players_identity or ""
            ),
            bigquery.ArrayQueryParameter(
                "players_identities", "STRING", players_identities or []
            ),
            bigquery.ScalarQueryParameter(
                "players_identity_bucket",
                "INT64",
                int(
                    hashlib.sha256(
                        (players_identity or "").encode("utf-8")
                    ).hexdigest()[:8],
                    16,
                ) % 1024,
            ),
            bigquery.ArrayQueryParameter(
                "players_identity_buckets",
                "INT64",
                [
                    int(
                        hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8],
                        16,
                    ) % 1024
                    for identity in (players_identities or [])
                ],
            ),
            bigquery.ScalarQueryParameter("last_x_games", "INT64", int(last_x_games or 0)),
        ])
        rollup_where_sql = where_sql.replace(
            "CAST(f.game_ended_at AS DATE)", "f.game_date"
        )
        if players_view == PLAYERS_VIEW_PERFORMANCE_BY_MAP:
            query = _build_players_performance_by_map_query(
                where_sql if last_x_games else rollup_where_sql,
                use_last_x=bool(last_x_games),
            )
        elif players_view == PLAYERS_VIEW_COMPARISON:
            query = (
                _build_players_comparison_query(
                    where_sql, PREPARED_PLAYERS_RECENT_TABLE
                )
                if last_x_games
                else _build_players_comparison_rollup_query(
                    rollup_where_sql
                )
            )
        elif not last_x_games and players_component in {"baseline", "selected"}:
            query = _build_players_rollup_query(
                rollup_where_sql, players_component
            )
        else:
            query = _build_players_query(
                where_sql,
                players_component,
                (
                    PREPARED_PLAYERS_RECENT_TABLE
                    if last_x_games and players_component in {"selected", "combined"}
                    else None
                ),
            )
    elif stats_page == STATS_PAGE_RECORDS:
        where_sql, query_parameters = _build_full_sample_where_sql(
            is_mw,
            selected_maps,
            None,
            None,
            opponent_elo_min,
            opponent_elo_max,
            date_from,
            date_to,
            None,
            exclude_invalid_maps=False,
            arena_only=(records_arena_only or arena_only),
            tournament_only=(records_tournament_only or tournament_only),
            starting_positions=starting_positions,
        )
        if records_player:
            # The player predicate is part of the Records SQL, while its value
            # must be attached to the QueryJobConfig assembled in this scope.
            query_parameters.append(
                bigquery.ScalarQueryParameter("records_player", "STRING", records_player)
            )
        query = _build_records_query(
            where_sql,
            records_view,
            records_player=records_player,
            records_arena_only=records_arena_only,
            records_tournament_only=records_tournament_only,
        )
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
            completed_only,
            arena_only=arena_only,
            tournament_only=tournament_only,
            starting_positions=starting_positions,
        )
    if stats_page == STATS_PAGE_SPONSOR_ENDGAMES:
        query = _build_sponsor_endgames_query(where_sql, sponsor_endgames_view)
    if stats_page == STATS_PAGE_BUILD:
        if build_view == BUILD_VIEW_ENCLOSURES:
            query = _build_build_enclosures_query(where_sql)
    if stats_page == STATS_PAGE_ACTIONS:
        query = _build_actions_query(where_sql, actions_view)
    if stats_page == STATS_PAGE_CONSERVATION:
        query = _build_conservation_query(where_sql, conservation_view)
    if stats_page == STATS_PAGE_SCORING:
        query = _build_scoring_query(where_sql, scoring_view, expanded=scoring_expanded)
    if stats_page == STATS_PAGE_WORKERS:
        query = _build_workers_query(where_sql, workers_view)
    if stats_page == STATS_PAGE_COMBINATIONS:
        if combination_paged:
            query = _build_combinations_paged_query(
                where_sql,
                combinations_view,
                round_filter_active,
                selected_rounds,
                combination_sort,
                combination_sort_direction,
            )
        else:
            query = _build_combinations_query(
                where_sql,
                combinations_view,
                round_filter_active,
                selected_rounds,
            )
        if combination_scope_compact:
            # Returning 35k individual BigQuery Row objects dominated the old
            # cold request. One JSON array removes that per-row API overhead;
            # the Function decodes it once and stores the reusable scope cache.
            final_order = query.rfind("ORDER BY")
            if final_order >= 0:
                query = query[:final_order]
            compact_fields = [
                "card_1", "type_1", "delta_1", "card_2", "type_2",
                "delta_2", "delta_combined", "delta_actual",
                "delta_actual_ci_mean", "delta_actual_ci_sd",
                "delta_actual_ci_n", "interaction", "avg_elo", "n_played",
                "pair_type",
            ]
            compact_array = ", ".join(
                f"CAST(b.{field} AS STRING)" for field in compact_fields
            )
            query = f"""
            SELECT STRING_AGG(
              TO_JSON_STRING([{compact_array}]),
              '\\n'
            ) AS rows_compact
            FROM ({query}) b
            """
        if combinations_view == COMBINATIONS_VIEW_CARD_MAP:
            query_parameters.append(
                bigquery.ArrayQueryParameter("combination_maps", "STRING", VALID_MAPS)
            )
        if combination_paged:
            query_parameters.extend([
                bigquery.ScalarQueryParameter("combination_page_size", "INT64", combination_page_size),
                bigquery.ScalarQueryParameter("combination_offset", "INT64", max(0, (combination_page - 1) * combination_page_size)),
                bigquery.ScalarQueryParameter("combination_min_plays", "INT64", combination_min_plays),
                bigquery.ArrayQueryParameter("combination_pair_types", "STRING", combination_pair_types or []),
                bigquery.ArrayQueryParameter("combination_card_types", "STRING", combination_card_types or []),
                bigquery.ScalarQueryParameter("combination_primary", "STRING", combination_primary or ""),
                bigquery.ScalarQueryParameter("combination_secondary", "STRING", combination_secondary or ""),
                bigquery.ArrayQueryParameter("combination_header_maps", "STRING", combination_header_maps or []),
                bigquery.ArrayQueryParameter("combination_header_rounds", "STRING", combination_header_rounds or []),
            ])
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
        priority=query_priority,
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

    if stats_page == STATS_PAGE_PLAYERS:
        if players_view == PLAYERS_VIEW_PERFORMANCE_BY_MAP:
            schema_field_names = {field.name for field in results.schema}
            for row in results:
                item = {
                    "sort_order": int(row.sort_order or 0),
                    "player": row.player,
                }
                for map_meta in ALL_MAPS_FOR_METRICS:
                    key = map_meta["key"]
                    item[key] = getattr(row, key, None)
                    _attach_ci95(item, row, schema_field_names, key)
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
        if players_view == PLAYERS_VIEW_COMPARISON:
            for row in results:
                values = []
                for item in (row.player_values or []):
                    item_identity = (
                        item.get("player_identity")
                        if isinstance(item, dict)
                        else item.player_identity
                    )
                    item_value = item.get("value") if isinstance(item, dict) else item.value
                    item_tooltip = item.get("tooltip_value") if isinstance(item, dict) else item.tooltip_value
                    item_count = item.get("game_count") if isinstance(item, dict) else item.game_count
                    item_account_counts = (
                        item.get("account_counts")
                        if isinstance(item, dict)
                        else item.account_counts
                    )
                    values.append({
                        "player_identity": item_identity,
                        "value": item_value,
                        "tooltip_value": item_tooltip,
                        "game_count": int(item_count or 0),
                        "account_counts": _account_counts_payload(
                            item_account_counts
                        ),
                    })
                rows.append({
                    "sort_order": row.sort_order,
                    "metric": row.metric,
                    "tooltip": row.tooltip,
                    "is_default": bool(row.is_default),
                    "format": row.format,
                    "lower_is_better": bool(row.lower_is_better),
                    "values": values,
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
        for row in results:
            rows.append({
                "sort_order": row.sort_order,
                "metric": row.metric,
                "tooltip": row.tooltip,
                "is_default": bool(row.is_default),
                "format": row.format,
                "lower_is_better": bool(row.lower_is_better),
                "player": row.player,
                "all": row.all_players,
                "winners": row.winners,
                "experts": row.experts,
                "masters": row.masters,
                "count_player": int(row.count_player or 0),
                "account_counts": _account_counts_payload(row.account_counts),
                "count_all": int(row.count_all_players or 0),
                "count_winners": int(row.count_winners or 0),
                "count_experts": int(row.count_experts or 0),
                "count_masters": int(row.count_masters or 0),
                "tooltip_player": row.tooltip_player,
                "tooltip_all": row.tooltip_all_players,
                "tooltip_winners": row.tooltip_winners,
                "tooltip_experts": row.tooltip_experts,
                "tooltip_masters": row.tooltip_masters,
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
    if stats_page == STATS_PAGE_RECORDS:
        for row in results:
            item = {
                "turns": getattr(row, "turns", None),
                "score": getattr(row, "score", None),
                "player": getattr(row, "player", None),
                "map_name": getattr(row, "map_name", None),
                "table_id": getattr(row, "table_id", None),
                "game_date": getattr(row, "game_date", None),
                "result_code": getattr(row, "result_code", None),
                "ept": getattr(row, "ept", 0),
                # Public Records payload compatibility. The value is derived
                # from the opponent row's pre_match_elo.
                "opponent_elo": getattr(row, "opponent_pre_match_elo", None),
                "starting_position": getattr(row, "starting_position", None),
                "source_enriched": bool(getattr(row, "source_enriched", False)),
                "is_arena": bool(getattr(row, "is_arena", False)),
                "is_tournament": bool(getattr(row, "is_tournament", False)),
                "source_row": getattr(row, "source_row", None),
            }
            if records_view == RECORDS_VIEW_MOST_ICONS:
                item["n"] = getattr(row, "n", None)
                item["icon"] = getattr(row, "icon", None)
            elif records_view == RECORDS_VIEW_BIGGEST_TURNS:
                item.update({
                    "flat": getattr(row, "flat", None),
                    "end": getattr(row, "end", None),
                    "total": getattr(row, "total", None),
                    "move": getattr(row, "move", None),
                    "actions": getattr(row, "actions", None),
                })
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
            schema_field_names = {field.name for field in results.schema}
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
                    tooltip_key = f"tooltip_{key}"
                    if tooltip_key in schema_field_names:
                        item[tooltip_key] = getattr(row, tooltip_key, None)
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

    if stats_page == STATS_PAGE_BUILD:
        schema_field_names = {field.name for field in results.schema}
        if build_view == BUILD_VIEW_HEXES:
            for row in results:
                item = {
                    "bucket_key": row.bucket_key,
                    "bucket_label": row.bucket_label,
                    "sort_order": row.sort_order,
                    "avg": row.avg,
                    "count_avg": row.count_avg,
                    "denom_avg": row.denom_avg,
                }
                _attach_ci95(item, row, schema_field_names, "avg")
                for map_meta in ALL_MAPS_FOR_METRICS[:15]:
                    key = map_meta["key"]
                    item[key] = getattr(row, key, None)
                    item[f"count_{key}"] = getattr(row, f"count_{key}", 0)
                    item[f"denom_{key}"] = getattr(row, f"denom_{key}", 0)
                    _attach_ci95(item, row, schema_field_names, key)
                rows.append(item)
        else:
            for row in results:
                item = {
                    "enclosure": row.enclosure,
                    "category": row.category,
                    "n_total": row.n_total,
                    "empty_denominator": row.empty_denominator,
                }
                for prefix in (
                    "delta_0", "delta_1", "delta_2", "delta_3",
                    "delta_4", "delta_5_plus", "delta_empty",
                ):
                    item[prefix] = getattr(row, prefix, None)
                    item[prefix.replace("delta_", "count_")] = getattr(
                        row, prefix.replace("delta_", "count_"), 0
                    )
                    _attach_ci95(item, row, schema_field_names, prefix)
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

    if stats_page == STATS_PAGE_SCORING:
        schema_field_names = {field.name for field in results.schema}
        for row in results:
            item = {
                "bucket_key": row.bucket_key,
                "bucket_label": row.bucket_label,
                "sort_order": row.sort_order,
                "avg": row.avg,
                "count_avg": row.count_avg,
                "denom_avg": row.denom_avg,
            }
            _attach_ci95(item, row, schema_field_names, "avg")
            for map_meta in ALL_MAPS_FOR_METRICS[:15]:
                key = map_meta["key"]
                item[key] = getattr(row, key, None)
                item[f"count_{key}"] = getattr(row, f"count_{key}", 0)
                item[f"denom_{key}"] = getattr(row, f"denom_{key}", 0)
                _attach_ci95(item, row, schema_field_names, key)
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

    if stats_page == STATS_PAGE_PREDICTORS:
        schema_field_names = {field.name for field in results.schema}
        for row in results:
            item = {
                "sort_order": row.sort_order,
                "condition": row.condition,
                "delta": row.delta,
                "count": row.count,
            }
            if "denominator" in schema_field_names:
                item["denominator"] = row.denominator
            _attach_ci95(item, row, schema_field_names, "delta")
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

    if stats_page == STATS_PAGE_CONSERVATION:
        schema_field_names = {field.name for field in results.schema}
        map_keys = [item["key"] for item in ALL_MAPS_FOR_METRICS[:15]]
        for row in results:
            if conservation_view == CONSERVATION_VIEW_PROJECTS:
                item = {
                    "sort_order": row.sort_order,
                    "subject": row.subject,
                    "count_value": row.count_value,
                }
                prefixes = ["avg", *map_keys]
                for prefix in prefixes:
                    item[prefix] = getattr(row, prefix, None)
                    item[f"count_{prefix}"] = getattr(row, f"count_{prefix}", 0)
                    item[f"denom_{prefix}"] = getattr(row, f"denom_{prefix}", 0)
                    _attach_ci95(item, row, schema_field_names, prefix)
            elif conservation_view == CONSERVATION_VIEW_PROJECT_REWARDS:
                item = {
                    "sort_order": row.sort_order,
                    "label": row.label,
                    "group_name": row.group_name,
                    "applicable_map": row.applicable_map,
                    "available": bool(row.available),
                }
                for key in ["overall", *[f"order_{value}" for value in range(1, 8)]]:
                    prefix = f"delta_{key}"
                    item[prefix] = getattr(row, prefix, None)
                    item[f"count_{prefix}"] = getattr(row, f"count_{prefix}", 0)
                    item[f"freq_{key}_numer"] = getattr(row, f"freq_{key}_numer", 0)
                    item[f"freq_{key}_denom"] = getattr(row, f"freq_{key}_denom", 0)
                    _attach_ci95(item, row, schema_field_names, prefix)
            else:
                item = {
                    "sort_order": row.sort_order,
                    "label": row.label,
                    "mw_only": bool(row.mw_only),
                    "scope": row.scope,
                }
                for key in ["overall", *map_keys]:
                    prefix = f"delta_{key}"
                    item[prefix] = getattr(row, prefix, None)
                    item[f"count_{prefix}"] = getattr(row, f"count_{prefix}", 0)
                    item[f"freq_{key}_numer"] = getattr(row, f"freq_{key}_numer", 0)
                    item[f"freq_{key}_denom"] = getattr(row, f"freq_{key}_denom", 0)
                    _attach_ci95(item, row, schema_field_names, prefix)
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

    if stats_page == STATS_PAGE_ACTIONS:
        schema_field_names = {field.name for field in results.schema}
        for row in results:
            item = {
                "sort_order": getattr(row, "sort_order", None),
                "label": getattr(row, "label", None),
            }
            if "section" in schema_field_names:
                item["section"] = row.section
            if "denominator" in schema_field_names:
                item["denominator"] = row.denominator
            if "count" in schema_field_names:
                item["count"] = row.count
            # Upgrade-order frequency uses the slot-count field names
            # count_1..count_4.  They do not follow the count_<metric>
            # convention used by the delta/map fields below, so expose them
            # explicitly instead of leaving the frontend to default them to 0.
            for slot in ("1", "2", "3", "4"):
                field_name = f"count_{slot}"
                if field_name in schema_field_names:
                    item[field_name] = getattr(row, field_name, 0)
            for prefix in (
                "delta", "delta_1", "delta_2", "delta_3", "delta_4", "delta_5",
                "map_1a", "map_2a", "map_3a", "map_4a", "map_5a",
                "map_6a", "map_7a", "map_8a", "map_9", "map_10",
                "map_11", "map_12", "map_13", "map_14", "map_t1", "avg",
            ):
                if prefix in schema_field_names:
                    item[prefix] = getattr(row, prefix, None)
                    count_field = f"count_{prefix}"
                    denom_field = f"denom_{prefix}"
                    if count_field in schema_field_names:
                        item[count_field] = getattr(row, count_field, 0)
                    if denom_field in schema_field_names:
                        item[denom_field] = getattr(row, denom_field, 0)
                    _attach_ci95(item, row, schema_field_names, prefix)
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

    if stats_page == STATS_PAGE_WORKERS:
        schema_field_names = {field.name for field in results.schema}
        map_keys = [item["key"] for item in ALL_MAPS_FOR_METRICS[:15]]
        for row in results:
            item = {
                "sort_order": getattr(row, "sort_order", None),
                "label": getattr(row, "label", None),
            }
            for prefix in ["avg", *map_keys]:
                if prefix in schema_field_names:
                    item[prefix] = getattr(row, prefix, None)
                    for suffix in ("count", "denom"):
                        field_name = f"{suffix}_{prefix}"
                        if field_name in schema_field_names:
                            item[field_name] = getattr(row, field_name, 0)
                    _attach_ci95(item, row, schema_field_names, prefix)
            if "worker_avg_avg" in schema_field_names:
                item["worker_avg_avg"] = getattr(row, "worker_avg_avg", None)
                for key in map_keys:
                    item[f"worker_avg_{key}"] = getattr(row, f"worker_avg_{key}", None)
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
            for prefix in (
                "delta_0", "delta_1", "delta_2", "delta_3",
                "delta_4", "delta_5", "delta_6", "delta_3_plus",
            ):
                _attach_ci95(item, row, schema_field_names, prefix)
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

    if stats_page == STATS_PAGE_ICONS:
        schema_field_names = {field.name for field in results.schema}
        for row in results:
            item = {
                "icon": row.icon,
                "amount": row.amount,
                "n_total": row.n_total,
            }
            for prefix in (
                "delta_0", "delta_1", "delta_2", "delta_3",
                "delta_4", "delta_5", "delta_6", "delta_7_plus",
            ):
                item[prefix] = getattr(row, prefix, None)
                item[prefix.replace("delta_", "count_")] = getattr(
                    row, prefix.replace("delta_", "count_"), 0
                )
                _attach_ci95(item, row, schema_field_names, prefix)
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

    if stats_page == STATS_PAGE_MW_ACTION_CARDS:
        schema_field_names = {field.name for field in results.schema}
        for row in results:
            if mw_action_cards_view == MW_ACTION_CARDS_VIEW_BY_MAP:
                item = {
                    "card_order": row.card_order,
                    "type": row.type,
                    "card_number": row.card_number,
                    "card_name": row.card_name,
                    "delta_overall": row.delta_overall,
                }
                _attach_ci95(item, row, schema_field_names, "delta_overall")
                for map_item in ALL_MAPS_FOR_METRICS[:15]:
                    key = map_item["key"]
                    item[key] = getattr(row, key, None)
                    _attach_ci95(item, row, schema_field_names, key)
            elif mw_action_cards_view == MW_ACTION_CARDS_VIEW_SYNERGIES:
                item = {
                    "card_1_order": row.card_1_order,
                    "card_1_key": row.card_1_key,
                    "card_1_type": row.card_1_type,
                    "card_1_number": row.card_1_number,
                    "card_1_name": row.card_1_name,
                    "delta_1": row.delta_1,
                    "card_2_order": row.card_2_order,
                    "card_2_key": row.card_2_key,
                    "card_2_type": row.card_2_type,
                    "card_2_number": row.card_2_number,
                    "card_2_name": row.card_2_name,
                    "delta_2": row.delta_2,
                    "delta_actual": row.delta_actual,
                    "avg_elo": row.avg_elo,
                    "n_picked": row.n_picked,
                    "pair_type": row.pair_type,
                    "delta_combined": row.delta_combined,
                    "interaction": row.interaction,
                }
                _attach_ci95(item, row, schema_field_names, "delta_actual")
            else:
                item = {
                    "card_order": row.card_order,
                    "type": row.type,
                    "card_number": row.card_number,
                    "card_name": row.card_name,
                    "delta_picked": row.delta_picked,
                    "delta_picked_upgraded": row.delta_picked_upgraded,
                    "delta_picked_basic": row.delta_picked_basic,
                    "elo_picked": row.elo_picked,
                    "available_n": row.available_n,
                    "picked_n": row.picked_n,
                    "picked_pct": row.picked_pct,
                    "drafted_first_n": row.drafted_first_n,
                    "drafted_first_pct": row.drafted_first_pct,
                    "drafted_second_n": row.drafted_second_n,
                    "drafted_second_pct": row.drafted_second_pct,
                    "undrafted_n": row.undrafted_n,
                    "undrafted_pct": row.undrafted_pct,
                }
                _attach_ci95(item, row, schema_field_names, "delta_picked")
                _attach_ci95(item, row, schema_field_names, "delta_picked_upgraded")
                _attach_ci95(item, row, schema_field_names, "delta_picked_basic")
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
        if combination_scope_compact:
            wrapper = next(iter(results), None)
            compact_rows = wrapper.rows_compact or "" if wrapper else ""
            rows = _decode_card_card_compact_rows(compact_rows)
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
                "combination_scope_compact_rows": compact_rows,
            }
            return rows, timing
        combination_meta = None
        if combination_paged:
            wrapper = next(iter(results), None)
            result_rows = list(getattr(wrapper, "page_rows", None) or []) if wrapper else []
            result_rows = [
                SimpleNamespace(**row) if isinstance(row, dict) else row
                for row in result_rows
            ]
            schema_field_names = {field.name for field in results.schema}
            ci_prefixes = {
                COMBINATIONS_VIEW_CARD_CARD: ["delta_actual"],
                COMBINATIONS_VIEW_CARD_MAP: ["delta_map"],
                COMBINATIONS_VIEW_CARD_ROUND: ["delta_round"],
                COMBINATIONS_VIEW_CARD_ENDGAME: ["delta_actual"],
                COMBINATIONS_VIEW_CARD_ACTION_CARD: ["delta_actual"],
            }[combinations_view]
            for prefix in ci_prefixes:
                schema_field_names.update({f"{prefix}_ci_mean", f"{prefix}_ci_sd", f"{prefix}_ci_n"})
            range_fields = {
                COMBINATIONS_VIEW_CARD_CARD: ["avg_elo", "interaction", "delta_1", "delta_2", "delta_combined", "delta_actual"],
                COMBINATIONS_VIEW_CARD_MAP: ["avg_elo", "interaction", "delta_general", "delta_map"],
                COMBINATIONS_VIEW_CARD_ROUND: ["avg_elo", "interaction", "delta_general", "delta_round"],
                COMBINATIONS_VIEW_CARD_ENDGAME: ["avg_elo", "interaction", "delta_card", "delta_endgame", "delta_combined", "delta_actual"],
                COMBINATIONS_VIEW_CARD_ACTION_CARD: ["avg_elo", "interaction", "delta_card", "delta_action", "delta_combined", "delta_actual"],
            }[combinations_view]
            combination_ranges = {}
            for field in range_fields:
                combination_ranges[field] = {
                    "min": getattr(wrapper, f"range_{field}_min", None) if wrapper else None,
                    "max": getattr(wrapper, f"range_{field}_max", None) if wrapper else None,
                }
            combination_meta = {
                "combination_paged": True,
                "page": combination_page,
                "page_size": combination_page_size,
                "total_rows": int(getattr(wrapper, "total_rows", 0) or 0) if wrapper else 0,
                "candidate_count_before_minimum": int(
                    getattr(wrapper, "candidate_count", 0) or 0
                ) if wrapper else 0,
                "visible_count": int(getattr(wrapper, "total_rows", 0) or 0) if wrapper else 0,
                "highest_matching_play_count": getattr(
                    wrapper, "highest_matching_play_count", None
                ) if wrapper else None,
                "combination_ranges": combination_ranges,
                "combination_card_options": list(getattr(wrapper, "card_options", None) or []) if wrapper else [],
                "combination_endgame_options": list(getattr(wrapper, "endgame_options", None) or []) if wrapper else [],
                "combination_action_card_options": list(getattr(wrapper, "action_card_options", None) or []) if wrapper else [],
            }
        else:
            result_rows = results
            schema_field_names = {field.name for field in results.schema}
        for row in result_rows:
            if combinations_view == COMBINATIONS_VIEW_CARD_ENDGAME:
                item = {
                    "card_name": row.card_name,
                    "card_type": row.card_type,
                    "delta_card": row.delta_card,
                    "endgame_name": row.endgame_name,
                    "delta_endgame": row.delta_endgame,
                    "delta_combined": row.delta_combined,
                    "delta_actual": row.delta_actual,
                    "interaction": row.interaction,
                    "avg_elo": row.avg_elo,
                    "n_played": row.n_played,
                }
                _attach_ci95(item, row, schema_field_names, "delta_actual")
            elif combinations_view == COMBINATIONS_VIEW_CARD_ACTION_CARD:
                item = {
                    "card_name": row.card_name,
                    "card_type": row.card_type,
                    "delta_card": row.delta_card,
                    "action_card_key": row.action_card_key,
                    "action_card_name": row.action_card_name,
                    "action_card_type": row.action_card_type,
                    "action_card_number": row.action_card_number,
                    "delta_action": row.delta_action,
                    "delta_combined": row.delta_combined,
                    "delta_actual": row.delta_actual,
                    "interaction": row.interaction,
                    "avg_elo": row.avg_elo,
                    "n_played": row.n_played,
                    "pair_type": row.pair_type,
                }
                _attach_ci95(item, row, schema_field_names, "delta_actual")
            elif combinations_view == COMBINATIONS_VIEW_CARD_MAP:
                item = {
                    "card_name": row.card_name,
                    "card_type": row.card_type,
                    "map_name": row.map_name,
                    "delta_general": row.delta_general,
                    "delta_map": row.delta_map,
                    "interaction": row.interaction,
                    "avg_elo": row.avg_elo,
                    "n_played": row.n_played,
                }
                _attach_ci95(item, row, schema_field_names, "delta_map")
            elif combinations_view == COMBINATIONS_VIEW_CARD_ROUND:
                item = {
                    "card_name": row.card_name,
                    "card_type": row.card_type,
                    "round_name": row.round_name,
                    "delta_general": row.delta_general,
                    "delta_round": row.delta_round,
                    "interaction": row.interaction,
                    "avg_elo": row.avg_elo,
                    "n_played": row.n_played,
                }
                _attach_ci95(item, row, schema_field_names, "delta_round")
            else:
                item = {
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
                }
                _attach_ci95(item, row, schema_field_names, "delta_actual")
            if combination_paged:
                item["global_rank"] = getattr(row, "global_rank", None)
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
        if combination_meta is not None:
            timing["combination_meta"] = combination_meta
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
            _attach_ci95(item, row, schema_field_names, "delta_played")
            _attach_ci95(item, row, schema_field_names, "delta_in_hand")
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


def _players_component_cache_blob_name(
    component,
    data_version,
    is_mw,
    selected_maps,
    opponent_elo_min,
    opponent_elo_max,
    date_from,
    date_to,
    player_identity=None,
    last_x_games=None,
    arena_only=False,
    arena_seasons=None,
    tournament_only=False,
    starting_positions=None,
):
    cache_key = {
        "version": FILTER_CACHE_VERSION,
        "data_version": data_version,
        "component": component,
        "is_mw": int(is_mw),
        "maps": sorted(selected_maps),
        "opponent_elo_min": opponent_elo_min,
        "opponent_elo_max": opponent_elo_max,
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "player_identity": (
            player_identity if component == "selected" else None
        ),
        "last_x_games": last_x_games if component == "selected" else None,
        "arena_only": bool(arena_only),
        "arena_seasons": sorted(arena_seasons or []) if arena_only else [],
        "tournament_only": bool(tournament_only),
        "starting_positions": sorted(starting_positions or []),
        "rollup_schema": 6,
    }
    digest = hashlib.sha256(
        json.dumps(cache_key, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:32]
    return f"{CACHE_PREFIX}/filters/players-components/{digest}.json"


def _is_default_players_filter_scope(
    selected_maps,
    opponent_elo_min,
    opponent_elo_max,
    date_from,
    date_to,
    arena_only=False,
    tournament_only=False,
    starting_positions=None,
):
    return (
        set(selected_maps) == set(ALL_KNOWN_MAPS)
        and opponent_elo_min == 0
        and opponent_elo_max is None
        and date_from is None
        and date_to is None
        and not arena_only
        and not tournament_only
        and not starting_positions
    )


def _merge_players_component_rows(baseline_rows, selected_rows):
    baseline_by_order = {int(row.get("sort_order") or 0): row for row in baseline_rows or []}
    selected_by_order = {int(row.get("sort_order") or 0): row for row in selected_rows or []}
    merged = []
    for definition in _players_metric_definitions():
        sort_order = definition[1]
        base = baseline_by_order.get(sort_order, {})
        selected = selected_by_order.get(sort_order, {})
        row = {
            "sort_order": sort_order,
            "metric": base.get("metric", selected.get("metric", definition[2])),
            "tooltip": base.get("tooltip", selected.get("tooltip", definition[3])),
            "is_default": bool(base.get("is_default", selected.get("is_default", definition[4]))),
            "format": base.get("format", selected.get("format", definition[5])),
            "lower_is_better": bool(base.get("lower_is_better", selected.get("lower_is_better", definition[6]))),
            "player": selected.get("player"),
            "count_player": int(selected.get("count_player") or 0),
            "tooltip_player": selected.get("tooltip_player"),
            "account_counts": list(selected.get("account_counts") or []),
        }
        for population in ("all", "winners", "experts", "masters"):
            row[population] = base.get(population)
            row[f"count_{population}"] = int(base.get(f"count_{population}") or 0)
            row[f"tooltip_{population}"] = base.get(f"tooltip_{population}")
        merged.append(row)
    return merged


def _query_default_player_component(is_mw, player_identity):
    """Read one merged identity's unfiltered aggregate instead of scanning games."""
    started_at = time.perf_counter()
    client_started = time.perf_counter()
    client = bigquery.Client(project=BIGQUERY_JOB_PROJECT)
    client_ms = _ms_since(client_started)
    job = client.query(
        f"SELECT * FROM `{PREPARED_PLAYERS_DEFAULT_TABLE}` "
        "WHERE is_mw = @is_mw AND player_identity = @player_identity LIMIT 1",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("is_mw", "INT64", int(is_mw)),
            bigquery.ScalarQueryParameter(
                "player_identity", "STRING", player_identity
            ),
        ]),
        location=BIGQUERY_LOCATION,
    )
    result = list(job.result())
    aggregate = result[0] if result else None
    account_counts = _account_counts_payload(
        aggregate.account_counts if aggregate is not None else []
    )
    money_fields = _players_money_fields()
    rows = []
    for key, sort_order, label, tooltip, is_default, value_format, lower_is_better in _players_metric_definitions():
        tooltip_value = None
        if aggregate is None:
            value = None
            count = 0
        elif key in money_fields:
            tooltip_value = getattr(aggregate, f"{key}_raw", None)
            denominator = sum(
                float(getattr(aggregate, f"{money_key}_raw", 0) or 0)
                for money_key in money_fields
            )
            value = 100 * float(tooltip_value) / denominator if tooltip_value is not None and denominator else None
            count = int(aggregate.game_count or 0)
        else:
            value = getattr(aggregate, key, None)
            count = int(aggregate.game_count or 0)
        rows.append({
            "sort_order": sort_order, "metric": label, "tooltip": tooltip,
            "is_default": bool(is_default), "format": value_format,
            "lower_is_better": bool(lower_is_better), "player": value,
            "count_player": count, "tooltip_player": tooltip_value,
            "account_counts": account_counts,
        })
    timing = {
        "client_ms": client_ms, "submit_ms": 0, "query_wait_ms": _ms_since(started_at),
        "iteration_ms": 0, "job_id": job.job_id, "job_created": _dt_iso(job.created),
        "job_started": _dt_iso(job.started), "job_ended": _dt_iso(job.ended),
        "job_cache_hit": job.cache_hit, "job_total_bytes_processed": job.total_bytes_processed,
        "job_total_slot_ms": job.slot_millis,
    }
    return rows, timing


def _query_default_players_comparison(is_mw, players, player_identities):
    """Read up to five unfiltered merged identities in one small lookup."""
    started_at = time.perf_counter()
    client = bigquery.Client(project=BIGQUERY_JOB_PROJECT)
    job = client.query(
        f"SELECT * FROM `{PREPARED_PLAYERS_DEFAULT_TABLE}` "
        "WHERE is_mw = @is_mw "
        "AND player_identity IN UNNEST(@player_identities)",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("is_mw", "INT64", int(is_mw)),
            bigquery.ArrayQueryParameter(
                "player_identities", "STRING", player_identities
            ),
        ]),
        location=BIGQUERY_LOCATION,
    )
    aggregates = {row.player_identity: row for row in job.result()}
    money_fields = _players_money_fields()
    rows = []
    for key, sort_order, label, tooltip, is_default, value_format, lower_is_better in _players_metric_definitions():
        values = []
        for player, player_identity in zip(players, player_identities):
            aggregate = aggregates.get(player_identity)
            tooltip_value = None
            value = None
            count = int(aggregate.game_count or 0) if aggregate else 0
            if aggregate and key in money_fields:
                tooltip_value = getattr(aggregate, f"{key}_raw", None)
                denominator = sum(float(getattr(aggregate, f"{money_key}_raw", 0) or 0) for money_key in money_fields)
                value = 100 * float(tooltip_value) / denominator if tooltip_value is not None and denominator else None
            elif aggregate:
                value = getattr(aggregate, key, None)
            values.append({
                "player": player,
                "player_identity": player_identity,
                "value": value,
                "tooltip_value": tooltip_value,
                "game_count": count,
                "account_counts": _account_counts_payload(
                    aggregate.account_counts if aggregate else []
                ),
            })
        rows.append({
            "sort_order": sort_order, "metric": label, "tooltip": tooltip,
            "is_default": bool(is_default), "format": value_format,
            "lower_is_better": bool(lower_is_better), "values": values,
        })
    timing = {
        "client_ms": 0, "submit_ms": 0, "query_wait_ms": _ms_since(started_at),
        "iteration_ms": 0, "job_id": job.job_id, "job_created": _dt_iso(job.created),
        "job_started": _dt_iso(job.started), "job_ended": _dt_iso(job.ended),
        "job_cache_hit": job.cache_hit, "job_total_bytes_processed": job.total_bytes_processed,
        "job_total_slot_ms": job.slot_millis,
    }
    return rows, timing


def _query_players_components(query_args, query_kwargs, data_version, use_component_cache=True):
    """Resolve reusable baseline and selected-player components independently."""
    is_mw = query_args[0]
    selected_maps = query_args[1]
    opponent_elo_min = query_args[8]
    opponent_elo_max = query_args[9]
    date_from = query_args[10]
    date_to = query_args[11]
    player_identity = query_kwargs.get("players_identity")
    last_x_games = query_kwargs.get("last_x_games")
    arena_only = bool(query_kwargs.get("players_arena_only"))
    arena_seasons = query_kwargs.get("players_arena_seasons") or []
    tournament_only = bool(query_kwargs.get("tournament_only"))
    starting_positions = query_kwargs.get("starting_positions") or []
    baseline_rows = None
    selected_rows = None
    component_timings = {}

    default_scope = _is_default_players_filter_scope(
        selected_maps, opponent_elo_min, opponent_elo_max, date_from, date_to,
        arena_only, tournament_only, starting_positions,
    )
    if default_scope:
        snapshot = _read_cached_snapshot(
            is_mw, STATS_PAGE_PLAYERS, players_view=PLAYERS_VIEW_GENERAL
        )
        if snapshot:
            baseline_rows = snapshot.get("data") or []

    baseline_blob = _players_component_cache_blob_name(
        "baseline", data_version, is_mw, selected_maps,
        opponent_elo_min, opponent_elo_max, date_from, date_to,
        arena_only=arena_only, arena_seasons=arena_seasons,
        tournament_only=tournament_only,
        starting_positions=starting_positions,
    )
    selected_blob = _players_component_cache_blob_name(
        "selected", data_version, is_mw, selected_maps,
        opponent_elo_min, opponent_elo_max, date_from, date_to,
        player_identity, last_x_games, arena_only, arena_seasons,
        tournament_only, starting_positions,
    ) if player_identity else None
    cache_reads = {}
    if use_component_cache and baseline_rows is None:
        cache_reads["baseline"] = (
            baseline_blob, "players_baseline_hit"
        )
    if use_component_cache and selected_blob:
        cache_reads["selected"] = (
            selected_blob, "players_selected_hit"
        )
    if cache_reads:
        with ThreadPoolExecutor(max_workers=len(cache_reads)) as executor:
            futures = {
                component: executor.submit(
                    _read_cache_blob, blob_name, cache_status
                )
                for component, (blob_name, cache_status) in cache_reads.items()
            }
            for component, future in futures.items():
                cached = future.result()
                if not cached:
                    continue
                if component == "baseline":
                    baseline_rows = cached.get("data") or []
                else:
                    selected_rows = cached.get("data") or []

    missing = []
    if baseline_rows is None:
        missing.append("baseline")
    if player_identity and selected_rows is None:
        missing.append("selected")

    def run_component(component):
        if component == "selected" and default_scope and not last_x_games and not arena_only and not tournament_only:
            return _query_default_player_component(is_mw, player_identity)
        kwargs = dict(query_kwargs)
        kwargs["players_component"] = component
        if component == "baseline":
            kwargs["players_player"] = None
            kwargs["last_x_games"] = None
        return _query_card_stats(*query_args, **kwargs)

    if missing:
        with ThreadPoolExecutor(max_workers=len(missing)) as executor:
            futures = {component: executor.submit(run_component, component) for component in missing}
            for component, future in futures.items():
                rows, timing = future.result()
                component_timings[component] = timing
                if component == "baseline":
                    baseline_rows = rows
                else:
                    selected_rows = rows
        cache_writes = {}
        if use_component_cache and "baseline" in component_timings:
            cache_writes["baseline"] = (
                baseline_blob,
                {"status": "ok", "data": baseline_rows or []},
                "players_baseline_refreshed",
            )
        if (
            use_component_cache
            and selected_blob
            and "selected" in component_timings
        ):
            cache_writes["selected"] = (
                selected_blob,
                {"status": "ok", "data": selected_rows or []},
                "players_selected_refreshed",
            )
        if cache_writes:
            with ThreadPoolExecutor(max_workers=len(cache_writes)) as executor:
                futures = [
                    executor.submit(_write_cache_blob, *arguments)
                    for arguments in cache_writes.values()
                ]
                for future in futures:
                    future.result()

    rows = _merge_players_component_rows(baseline_rows or [], selected_rows or [])
    timings = list(component_timings.values())
    timing = {
        "client_ms": sum(item.get("client_ms") or 0 for item in timings),
        "submit_ms": sum(item.get("submit_ms") or 0 for item in timings),
        "query_wait_ms": max([item.get("query_wait_ms") or 0 for item in timings] or [0]),
        "iteration_ms": sum(item.get("iteration_ms") or 0 for item in timings),
        "job_id": ",".join(str(item.get("job_id")) for item in timings if item.get("job_id")) or None,
        "job_created": None,
        "job_started": None,
        "job_ended": None,
        "job_cache_hit": all(item.get("job_cache_hit") for item in timings) if timings else True,
        "job_total_bytes_processed": sum(item.get("job_total_bytes_processed") or 0 for item in timings),
        "job_total_slot_ms": sum(item.get("job_total_slot_ms") or 0 for item in timings),
        "players_components": component_timings,
    }
    return rows, timing


def _decode_card_card_compact_rows(compact_rows):
    """Expand the internal keyless Card + Card scope representation."""
    fields = (
        "card_1", "type_1", "delta_1", "card_2", "type_2", "delta_2",
        "delta_combined", "delta_actual", "delta_actual_ci_mean",
        "delta_actual_ci_sd", "delta_actual_ci_n", "interaction", "avg_elo",
        "n_played", "pair_type",
    )
    float_fields = {
        "delta_1", "delta_2", "delta_combined", "delta_actual",
        "delta_actual_ci_mean", "delta_actual_ci_sd", "interaction", "avg_elo",
    }
    int_fields = {"delta_actual_ci_n", "n_played"}
    rows = []
    for line in (compact_rows or "").splitlines():
        values = json.loads(line)
        row = dict(zip(fields, values))
        for field in float_fields:
            value = row.get(field)
            row[field] = float(value) if value not in (None, "") else None
        for field in int_fields:
            value = row.get(field)
            row[field] = int(value) if value not in (None, "") else 0
        rows.append(row)
    return rows


def _card_card_scope_cache_blob_name(query_args, query_kwargs, data_version):
    """Cache the complete filtered pair aggregate independently of table controls."""
    scope = {
        "schema": 6,
        "data_version": data_version,
        "is_mw": query_args[0],
        "maps": sorted(query_args[1]),
        "rounds": sorted(query_args[3]),
        "round_filter_active": bool(query_args[4]),
        "player_elo_min": query_args[6],
        "player_elo_max": query_args[7],
        "opponent_elo_min": query_args[8],
        "opponent_elo_max": query_args[9],
        "date_from": query_args[10].isoformat() if query_args[10] else None,
        "date_to": query_args[11].isoformat() if query_args[11] else None,
        "completed_only": query_args[12],
        "arena_only": bool(query_kwargs.get("arena_only")),
        "tournament_only": bool(query_kwargs.get("tournament_only")),
        "starting_positions": sorted(query_kwargs.get("starting_positions") or []),
    }
    digest = hashlib.sha256(
        json.dumps(scope, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:32]
    return f"{CACHE_PREFIX}/filters/card-card-scopes/{digest}.json"


def _materialize_card_card_scope(blob_name, query_args, query_kwargs):
    """Populate a reusable full scope after the requested page has returned."""
    try:
        scope_kwargs = dict(query_kwargs)
        scope_kwargs["combination_paged"] = False
        scope_kwargs["combination_min_plays"] = 0
        scope_kwargs["combination_scope_compact"] = True
        rows, timing = _query_card_stats(*query_args, **scope_kwargs)
        compact_rows = timing.pop("combination_scope_compact_rows", "")
        _write_cache_blob(
            blob_name,
            (
                {"status": "ok", "compact_rows": compact_rows}
                if compact_rows else {"status": "ok", "data": rows}
            ),
            "card_card_scope_refreshed",
            compresslevel=1,
        )
    except Exception:
        logging.exception("Failed to materialize Card + Card scope %s", blob_name)
    finally:
        with _BACKGROUND_SCOPE_LOCK:
            _BACKGROUND_SCOPE_KEYS.discard(blob_name)


def _enqueue_card_card_scope(blob_name, query_args, query_kwargs):
    with _BACKGROUND_SCOPE_LOCK:
        if blob_name in _BACKGROUND_SCOPE_KEYS:
            return False
        _BACKGROUND_SCOPE_KEYS.add(blob_name)
    _BACKGROUND_EXECUTOR.submit(
        _materialize_card_card_scope, blob_name, query_args, query_kwargs
    )
    return True


def _query_cached_card_card_page(query_args, query_kwargs, data_version):
    """Page/sort/minimum Card + Card from one reusable filtered aggregate.

    The first scope request queries the compact daily moment table. Subsequent
    Minimum plays, sort, and page changes read this cache and never start a
    BigQuery job.
    """
    started_at = time.perf_counter()
    blob_name = _card_card_scope_cache_blob_name(
        query_args, query_kwargs, data_version
    )
    cached = _read_cache_blob(blob_name, "card_card_scope_hit")
    if cached and (
        isinstance(cached.get("data"), list)
        or isinstance(cached.get("compact_rows"), str)
    ):
        base_rows = (
            cached["data"]
            if isinstance(cached.get("data"), list)
            else _decode_card_card_compact_rows(cached["compact_rows"])
        )
        base_timing = {
            "query_wait_ms": 0,
            "job_id": None,
            "job_cache_hit": True,
            "job_total_bytes_processed": 0,
            "job_total_slot_ms": 0,
        }
        cache_status = "scope_hit"
    else:
        # The first request must not wait for or serialize the complete scope.
        # Return the narrow BigQuery page immediately and warm that scope in
        # the background for later Minimum/sort/page changes.
        page_kwargs = dict(query_kwargs)
        page_kwargs["combination_paged"] = True
        page_rows, page_timing = _query_card_stats(*query_args, **page_kwargs)
        combination_meta = page_timing.get("combination_meta") or {}
        queued = _enqueue_card_card_scope(blob_name, query_args, query_kwargs)
        combination_meta["combination_scope_cache"] = (
            "scope_warming" if queued else "scope_warming_inflight"
        )
        page_timing["combination_meta"] = combination_meta
        page_timing["scope_total_ms"] = _ms_since(started_at)
        return page_rows, page_timing

    pair_types = set(query_kwargs.get("combination_pair_types") or [])
    primary = query_kwargs.get("combination_primary") or ""
    secondary = query_kwargs.get("combination_secondary") or ""

    def visible(row):
        if row.get("pair_type") not in pair_types:
            return False
        card_1 = row.get("card_1")
        card_2 = row.get("card_2")
        if not primary and not secondary:
            return True
        if primary and not secondary:
            return card_1 == primary or card_2 == primary
        if secondary and not primary:
            return card_1 == secondary or card_2 == secondary
        return (
            (card_1 == primary and card_2 == secondary)
            or (card_1 == secondary and card_2 == primary)
        )

    candidates = [row for row in base_rows if visible(row)]
    minimum = int(query_kwargs.get("combination_min_plays") or 0)

    # Preserve the pair's rank in the complete minimum-qualified scope even
    # when a card/type header filter narrows the visible table.
    global_universe = [
        row for row in base_rows if int(row.get("n_played") or 0) >= minimum
    ]
    global_universe.sort(key=lambda row: (
        -(float(row.get("interaction")) if row.get("interaction") is not None else float("-inf")),
        -int(row.get("n_played") or 0),
        str(row.get("card_1") or ""),
        str(row.get("card_2") or ""),
    ))
    global_ranks = {
        (row.get("card_1"), row.get("card_2")): rank
        for rank, row in enumerate(global_universe, 1)
    }
    visible_rows = [
        dict(row, global_rank=global_ranks.get((row.get("card_1"), row.get("card_2"))))
        for row in candidates
        if int(row.get("n_played") or 0) >= minimum
    ]

    sort_field = query_kwargs.get("combination_sort") or "interaction"
    direction = query_kwargs.get("combination_sort_direction") or "desc"

    def projected_cards(row):
        card_1, card_2 = row.get("card_1"), row.get("card_2")
        if (
            (primary and card_2 == primary)
            or (not primary and secondary and card_1 == secondary)
        ):
            return card_2, card_1
        return card_1, card_2

    def sort_value(row):
        if sort_field == "card_1":
            return projected_cards(row)[0]
        if sort_field == "card_2":
            return projected_cards(row)[1]
        return row.get(sort_field)

    valid_rows = [row for row in visible_rows if sort_value(row) is not None]
    missing_rows = [row for row in visible_rows if sort_value(row) is None]
    valid_rows.sort(
        key=lambda row: (
            sort_value(row),
            projected_cards(row)[0] or "",
            projected_cards(row)[1] or "",
            row.get("pair_type") or "",
        ),
        reverse=(direction != "asc"),
    )
    visible_rows = valid_rows + sorted(
        missing_rows,
        key=lambda row: (
            projected_cards(row)[0] or "",
            projected_cards(row)[1] or "",
            row.get("pair_type") or "",
        ),
    )
    page = int(query_kwargs.get("combination_page") or 1)
    page_size = int(query_kwargs.get("combination_page_size") or COMBINATION_PAGE_SIZE_DEFAULT)
    offset = max(0, (page - 1) * page_size)
    page_rows = visible_rows[offset:offset + page_size]
    ranges = _combination_ranges(base_rows, COMBINATIONS_VIEW_CARD_CARD)
    meta = {
        "combination_paged": True,
        "page": page,
        "page_size": page_size,
        "total_rows": len(visible_rows),
        "candidate_count_before_minimum": len(candidates),
        "visible_count": len(visible_rows),
        "highest_matching_play_count": max(
            [int(row.get("n_played") or 0) for row in candidates] or [0]
        ),
        "combination_ranges": ranges,
        "combination_card_options": [],
        "combination_endgame_options": [],
        "combination_scope_cache": cache_status,
    }
    timing = dict(base_timing)
    timing["combination_meta"] = meta
    timing["scope_total_ms"] = _ms_since(started_at)
    return page_rows, timing


def _default_card_card_scope_request(is_mw):
    query_args = (
        int(is_mw),
        list(VALID_MAPS),
        list(DEFAULT_CARD_TYPES),
        [],
        False,
        STATS_PAGE_COMBINATIONS,
        300,
        None,
        300,
        None,
        DEFAULT_DATE_FROM,
        None,
        None,
    )
    query_kwargs = {
        "combinations_view": COMBINATIONS_VIEW_CARD_CARD,
        "combination_paged": True,
        "combination_page": COMBINATION_PAGE_DEFAULT,
        "combination_page_size": COMBINATION_PAGE_SIZE_DEFAULT,
        "combination_min_plays": COMBINATION_DEFAULT_MIN_PLAYS,
        "combination_sort": "interaction",
        "combination_sort_direction": "desc",
        "combination_pair_types": list(COMBINATION_PAIR_TYPES),
        "combination_card_types": list(DEFAULT_CARD_TYPES),
        "combination_primary": "",
        "combination_secondary": "",
        "combination_header_maps": list(VALID_MAPS),
        "combination_header_rounds": ["1", "2", "3", "4", "5", "6+"],
        "arena_only": False,
        "tournament_only": False,
        "use_query_cache": True,
    }
    return query_args, query_kwargs


def _warm_default_card_card_scope(is_mw, data_version):
    """Synchronously build one default scope from low-priority batch SQL."""
    started_at = time.perf_counter()
    query_args, query_kwargs = _default_card_card_scope_request(is_mw)
    blob_name = _card_card_scope_cache_blob_name(
        query_args, query_kwargs, data_version
    )
    cached = _read_cache_blob(blob_name, "card_card_scope_warm_check")
    if cached and (
        isinstance(cached.get("data"), list)
        or isinstance(cached.get("compact_rows"), str)
    ):
        return {
            "status": "ok",
            "is_mw": int(is_mw),
            "cache_status": "already_warm",
            "total_ms": _ms_since(started_at),
        }

    scope_kwargs = dict(query_kwargs)
    scope_kwargs.update({
        "combination_paged": False,
        "combination_min_plays": 0,
        "combination_scope_compact": True,
        "query_priority": bigquery.QueryPriority.BATCH,
    })
    _rows, timing = _query_card_stats(*query_args, **scope_kwargs)
    compact_rows = timing.pop("combination_scope_compact_rows", "")
    cache_ok = _write_cache_blob(
        blob_name,
        (
            {"status": "ok", "compact_rows": compact_rows}
            if compact_rows else {"status": "ok", "data": _rows}
        ),
        "card_card_scope_scheduled_warm",
        compresslevel=1,
    )
    return {
        "status": "ok" if cache_ok else "error",
        "is_mw": int(is_mw),
        "cache_status": "warmed" if cache_ok else "cache_write_failed",
        "total_ms": _ms_since(started_at),
        "job_id": timing.get("job_id"),
        "job_total_bytes_processed": timing.get("job_total_bytes_processed"),
        "job_total_slot_ms": timing.get("job_total_slot_ms"),
    }


def _warm_card_card_default_scopes():
    """Warm today's MW/Base scopes without participating in pack publication."""
    data_version = _read_data_version()
    try:
        version_date = datetime.fromisoformat(
            str(data_version).replace("Z", "+00:00")
        ).date()
    except (TypeError, ValueError):
        version_date = None
    if version_date != datetime.now(timezone.utc).date():
        return {
            "status": "retry",
            "message": "Today's data version has not been published yet",
            "data_version": data_version,
        }

    started_at = time.perf_counter()
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            dataset: executor.submit(
                _warm_default_card_card_scope, dataset, data_version
            )
            for dataset in (1, 0)
        }
        results = [futures[dataset].result() for dataset in (1, 0)]
    return {
        "status": (
            "ok" if all(item.get("status") == "ok" for item in results)
            else "error"
        ),
        "data_version": data_version,
        "total_ms": _ms_since(started_at),
        "datasets": results,
    }


def _query_hexes_both(*args, **kwargs):
    """Return collapsed and exact Hexes rows in one API request."""
    collapsed_kwargs = dict(kwargs)
    collapsed_kwargs["hexes_expanded"] = False
    expanded_kwargs = dict(kwargs)
    expanded_kwargs["hexes_expanded"] = True
    with ThreadPoolExecutor(max_workers=2) as executor:
        collapsed_future = executor.submit(
            _query_card_stats, *args, **collapsed_kwargs
        )
        expanded_future = executor.submit(
            _query_card_stats, *args, **expanded_kwargs
        )
        collapsed_rows, collapsed_timing = collapsed_future.result()
        expanded_rows, expanded_timing = expanded_future.result()
    combined_timing = dict(collapsed_timing)
    combined_timing["expanded_query_wait_ms"] = expanded_timing.get("query_wait_ms")
    combined_timing["expanded_job_id"] = expanded_timing.get("job_id")
    combined_timing["expanded_job_total_bytes_processed"] = expanded_timing.get(
        "job_total_bytes_processed"
    )
    combined_timing["expanded_job_total_slot_ms"] = expanded_timing.get("job_total_slot_ms")
    return collapsed_rows, expanded_rows, combined_timing


def _query_scoring_both(*args, **kwargs):
    """Return collapsed and exact Scoring buckets in one frontend request."""
    collapsed_kwargs = dict(kwargs)
    collapsed_kwargs["scoring_expanded"] = False
    expanded_kwargs = dict(kwargs)
    expanded_kwargs["scoring_expanded"] = True
    scoring_view = collapsed_kwargs.get("scoring_view", SCORING_VIEW_FINAL_SCORE)
    if scoring_view == SCORING_VIEW_REPUTATION:
        collapsed_rows, collapsed_timing = _query_card_stats(
            *args, **collapsed_kwargs
        )
        return collapsed_rows, list(collapsed_rows), collapsed_timing
    with ThreadPoolExecutor(max_workers=2) as executor:
        collapsed_future = executor.submit(
            _query_card_stats, *args, **collapsed_kwargs
        )
        expanded_future = executor.submit(
            _query_card_stats, *args, **expanded_kwargs
        )
        collapsed_rows, collapsed_timing = collapsed_future.result()
        expanded_rows, expanded_timing = expanded_future.result()
    combined_timing = dict(collapsed_timing)
    combined_timing["expanded_query_wait_ms"] = expanded_timing.get("query_wait_ms")
    combined_timing["expanded_job_id"] = expanded_timing.get("job_id")
    combined_timing["expanded_job_total_bytes_processed"] = expanded_timing.get(
        "job_total_bytes_processed"
    )
    combined_timing["expanded_job_total_slot_ms"] = expanded_timing.get("job_total_slot_ms")
    return collapsed_rows, expanded_rows, combined_timing


def _combination_ranges(rows, combinations_view):
    fields = {
        COMBINATIONS_VIEW_CARD_CARD: ["avg_elo", "interaction", "delta_1", "delta_2", "delta_combined", "delta_actual"],
        COMBINATIONS_VIEW_CARD_MAP: ["avg_elo", "interaction", "delta_general", "delta_map"],
        COMBINATIONS_VIEW_CARD_ROUND: ["avg_elo", "interaction", "delta_general", "delta_round"],
        COMBINATIONS_VIEW_CARD_ENDGAME: ["avg_elo", "interaction", "delta_card", "delta_endgame", "delta_combined", "delta_actual"],
        COMBINATIONS_VIEW_CARD_ACTION_CARD: ["avg_elo", "interaction", "delta_card", "delta_action", "delta_combined", "delta_actual"],
    }[combinations_view]
    result = {}
    for field in fields:
        values = []
        for row in rows:
            try:
                value = float(row.get(field))
            except (TypeError, ValueError):
                continue
            if math.isfinite(value):
                values.append(value)
        result[field] = {
            "min": min(values) if values else None,
            "max": max(values) if values else None,
        }
    return result


def _synergy_ci_request_row(stats_page, view, row):
    if stats_page == STATS_PAGE_MW_ACTION_CARDS:
        return {
            "card_1_key": row.get("card_1_key"),
            "card_2_key": row.get("card_2_key"),
        }
    if view == COMBINATIONS_VIEW_CARD_CARD:
        return {"card_1": row.get("card_1"), "card_2": row.get("card_2")}
    if view == COMBINATIONS_VIEW_CARD_MAP:
        return {"card_name": row.get("card_name"), "map_name": row.get("map_name")}
    if view == COMBINATIONS_VIEW_CARD_ROUND:
        return {"card_name": row.get("card_name"), "round_name": row.get("round_name")}
    if view == COMBINATIONS_VIEW_CARD_ENDGAME:
        return {
            "card_name": row.get("card_name"),
            "endgame_name": row.get("endgame_name"),
        }
    if view == COMBINATIONS_VIEW_CARD_ACTION_CARD:
        return {
            "card_name": row.get("card_name"),
            "action_card_key": row.get("action_card_key"),
        }
    raise ValueError("Unsupported Synergy snapshot view")


def _attach_snapshot_synergy_cis(
    rows,
    data_version,
    stats_page,
    view,
    is_mw,
    selected_maps,
    selected_rounds,
    player_elo_min,
    player_elo_max,
    opponent_elo_min,
    opponent_elo_max,
    date_from,
    date_to,
    completed_only,
    new_batch_budget=6,
):
    """Attach complete default-scope Synergy CIs before atomic publication."""
    if not rows:
        return rows
    requests = [_synergy_ci_request_row(stats_page, view, row) for row in rows]
    # Snapshot populations can contain many thousands of combinations. Keep
    # the existing views at the same proven size as a visible-page request:
    # large Card + Card batches have an expensive join fan-out and can prevent
    # useful checkpoints before the Cloud Run request deadline. Card + Action
    # Card is backed by a compact, key-addressable MW derivative and safely uses
    # 500-row batches. Larger all-snapshot batches exceed BigQuery's on-demand
    # CPU-per-byte limit, while 100-row batches repeat the same scan excessively.
    ci_by_key = {}
    snapshot_batch_size = (
        500
        if stats_page == "combinations" and view == COMBINATIONS_VIEW_CARD_ACTION_CARD
        else 100
    )
    new_batches = 0
    for offset in range(0, len(requests), snapshot_batch_size):
        payload = _load_synergy_ci(
            data_version,
            stats_page,
            view,
            requests[offset:offset + snapshot_batch_size],
            is_mw,
            selected_maps,
            selected_rounds,
            player_elo_min,
            player_elo_max,
            opponent_elo_min,
            opponent_elo_max,
            date_from,
            date_to,
            completed_only,
            # The cache key includes the current data version and exact batch
            # row keys, so a hit can only belong to this publication. Reusing
            # completed batches makes the maintenance operation restartable
            # across the Cloud Run request deadline without mixing versions.
            force_refresh=False,
            persist_synchronously=True,
            row_limit=snapshot_batch_size,
        )
        if not payload.get("cache_status"):
            new_batches += 1
        for item in payload.get("data") or []:
            ci_by_key[item.get("row_key")] = item
        if (
            new_batches >= new_batch_budget
            and offset + snapshot_batch_size < len(requests)
        ):
            return None
    for row, request_row in zip(rows, requests):
        key = _synergy_ci_row_key(stats_page, view, request_row)
        ci = ci_by_key.get(key) or {}
        for field, value in ci.items():
            if field == "row_key" or "_ci95_" not in field:
                continue
            row[field] = value
    return rows


def _refresh_default_snapshot_from_prepared(
    is_mw,
    stats_page=STATS_PAGE_CARDS,
    endgames_view=ENDGAMES_VIEW_GENERAL,
    maps_view=MAPS_VIEW_METRICS,
    sponsor_endgames_view=SPONSOR_ENDGAMES_VIEW_CP,
    combinations_view=COMBINATIONS_VIEW_CARD_CARD,
    build_view=BUILD_VIEW_ENCLOSURES,
    predictors_view=PREDICTORS_VIEW_GENERAL,
    actions_view=ACTIONS_VIEW_STARTING_POSITION,
    conservation_view=CONSERVATION_VIEW_PROJECTS,
    scoring_view=SCORING_VIEW_FINAL_SCORE,
    workers_view=WORKERS_VIEW_GENERAL,
    players_view=PLAYERS_VIEW_GENERAL,
    records_view=RECORDS_VIEW_ELO_LEADERBOARD,
    mw_action_cards_view=MW_ACTION_CARDS_VIEW_GENERAL,
    completed_only_override=None,
    cache_blob_override=None,
):
    started_at = time.perf_counter()
    is_home = stats_page == STATS_PAGE_HOME
    snapshot_date_from = None if is_home or stats_page in (STATS_PAGE_PLAYERS, STATS_PAGE_RECORDS) else (
        MAPS_METRICS_DEFAULT_DATE_FROM
        if stats_page == STATS_PAGE_MAPS and maps_view == MAPS_VIEW_METRICS
        else DEFAULT_DATE_FROM
    )
    query_args = (
        int(is_mw),
        ALL_KNOWN_MAPS
        if is_home or stats_page in (STATS_PAGE_PLAYERS, STATS_PAGE_RECORDS)
        else VALID_MAPS,
        DEFAULT_CARD_TYPES,
        [],
        False,
        stats_page,
        0 if is_home else None if stats_page in (STATS_PAGE_PLAYERS, STATS_PAGE_RECORDS) else 300,
        None,
        0 if stats_page in (STATS_PAGE_HOME, STATS_PAGE_PLAYERS) else None if stats_page == STATS_PAGE_RECORDS else 300,
        None,
        snapshot_date_from,
        None,
        completed_only_override,
    )
    query_kwargs = {
        "endgames_view": endgames_view,
        "maps_view": maps_view,
        "sponsor_endgames_view": sponsor_endgames_view,
        "combinations_view": combinations_view,
        "build_view": build_view,
        "predictors_view": predictors_view,
        "actions_view": actions_view,
        "conservation_view": conservation_view,
        "scoring_view": scoring_view,
        "workers_view": workers_view,
        "players_view": players_view,
        "records_view": records_view,
        "mw_action_cards_view": mw_action_cards_view,
        "records_player": None,
        "records_arena_only": False,
        "records_tournament_only": False,
        "players_player": None,
        "players_players": [],
        "last_x_games": None,
        "use_query_cache": False,
    }
    expanded_rows = None
    if stats_page == STATS_PAGE_BUILD and build_view == BUILD_VIEW_HEXES:
        rows, expanded_rows, timing = _query_hexes_both(*query_args, **query_kwargs)
    elif stats_page == STATS_PAGE_SCORING:
        rows, expanded_rows, timing = _query_scoring_both(*query_args, **query_kwargs)
    else:
        rows, timing = _query_card_stats(*query_args, **query_kwargs)
    combination_ranges = None
    if stats_page == STATS_PAGE_COMBINATIONS:
        combination_ranges = _combination_ranges(rows, combinations_view)
        rows = [row for row in rows if int(row.get("n_played") or 0) >= COMBINATION_DEFAULT_MIN_PLAYS]
    if (
        stats_page == STATS_PAGE_COMBINATIONS
        or (
            stats_page == STATS_PAGE_MW_ACTION_CARDS
            and mw_action_cards_view == MW_ACTION_CARDS_VIEW_SYNERGIES
        )
    ):
        ci_view = (
            combinations_view
            if stats_page == STATS_PAGE_COMBINATIONS
            else mw_action_cards_view
        )
        rows = _attach_snapshot_synergy_cis(
            rows,
            _read_data_version(),
            stats_page,
            ci_view,
            int(is_mw),
            list(query_args[1]),
            [],
            query_args[6],
            query_args[7],
            query_args[8],
            query_args[9],
            query_args[10],
            query_args[11],
            query_args[12],
        )
        if rows is None:
            _active_refresh_snapshot_completed()
            return {
                "status": "staged",
                "is_mw": int(is_mw),
                "stats_page": stats_page,
                "view": ci_view,
                "cache_status": "ci_batches_checkpointed",
                "total_ms": _ms_since(started_at),
            }
    payload = {
        "status": "ok",
        "data_version": _read_data_version(),
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
        "build_view": build_view if stats_page == STATS_PAGE_BUILD else None,
        "predictors_view": predictors_view if stats_page == STATS_PAGE_PREDICTORS else None,
        "actions_view": actions_view if stats_page == STATS_PAGE_ACTIONS else None,
        "conservation_view": conservation_view if stats_page == STATS_PAGE_CONSERVATION else None,
        "scoring_view": scoring_view if stats_page == STATS_PAGE_SCORING else None,
        "workers_view": workers_view if stats_page == STATS_PAGE_WORKERS else None,
        "players_view": players_view if stats_page == STATS_PAGE_PLAYERS else None,
        "records_view": records_view if stats_page == STATS_PAGE_RECORDS else None,
        "mw_action_cards_view": (
            mw_action_cards_view if stats_page == STATS_PAGE_MW_ACTION_CARDS else None
        ),
        "maps": (
            ALL_MAPS_FOR_METRICS
            if stats_page in (
                STATS_PAGE_MAPS, STATS_PAGE_BUILD, STATS_PAGE_ACTIONS,
                STATS_PAGE_CONSERVATION, STATS_PAGE_SCORING, STATS_PAGE_WORKERS,
            )
            else None
        ),
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
            else f"{stats_page}_{build_view}_default_snapshot"
            if stats_page == STATS_PAGE_BUILD
            else f"{stats_page}_{predictors_view}_default_snapshot"
            if stats_page == STATS_PAGE_PREDICTORS
            else f"{stats_page}_{actions_view}_default_snapshot"
            if stats_page == STATS_PAGE_ACTIONS
            else f"{stats_page}_{conservation_view}_default_snapshot"
            if stats_page == STATS_PAGE_CONSERVATION
            else f"{stats_page}_{scoring_view}_default_snapshot"
            if stats_page == STATS_PAGE_SCORING
            else f"{stats_page}_{workers_view}_default_snapshot"
            if stats_page == STATS_PAGE_WORKERS
            else f"{stats_page}_{mw_action_cards_view}_default_snapshot"
            if stats_page == STATS_PAGE_MW_ACTION_CARDS
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
    if stats_page == STATS_PAGE_PLAYERS and players_view == PLAYERS_VIEW_GENERAL:
        payload["players_players"] = []
        payload["player_game_count"] = int(rows[0].get("count_player") or 0) if rows else 0
    if combination_ranges is not None:
        payload["combination_snapshot_min_plays"] = COMBINATION_DEFAULT_MIN_PLAYS
        payload["combination_ranges"] = combination_ranges
    if (
        stats_page == STATS_PAGE_COMBINATIONS
        or (
            stats_page == STATS_PAGE_MW_ACTION_CARDS
            and mw_action_cards_view == MW_ACTION_CARDS_VIEW_SYNERGIES
        )
    ):
        # Marks a snapshot whose complete default population passed through
        # the CI attachment loop. Individual rows may still have statistically
        # unavailable intervals, which is a valid completed result.
        payload["synergy_ci_complete"] = True
    if expanded_rows is not None:
        payload["expanded_data"] = expanded_rows
    cache_write_ok = (
        _write_cache_blob(cache_blob_override, payload, "refreshed")
        if cache_blob_override
        else _write_cached_snapshot(
            is_mw, payload, stats_page, endgames_view, maps_view,
            sponsor_endgames_view, combinations_view,
            build_view, predictors_view, actions_view, conservation_view, scoring_view, workers_view, players_view, records_view,
            mw_action_cards_view
        )
    )
    _active_refresh_snapshot_completed()
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
        "build_view": build_view if stats_page == STATS_PAGE_BUILD else None,
        "predictors_view": predictors_view if stats_page == STATS_PAGE_PREDICTORS else None,
        "actions_view": actions_view if stats_page == STATS_PAGE_ACTIONS else None,
        "conservation_view": conservation_view if stats_page == STATS_PAGE_CONSERVATION else None,
        "scoring_view": scoring_view if stats_page == STATS_PAGE_SCORING else None,
        "workers_view": workers_view if stats_page == STATS_PAGE_WORKERS else None,
        "mw_action_cards_view": (
            mw_action_cards_view if stats_page == STATS_PAGE_MW_ACTION_CARDS else None
        ),
        "cache_status": "refreshed" if cache_write_ok else "cache_write_failed",
        "rows": len(rows),
        "total_ms": payload["total_ms"],
        "job_id": timing["job_id"],
        "job_total_bytes_processed": timing["job_total_bytes_processed"],
        "job_total_slot_ms": timing["job_total_slot_ms"],
    }


def _refresh_synergy_ci_snapshots():
    """Stage and atomically promote every complete default Synergy snapshot.

    This intentionally runs after the main daily refresh. The normal refresh
    retains the previous complete Synergy set; this operation only promotes a
    replacement after all default Synergy datasets have pointwise clustered intervals.
    """
    if not CACHE_BUCKET:
        raise RuntimeError("CACHE_BUCKET is required for Synergy CI publication")
    started_at = time.perf_counter()
    data_version = _read_data_version()
    # Stable per-version staging lets scheduler retries reuse completed
    # snapshots and per-batch inference caches after a request deadline.
    stage_id = hashlib.sha256(
        f"{data_version}:synergy-ci-schema-3".encode("utf-8")
    ).hexdigest()[:20]
    completion_marker = (
        f"{CACHE_PREFIX}/staging/synergy-ci/completed/{stage_id}.json"
    )
    completed = _read_cache_blob(completion_marker, "synergy_ci_complete_hit")
    if isinstance(completed, dict) and completed.get("data_version") == data_version:
        return {
            "status": "ok",
            "data_version": data_version,
            "snapshots": [],
            "default_pack": "already_published",
            "total_ms": _ms_since(started_at),
        }
    specs = [
        {
            "stats_page": STATS_PAGE_COMBINATIONS,
            "is_mw": dataset,
            "view": view,
            "canonical": _cache_blob_name(
                dataset, STATS_PAGE_COMBINATIONS, combinations_view=view
            ),
        }
        for dataset in (1, 0)
        for view in (
            COMBINATIONS_VIEW_CARD_CARD,
            COMBINATIONS_VIEW_CARD_MAP,
            COMBINATIONS_VIEW_CARD_ROUND,
            COMBINATIONS_VIEW_CARD_ENDGAME,
        )
    ]
    specs.append({
        "stats_page": STATS_PAGE_COMBINATIONS,
        "is_mw": 1,
        "view": COMBINATIONS_VIEW_CARD_ACTION_CARD,
        "canonical": _cache_blob_name(
            1, STATS_PAGE_COMBINATIONS,
            combinations_view=COMBINATIONS_VIEW_CARD_ACTION_CARD,
        ),
    })
    specs.append({
        "stats_page": STATS_PAGE_MW_ACTION_CARDS,
        "is_mw": 1,
        "view": MW_ACTION_CARDS_VIEW_SYNERGIES,
        "canonical": _cache_blob_name(
            1, STATS_PAGE_MW_ACTION_CARDS,
            mw_action_cards_view=MW_ACTION_CARDS_VIEW_SYNERGIES,
        ),
    })
    for spec in specs:
        suffix = spec["canonical"][len(CACHE_PREFIX):].lstrip("/")
        spec["stage"] = f"{CACHE_PREFIX}/staging/synergy-ci/{stage_id}/{suffix}"
        spec["backup"] = f"{CACHE_PREFIX}/staging/synergy-ci/{stage_id}/backup/{suffix}"

    def build(spec):
        staged = _read_cache_blob(spec["stage"], "synergy_ci_stage_hit")
        if (
            isinstance(staged, dict)
            and staged.get("data_version") == data_version
            and staged.get("synergy_ci_complete") is True
        ):
            return {
                "status": "ok",
                "is_mw": spec["is_mw"],
                "stats_page": spec["stats_page"],
                "view": spec["view"],
                "rows": len(staged.get("data") or []),
                "cache_status": "staged_reused",
            }
        kwargs = {"cache_blob_override": spec["stage"]}
        if spec["stats_page"] == STATS_PAGE_COMBINATIONS:
            kwargs["combinations_view"] = spec["view"]
        else:
            kwargs["mw_action_cards_view"] = spec["view"]
        return _refresh_default_snapshot_from_prepared(
            spec["is_mw"], spec["stats_page"], **kwargs
        )

    def stage_is_complete(spec):
        staged = _read_cache_blob(spec["stage"], "synergy_ci_stage_probe")
        return (
            isinstance(staged, dict)
            and staged.get("data_version") == data_version
            and staged.get("synergy_ci_complete") is True
        )

    missing = [spec for spec in specs if not stage_is_complete(spec)]
    heavy = next((
        spec for spec in missing
        if spec["stats_page"] == STATS_PAGE_COMBINATIONS
        and spec["is_mw"] == 1
        and spec["view"] == COMBINATIONS_VIEW_CARD_CARD
    ), None)
    # Finish every smaller snapshot before giving the high-cardinality MW
    # Card + Card population a request window of its own. Scheduler retries
    # then resume only that snapshot from its durable 100-row CI batches.
    build_specs = [spec for spec in missing if spec is not heavy] if len(missing) > 1 else missing
    # New or low-cardinality products must not wait behind the older, much
    # larger Combos populations. ThreadPoolExecutor starts queued work in list
    # order, so keep Card + Action Card first and its related MW summary next.
    # Every completed 100-row CI batch remains durable across later retries.
    def stage_priority(spec):
        if (
            spec["stats_page"] == STATS_PAGE_COMBINATIONS
            and spec["view"] == COMBINATIONS_VIEW_CARD_ACTION_CARD
        ):
            return 0
        if spec["stats_page"] == STATS_PAGE_MW_ACTION_CARDS:
            return 1
        return 2

    build_specs.sort(key=stage_priority)
    executor = ThreadPoolExecutor(max_workers=min(4, max(1, len(build_specs))))
    try:
        futures = [executor.submit(build, spec) for spec in build_specs]
        results = [future.result() for future in futures]
    finally:
        executor.shutdown(wait=True)
    if any(item.get("status") not in ("ok", "staged") for item in results):
        return {
            "status": "error",
            "data_version": data_version,
            "snapshots": results,
            "message": "At least one staged Synergy CI snapshot failed",
            "total_ms": _ms_since(started_at),
        }

    if any(item.get("status") == "staged" for item in results):
        return {
            "status": "staged",
            "data_version": data_version,
            "snapshots": results,
            "remaining": [
                {
                    "stats_page": spec["stats_page"],
                    "is_mw": spec["is_mw"],
                    "view": spec["view"],
                }
                for spec in specs if not stage_is_complete(spec)
            ],
            "default_pack": "pending_complete_set",
            "total_ms": _ms_since(started_at),
        }

    remaining = [spec for spec in specs if not stage_is_complete(spec)]
    if remaining:
        return {
            "status": "staged",
            "data_version": data_version,
            "snapshots": results,
            "remaining": [
                {
                    "stats_page": spec["stats_page"],
                    "is_mw": spec["is_mw"],
                    "view": spec["view"],
                }
                for spec in remaining
            ],
            "default_pack": "pending_complete_set",
            "total_ms": _ms_since(started_at),
        }

    bucket = storage.Client().bucket(CACHE_BUCKET)
    promoted = []
    try:
        for spec in specs:
            canonical_blob = bucket.blob(spec["canonical"])
            if not canonical_blob.exists():
                raise RuntimeError(
                    f"Cannot back up missing Synergy snapshot {spec['canonical']}"
                )
            bucket.copy_blob(canonical_blob, bucket, spec["backup"])
        for spec in specs:
            stage_blob = bucket.blob(spec["stage"])
            if not stage_blob.exists():
                raise RuntimeError(
                    f"Staged Synergy snapshot is missing: {spec['stage']}"
                )
            bucket.copy_blob(stage_blob, bucket, spec["canonical"])
            promoted.append(spec)
        if not _write_default_snapshot_pack(data_version):
            raise RuntimeError("Could not publish the default pack after Synergy CI promotion")
        if not _write_cache_blob(
            completion_marker,
            {
                "status": "ok",
                "data_version": data_version,
                "published_at": datetime.now(timezone.utc).isoformat(),
            },
            "synergy_ci_complete",
        ):
            # Publication itself is already complete. A missing marker merely
            # causes a later maintenance call to verify/re-promote the same
            # staged version instead of treating a healthy release as failed.
            logging.warning("Could not publish the Synergy CI completion marker")
    except Exception:
        logging.exception("Synergy CI promotion failed; restoring previous snapshots")
        for spec in promoted:
            backup_blob = bucket.blob(spec["backup"])
            if backup_blob.exists():
                bucket.copy_blob(backup_blob, bucket, spec["canonical"])
        raise
    else:
        # Staged objects are deleted only after a successful promotion. On any
        # failure they remain as restart checkpoints for the next retry.
        for spec in specs:
            for name in (spec["stage"], spec["backup"]):
                try:
                    blob = bucket.blob(name)
                    if blob.exists():
                        blob.delete()
                except Exception:
                    logging.warning("Could not remove staging object %s", name)

    return {
        "status": "ok",
        "data_version": data_version,
        "snapshots": results,
        "default_pack": "ok",
        "total_ms": _ms_since(started_at),
    }


def _run_daily_refresh(progress=None):
    started_at = time.perf_counter()
    if progress:
        progress.report(1, "Validating source metadata")
    card_attributes = _load_card_attribute_groups(force_refresh=True)
    # Arena CSV metadata is validated before the prepared table is rebuilt so
    # season assignment and every static Top 100 artifact use one coherent
    # definition during the entire daily publication.
    arena_metadata = _load_arena_metadata(force_refresh=True, publish_manifest=False)
    merge_metadata = _load_merge_players_metadata(force_refresh=True)
    if progress:
        progress.report(4, "Rebuilding prepared data")
    prepared = _refresh_prepared_tables(
        arena_metadata,
        merge_metadata,
        progress_callback=progress.prepared if progress else None,
    )
    data_version = _write_data_version(prepared)
    if progress:
        progress.report(46, "Publishing Arena and player indexes")
    arena_top100 = _refresh_arena_top100_bundle(arena_metadata, data_version)
    players_index_mw = _refresh_player_index_snapshot(1, merge_metadata)
    players_index_base = _refresh_player_index_snapshot(0, merge_metadata)
    if progress:
        progress.report(50, "Generating default snapshots")
    # Card + Card's complete reusable scopes are intentionally warmed by a
    # separate low-priority maintenance job. Snapshot-pack publication must
    # never wait for that optional performance cache.
    # Conservation adds six substantial aggregations. Start three workers now
    # so they overlap the existing sequential snapshot refresh instead of
    # extending an already long maintenance request beyond its timeout.
    conservation_executor = ThreadPoolExecutor(max_workers=3)
    conservation_futures = {
        (dataset, view): conservation_executor.submit(
            _refresh_default_snapshot_from_prepared,
            dataset,
            STATS_PAGE_CONSERVATION,
            conservation_view=view,
        )
        for dataset in (1, 0)
        for view in (
            CONSERVATION_VIEW_PROJECTS,
            CONSERVATION_VIEW_PROJECT_REWARDS,
            CONSERVATION_VIEW_CP_REWARDS,
        )
    }
    scoring_executor = ThreadPoolExecutor(max_workers=4)
    scoring_futures = {
        (dataset, view): scoring_executor.submit(
            _refresh_default_snapshot_from_prepared,
            dataset,
            STATS_PAGE_SCORING,
            scoring_view=view,
        )
        for dataset in (1, 0)
        for view in (
            SCORING_VIEW_FINAL_SCORE,
            SCORING_VIEW_APPEAL,
            SCORING_VIEW_CONSERVATION_POINTS,
            SCORING_VIEW_REPUTATION,
        )
    }
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
    icons_mw = _refresh_default_snapshot_from_prepared(1, STATS_PAGE_ICONS)
    icons_base = _refresh_default_snapshot_from_prepared(0, STATS_PAGE_ICONS)
    build_delta_mw = _refresh_default_snapshot_from_prepared(1, STATS_PAGE_BUILD)
    build_delta_base = _refresh_default_snapshot_from_prepared(0, STATS_PAGE_BUILD)
    build_frequency_mw = _refresh_default_snapshot_from_prepared(
        1, STATS_PAGE_BUILD, completed_only_override=True,
        cache_blob_override=f"{CACHE_PREFIX}/build/enclosures/frequency/default-mw.json",
    )
    build_frequency_base = _refresh_default_snapshot_from_prepared(
        0, STATS_PAGE_BUILD, completed_only_override=True,
        cache_blob_override=f"{CACHE_PREFIX}/build/enclosures/frequency/default-base.json",
    )
    build_hexes_delta_mw = _refresh_default_snapshot_from_prepared(
        1, STATS_PAGE_BUILD, build_view=BUILD_VIEW_HEXES
    )
    build_hexes_delta_base = _refresh_default_snapshot_from_prepared(
        0, STATS_PAGE_BUILD, build_view=BUILD_VIEW_HEXES
    )
    build_hexes_frequency_mw = _refresh_default_snapshot_from_prepared(
        1, STATS_PAGE_BUILD, build_view=BUILD_VIEW_HEXES,
        completed_only_override=True,
        cache_blob_override=f"{CACHE_PREFIX}/build/hexes/frequency/default-mw.json",
    )
    build_hexes_frequency_base = _refresh_default_snapshot_from_prepared(
        0, STATS_PAGE_BUILD, build_view=BUILD_VIEW_HEXES,
        completed_only_override=True,
        cache_blob_override=f"{CACHE_PREFIX}/build/hexes/frequency/default-base.json",
    )
    predictors_general_mw = _refresh_default_snapshot_from_prepared(
        1, STATS_PAGE_PREDICTORS, predictors_view=PREDICTORS_VIEW_GENERAL
    )
    predictors_general_base = _refresh_default_snapshot_from_prepared(
        0, STATS_PAGE_PREDICTORS, predictors_view=PREDICTORS_VIEW_GENERAL
    )
    predictors_icon_mw = _refresh_default_snapshot_from_prepared(
        1, STATS_PAGE_PREDICTORS, predictors_view=PREDICTORS_VIEW_ICON
    )
    predictors_icon_base = _refresh_default_snapshot_from_prepared(
        0, STATS_PAGE_PREDICTORS, predictors_view=PREDICTORS_VIEW_ICON
    )
    predictors_specific_mw = _refresh_default_snapshot_from_prepared(
        1, STATS_PAGE_PREDICTORS, predictors_view=PREDICTORS_VIEW_SPECIFIC
    )
    predictors_specific_base = _refresh_default_snapshot_from_prepared(
        0, STATS_PAGE_PREDICTORS, predictors_view=PREDICTORS_VIEW_SPECIFIC
    )
    actions_starting_position_mw = _refresh_default_snapshot_from_prepared(
        1, STATS_PAGE_ACTIONS, actions_view=ACTIONS_VIEW_STARTING_POSITION
    )
    actions_starting_position_base = _refresh_default_snapshot_from_prepared(
        0, STATS_PAGE_ACTIONS, actions_view=ACTIONS_VIEW_STARTING_POSITION
    )
    actions_upgrades_delta_mw = _refresh_default_snapshot_from_prepared(
        1, STATS_PAGE_ACTIONS, actions_view=ACTIONS_VIEW_UPGRADES
    )
    actions_upgrades_delta_base = _refresh_default_snapshot_from_prepared(
        0, STATS_PAGE_ACTIONS, actions_view=ACTIONS_VIEW_UPGRADES
    )
    actions_upgrade_order_delta_mw = _refresh_default_snapshot_from_prepared(
        1, STATS_PAGE_ACTIONS, actions_view=ACTIONS_VIEW_UPGRADE_ORDER
    )
    actions_upgrade_order_delta_base = _refresh_default_snapshot_from_prepared(
        0, STATS_PAGE_ACTIONS, actions_view=ACTIONS_VIEW_UPGRADE_ORDER
    )
    actions_upgrade_order_frequency_mw = _refresh_default_snapshot_from_prepared(
        1, STATS_PAGE_ACTIONS, actions_view=ACTIONS_VIEW_UPGRADE_ORDER,
        completed_only_override=True,
        cache_blob_override=f"{CACHE_PREFIX}/actions/upgrade_order/frequency/default-mw.json",
    )
    actions_upgrade_order_frequency_base = _refresh_default_snapshot_from_prepared(
        0, STATS_PAGE_ACTIONS, actions_view=ACTIONS_VIEW_UPGRADE_ORDER,
        completed_only_override=True,
        cache_blob_override=f"{CACHE_PREFIX}/actions/upgrade_order/frequency/default-base.json",
    )
    actions_upgrades_by_map_delta_mw = _refresh_default_snapshot_from_prepared(
        1, STATS_PAGE_ACTIONS, actions_view=ACTIONS_VIEW_UPGRADES_BY_MAP
    )
    actions_upgrades_by_map_delta_base = _refresh_default_snapshot_from_prepared(
        0, STATS_PAGE_ACTIONS, actions_view=ACTIONS_VIEW_UPGRADES_BY_MAP
    )
    actions_upgrades_by_map_frequency_mw = _refresh_default_snapshot_from_prepared(
        1, STATS_PAGE_ACTIONS, actions_view=ACTIONS_VIEW_UPGRADES_BY_MAP,
        completed_only_override=True,
        cache_blob_override=f"{CACHE_PREFIX}/actions/upgrades_by_map/frequency/default-mw.json",
    )
    actions_upgrades_by_map_frequency_base = _refresh_default_snapshot_from_prepared(
        0, STATS_PAGE_ACTIONS, actions_view=ACTIONS_VIEW_UPGRADES_BY_MAP,
        completed_only_override=True,
        cache_blob_override=f"{CACHE_PREFIX}/actions/upgrades_by_map/frequency/default-base.json",
    )
    workers_general_mw = _refresh_default_snapshot_from_prepared(
        1, STATS_PAGE_WORKERS, workers_view=WORKERS_VIEW_GENERAL
    )
    workers_general_base = _refresh_default_snapshot_from_prepared(
        0, STATS_PAGE_WORKERS, workers_view=WORKERS_VIEW_GENERAL
    )
    workers_two_cp_mw = _refresh_default_snapshot_from_prepared(
        1, STATS_PAGE_WORKERS, workers_view=WORKERS_VIEW_TWO_CP_WORKER
    )
    workers_two_cp_base = _refresh_default_snapshot_from_prepared(
        0, STATS_PAGE_WORKERS, workers_view=WORKERS_VIEW_TWO_CP_WORKER
    )
    players_general_mw = _refresh_default_snapshot_from_prepared(
        1, STATS_PAGE_PLAYERS, players_view=PLAYERS_VIEW_GENERAL
    )
    players_general_base = _refresh_default_snapshot_from_prepared(
        0, STATS_PAGE_PLAYERS, players_view=PLAYERS_VIEW_GENERAL
    )
    mw_action_cards_general = _refresh_default_snapshot_from_prepared(
        1, STATS_PAGE_MW_ACTION_CARDS,
        mw_action_cards_view=MW_ACTION_CARDS_VIEW_GENERAL,
    )
    mw_action_cards_by_map = _refresh_default_snapshot_from_prepared(
        1, STATS_PAGE_MW_ACTION_CARDS,
        mw_action_cards_view=MW_ACTION_CARDS_VIEW_BY_MAP,
    )
    elo_leaderboard_snapshots = _refresh_records_elo_leaderboard_snapshots()
    records_snapshots = []
    for records_view in (
        RECORDS_VIEW_FASTEST_GAMES,
        RECORDS_VIEW_HIGHEST_SCORES,
        RECORDS_VIEW_BIGGEST_TURNS,
        RECORDS_VIEW_MOST_ICONS,
    ):
        for dataset in (1, 0):
            records_snapshots.append(_refresh_default_snapshot_from_prepared(
                dataset, STATS_PAGE_RECORDS, records_view=records_view
            ))
    try:
        conservation_projects_mw = conservation_futures[(1, CONSERVATION_VIEW_PROJECTS)].result()
        conservation_projects_base = conservation_futures[(0, CONSERVATION_VIEW_PROJECTS)].result()
        conservation_project_rewards_mw = conservation_futures[(1, CONSERVATION_VIEW_PROJECT_REWARDS)].result()
        conservation_project_rewards_base = conservation_futures[(0, CONSERVATION_VIEW_PROJECT_REWARDS)].result()
        conservation_cp_rewards_mw = conservation_futures[(1, CONSERVATION_VIEW_CP_REWARDS)].result()
        conservation_cp_rewards_base = conservation_futures[(0, CONSERVATION_VIEW_CP_REWARDS)].result()
    finally:
        conservation_executor.shutdown(wait=True)
    try:
        scoring_final_score_mw = scoring_futures[(1, SCORING_VIEW_FINAL_SCORE)].result()
        scoring_final_score_base = scoring_futures[(0, SCORING_VIEW_FINAL_SCORE)].result()
        scoring_appeal_mw = scoring_futures[(1, SCORING_VIEW_APPEAL)].result()
        scoring_appeal_base = scoring_futures[(0, SCORING_VIEW_APPEAL)].result()
        scoring_conservation_mw = scoring_futures[(1, SCORING_VIEW_CONSERVATION_POINTS)].result()
        scoring_conservation_base = scoring_futures[(0, SCORING_VIEW_CONSERVATION_POINTS)].result()
        scoring_reputation_mw = scoring_futures[(1, SCORING_VIEW_REPUTATION)].result()
        scoring_reputation_base = scoring_futures[(0, SCORING_VIEW_REPUTATION)].result()
    finally:
        scoring_executor.shutdown(wait=True)
    # Covariance-aware Synergy snapshots are refreshed by the separate daily
    # inference stage. The main refresh deliberately retains the last complete
    # set so a failed or long-running CI build cannot replace it with partial
    # intervals or push this request beyond Cloud Run's timeout.
    def retained_synergy_snapshot(is_mw, stats_page, view):
        kwargs = (
            {"combinations_view": view}
            if stats_page == STATS_PAGE_COMBINATIONS
            else {"mw_action_cards_view": view}
        )
        payload = _read_cached_snapshot(is_mw, stats_page, **kwargs)
        return {
            "status": "ok" if payload is not None else "error",
            "is_mw": int(is_mw),
            "stats_page": stats_page,
            "combinations_view": view if stats_page == STATS_PAGE_COMBINATIONS else None,
            "mw_action_cards_view": view if stats_page == STATS_PAGE_MW_ACTION_CARDS else None,
            "cache_status": "retained_synergy_ci_snapshot" if payload is not None else "missing",
            "rows": len((payload or {}).get("data") or []),
        }

    combinations_card_card_mw = retained_synergy_snapshot(
        1, STATS_PAGE_COMBINATIONS, COMBINATIONS_VIEW_CARD_CARD
    )
    combinations_card_card_base = retained_synergy_snapshot(
        0, STATS_PAGE_COMBINATIONS, COMBINATIONS_VIEW_CARD_CARD
    )
    combinations_card_round_mw = retained_synergy_snapshot(
        1, STATS_PAGE_COMBINATIONS, COMBINATIONS_VIEW_CARD_ROUND
    )
    combinations_card_round_base = retained_synergy_snapshot(
        0, STATS_PAGE_COMBINATIONS, COMBINATIONS_VIEW_CARD_ROUND
    )
    combinations_card_map_mw = retained_synergy_snapshot(
        1, STATS_PAGE_COMBINATIONS, COMBINATIONS_VIEW_CARD_MAP
    )
    combinations_card_map_base = retained_synergy_snapshot(
        0, STATS_PAGE_COMBINATIONS, COMBINATIONS_VIEW_CARD_MAP
    )
    combinations_card_endgame_mw = retained_synergy_snapshot(
        1, STATS_PAGE_COMBINATIONS, COMBINATIONS_VIEW_CARD_ENDGAME
    )
    combinations_card_endgame_base = retained_synergy_snapshot(
        0, STATS_PAGE_COMBINATIONS, COMBINATIONS_VIEW_CARD_ENDGAME
    )
    combinations_card_action_card_mw = retained_synergy_snapshot(
        1, STATS_PAGE_COMBINATIONS, COMBINATIONS_VIEW_CARD_ACTION_CARD
    )
    mw_action_cards_synergies = retained_synergy_snapshot(
        1, STATS_PAGE_MW_ACTION_CARDS, MW_ACTION_CARDS_VIEW_SYNERGIES
    )
    snapshots = [
        home_mw, home_base, mw, base, opening_hand_mw, opening_hand_base, endgames_mw, endgames_base,
        endgames_cp_distribution_mw, endgames_cp_distribution_base,
        endgames_cp_by_map_mw, endgames_cp_by_map_base, maps_metrics_mw, maps_metrics_base,
        maps_h2h_mw, maps_h2h_base, sponsor_endgames_cp_mw, sponsor_endgames_cp_base,
        sponsor_endgames_appeal_mw, sponsor_endgames_appeal_base,
        icons_mw, icons_base, build_delta_mw, build_delta_base,
        build_frequency_mw, build_frequency_base,
        build_hexes_delta_mw, build_hexes_delta_base,
        build_hexes_frequency_mw, build_hexes_frequency_base,
        predictors_general_mw, predictors_general_base,
        predictors_icon_mw, predictors_icon_base,
        predictors_specific_mw, predictors_specific_base,
        actions_starting_position_mw, actions_starting_position_base,
        actions_upgrades_delta_mw, actions_upgrades_delta_base,
        actions_upgrade_order_delta_mw, actions_upgrade_order_delta_base,
        actions_upgrade_order_frequency_mw, actions_upgrade_order_frequency_base,
        actions_upgrades_by_map_delta_mw, actions_upgrades_by_map_delta_base,
        actions_upgrades_by_map_frequency_mw, actions_upgrades_by_map_frequency_base,
         conservation_projects_mw, conservation_projects_base,
         conservation_project_rewards_mw, conservation_project_rewards_base,
         conservation_cp_rewards_mw, conservation_cp_rewards_base,
         scoring_final_score_mw, scoring_final_score_base,
         scoring_appeal_mw, scoring_appeal_base,
         scoring_conservation_mw, scoring_conservation_base,
         scoring_reputation_mw, scoring_reputation_base,
         workers_general_mw, workers_general_base,
         workers_two_cp_mw, workers_two_cp_base,
         players_general_mw, players_general_base,
         mw_action_cards_general, mw_action_cards_by_map,
         mw_action_cards_synergies,
         *elo_leaderboard_snapshots,
         *records_snapshots,
        combinations_card_card_mw, combinations_card_card_base,
        combinations_card_round_mw, combinations_card_round_base,
        combinations_card_map_mw, combinations_card_map_base,
         combinations_card_endgame_mw, combinations_card_endgame_base,
         combinations_card_action_card_mw,
    ]
    snapshots_ok = all(item["status"] == "ok" for item in snapshots)
    if progress:
        progress.report(94, "Publishing the atomic snapshot pack")
    default_pack = (
        _write_default_snapshot_pack(data_version)
        if snapshots_ok
        else False
    )
    if progress:
        progress.report(99, "Finalizing refresh")
    status = (
        "ok"
        if data_version and home_bootstrap and default_pack
        and arena_top100["status"] == "ok"
        and players_index_mw["status"] == "ok" and players_index_base["status"] == "ok"
        and snapshots_ok
        else "error"
    )
    return {
        "status": status,
        "total_ms": _ms_since(started_at),
        "data_version": data_version,
        "card_attributes": {
            "source_sha256": card_attributes.get("source_sha256"),
            "reefer_animals": len(card_attributes.get("reefer_animals", [])),
            "project_cards": len(card_attributes.get("project_cards", [])),
            "sponsor_cards": len(card_attributes.get("sponsor_cards", [])),
        },
        "prepared": prepared,
        "arena": {
            "configured_seasons": len(arena_metadata.get("seasons", [])),
            "latest_by_mode": arena_metadata.get("latest_by_mode", {}),
            "latest_top_100": arena_metadata.get("latest_top_100"),
            "top_100": arena_top100,
        },
        "home_mw": home_mw,
        "home_base": home_base,
        "home_bootstrap": "ok" if home_bootstrap else "error",
        "default_pack": "ok" if default_pack else "error",
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
        "icons_mw": icons_mw,
        "icons_base": icons_base,
        "build_delta_mw": build_delta_mw,
        "build_delta_base": build_delta_base,
        "build_frequency_mw": build_frequency_mw,
        "build_frequency_base": build_frequency_base,
        "build_hexes_delta_mw": build_hexes_delta_mw,
        "build_hexes_delta_base": build_hexes_delta_base,
        "build_hexes_frequency_mw": build_hexes_frequency_mw,
        "build_hexes_frequency_base": build_hexes_frequency_base,
        "predictors_general_mw": predictors_general_mw,
        "predictors_general_base": predictors_general_base,
        "predictors_icon_mw": predictors_icon_mw,
        "predictors_icon_base": predictors_icon_base,
        "predictors_specific_mw": predictors_specific_mw,
        "predictors_specific_base": predictors_specific_base,
        "actions_starting_position_mw": actions_starting_position_mw,
        "actions_starting_position_base": actions_starting_position_base,
        "actions_upgrades_delta_mw": actions_upgrades_delta_mw,
        "actions_upgrades_delta_base": actions_upgrades_delta_base,
        "actions_upgrade_order_delta_mw": actions_upgrade_order_delta_mw,
        "actions_upgrade_order_delta_base": actions_upgrade_order_delta_base,
        "actions_upgrade_order_frequency_mw": actions_upgrade_order_frequency_mw,
        "actions_upgrade_order_frequency_base": actions_upgrade_order_frequency_base,
        "actions_upgrades_by_map_delta_mw": actions_upgrades_by_map_delta_mw,
        "actions_upgrades_by_map_delta_base": actions_upgrades_by_map_delta_base,
        "actions_upgrades_by_map_frequency_mw": actions_upgrades_by_map_frequency_mw,
        "actions_upgrades_by_map_frequency_base": actions_upgrades_by_map_frequency_base,
        "conservation_projects_mw": conservation_projects_mw,
        "conservation_projects_base": conservation_projects_base,
        "conservation_project_rewards_mw": conservation_project_rewards_mw,
        "conservation_project_rewards_base": conservation_project_rewards_base,
         "conservation_cp_rewards_mw": conservation_cp_rewards_mw,
         "conservation_cp_rewards_base": conservation_cp_rewards_base,
         "workers_general_mw": workers_general_mw,
         "workers_general_base": workers_general_base,
         "workers_two_cp_mw": workers_two_cp_mw,
        "workers_two_cp_base": workers_two_cp_base,
        "players_index_mw": players_index_mw,
        "players_index_base": players_index_base,
        "players_general_mw": players_general_mw,
        "players_general_base": players_general_base,
        "mw_action_cards_general": mw_action_cards_general,
        "mw_action_cards_by_map": mw_action_cards_by_map,
        "mw_action_cards_synergies": mw_action_cards_synergies,
        "combinations_card_card_mw": combinations_card_card_mw,
        "combinations_card_card_base": combinations_card_card_base,
        "combinations_card_round_mw": combinations_card_round_mw,
        "combinations_card_round_base": combinations_card_round_base,
        "combinations_card_map_mw": combinations_card_map_mw,
        "combinations_card_map_base": combinations_card_map_base,
        "combinations_card_endgame_mw": combinations_card_endgame_mw,
        "combinations_card_endgame_base": combinations_card_endgame_base,
        "combinations_card_action_card_mw": combinations_card_action_card_mw,
    }


def _run_tracked_daily_refresh():
    """Run one main refresh with a cross-instance lock and public progress."""
    global _ACTIVE_REFRESH_PROGRESS
    run_id = uuid.uuid4().hex
    if not _acquire_refresh_lock(run_id):
        status = _read_refresh_status()
        return {
            "status": "running",
            "message": "A refresh is already running",
            "refresh_status": status,
        }

    progress = _RefreshProgress(run_id)
    with _REFRESH_PROGRESS_STATE_LOCK:
        _ACTIVE_REFRESH_PROGRESS = progress
    try:
        payload = _run_daily_refresh(progress)
        if payload.get("status") == "ok":
            progress.complete(payload.get("data_version"))
        else:
            progress.fail()
        return payload
    except Exception:
        progress.fail()
        raise
    finally:
        with _REFRESH_PROGRESS_STATE_LOCK:
            if _ACTIVE_REFRESH_PROGRESS is progress:
                _ACTIVE_REFRESH_PROGRESS = None
        _release_refresh_lock(run_id)


@functions_framework.http
def _json_http_response(payload, status_code, headers, request):
    response_headers = dict(headers)
    request_id = request.environ.get("ark_request_id")
    if request_id:
        response_headers["X-Request-Id"] = request_id
    server_timing = payload.get("_server_timing") if isinstance(payload, dict) else None
    started_at = request.environ.get("ark_started_perf")
    timing_parts = []
    if isinstance(server_timing, dict):
        for key, label in (
            ("cache_lookup_ms", "cache"),
            ("submit_ms", "submit"),
            ("query_wait_ms", "bigquery"),
            ("iteration_ms", "iterate"),
            ("response_ms", "build"),
            ("cache_write_ms", "cache-write"),
        ):
            value = server_timing.get(key)
            if isinstance(value, (int, float)):
                timing_parts.append(f'{label};dur={max(0, value):.1f}')
    if started_at is not None:
        timing_parts.append(f'total;dur={_ms_since(started_at):.1f}')
    if timing_parts:
        response_headers["Server-Timing"] = ", ".join(timing_parts)
    if isinstance(payload, dict) and "_server_timing" in payload:
        payload = dict(payload)
        payload.pop("_server_timing", None)
    encoded = json.dumps(payload, default=_json_default, separators=(",", ":")).encode("utf-8")
    accepted = request.headers.get("Accept-Encoding", "").lower()
    if len(encoded) >= 64 * 1024 and "gzip" in accepted:
        compressed = gzip.compress(encoded, compresslevel=6, mtime=0)
        response_headers["Content-Encoding"] = "gzip"
        response_headers["Vary"] = "Accept-Encoding"
        response_headers["Content-Length"] = str(len(compressed))
        return (compressed, status_code, response_headers)
    return (encoded.decode("utf-8"), status_code, response_headers)


def get_card_stats(request):
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": (
            "Content-Type, X-Ark-Nova-Maintenance-Token, "
            "X-Ark-Nova-Refresh-Password"
        ),
        "Content-Type": "application/json",
    }

    if request.method == "OPTIONS":
        return ("", 204, headers)

    request_started_at = time.perf_counter()
    request.environ["ark_started_perf"] = request_started_at
    request.environ["ark_request_id"] = uuid.uuid4().hex[:16]
    params = request.get_json(silent=True) or {}
    if params.get("refresh_status") is True:
        status_headers = dict(headers)
        status_headers["Cache-Control"] = "no-store, max-age=0"
        return _json_http_response(
            {"status": "ok", "refresh_status": _read_refresh_status()},
            200,
            status_headers,
            request,
        )

    manual_refresh_requested = params.get("manual_refresh") is True
    if manual_refresh_requested and not _has_refresh_page_auth(request):
        return _refresh_page_auth_error(headers)

    refresh_data = params.get("refresh_data") is True
    debug_timing = params.get("debug") is True
    maintenance_requested = (
        refresh_data
        or debug_timing
        or params.get("refresh_prepared") is True
        or params.get("refresh_mw_action_cards_prepared") is True
        or params.get("refresh_mw_action_cards") is True
        or params.get("refresh_players_prepared") is True
        or params.get("daily_refresh") is True
        or params.get("refresh_default_pack") is True
        or params.get("refresh_synergy_cis") is True
        or params.get("warm_card_card_defaults") is True
    )

    if maintenance_requested and not _has_maintenance_auth(request):
        return _maintenance_auth_error(headers)

    if manual_refresh_requested:
        try:
            payload = _run_tracked_daily_refresh()
            status_code = (
                200 if payload.get("status") == "ok"
                else 409 if payload.get("status") == "running"
                else 500
            )
            return _json_http_response(payload, status_code, headers, request)
        except Exception:
            logging.exception("Failed to run manual daily refresh")
            return _json_http_response(
                {"status": "error", "message": "Refresh failed"},
                500,
                headers,
                request,
            )

    if params.get("refresh_prepared") is True:
        try:
            arena_metadata = _load_arena_metadata(force_refresh=True)
            merge_metadata = _load_merge_players_metadata(force_refresh=True)
            payload = _refresh_prepared_tables(
                arena_metadata, merge_metadata
            )
            payload["data_version"] = _write_data_version(payload)
            status_code = 200 if payload["data_version"] else 500
            return _json_http_response(payload, status_code, headers, request)
        except Exception as exc:
            logging.exception("Failed to refresh prepared tables")
            return _json_http_response({"status": "error", "message": str(exc)}, 500, headers, request)

    if params.get("refresh_mw_action_cards_prepared") is True:
        try:
            payload = _refresh_prepared_mw_action_card_tables()
            return _json_http_response(payload, 200, headers, request)
        except Exception as exc:
            logging.exception("Failed to refresh prepared MW Action Cards tables")
            return _json_http_response(
                {"status": "error", "message": str(exc)}, 500, headers, request
            )

    if params.get("refresh_mw_action_cards") is True:
        try:
            prepared = _refresh_prepared_mw_action_card_tables()
            snapshots = {
                "general": _refresh_default_snapshot_from_prepared(
                    1, STATS_PAGE_MW_ACTION_CARDS,
                    mw_action_cards_view=MW_ACTION_CARDS_VIEW_GENERAL,
                ),
                "by_map": _refresh_default_snapshot_from_prepared(
                    1, STATS_PAGE_MW_ACTION_CARDS,
                    mw_action_cards_view=MW_ACTION_CARDS_VIEW_BY_MAP,
                ),
                "synergies": _refresh_default_snapshot_from_prepared(
                    1, STATS_PAGE_MW_ACTION_CARDS,
                    mw_action_cards_view=MW_ACTION_CARDS_VIEW_SYNERGIES,
                ),
            }
            data_version = _read_data_version()
            snapshots_ok = all(item.get("status") == "ok" for item in snapshots.values())
            default_pack = (
                bool(data_version)
                and snapshots_ok
                and _write_default_snapshot_pack(data_version)
            )
            payload = {
                "status": "ok" if prepared.get("status") == "ok" and default_pack else "error",
                "data_version": data_version,
                "prepared": prepared,
                "snapshots": snapshots,
                "default_pack": "ok" if default_pack else "error",
            }
            return _json_http_response(
                payload, 200 if payload["status"] == "ok" else 500, headers, request
            )
        except Exception as exc:
            logging.exception("Failed to refresh MW Action Cards")
            return _json_http_response(
                {"status": "error", "message": str(exc)}, 500, headers, request
            )

    if params.get("refresh_players_prepared") is True:
        try:
            # Physical Players tuning can be rebuilt independently because it
            # does not change snapshot semantics or the shared data version.
            payload = _refresh_prepared_players_table(
                _load_arena_metadata(force_refresh=True),
                _load_merge_players_metadata(force_refresh=True),
            )
            return _json_http_response(payload, 200, headers, request)
        except Exception as exc:
            logging.exception("Failed to refresh the prepared Players table")
            return _json_http_response({"status": "error", "message": str(exc)}, 500, headers, request)

    if params.get("refresh_default_pack") is True:
        try:
            data_version = _read_data_version()
            published = bool(data_version) and _write_default_snapshot_pack(data_version)
            return _json_http_response({
                "status": "ok" if published else "error",
                "data_version": data_version,
                "default_pack": "ok" if published else "error",
            }, 200 if published else 500, headers, request)
        except Exception as exc:
            logging.exception("Failed to republish the default snapshot pack")
            return _json_http_response(
                {"status": "error", "message": str(exc)}, 500, headers, request
            )

    if params.get("refresh_synergy_cis") is True:
        try:
            payload = _refresh_synergy_ci_snapshots()
            status_code = 200 if payload.get("status") in ("ok", "staged") else 500
            return _json_http_response(payload, status_code, headers, request)
        except Exception as exc:
            logging.exception("Failed to refresh staged Synergy CI snapshots")
            return _json_http_response(
                {"status": "error", "message": str(exc)}, 500, headers, request
            )

    if params.get("daily_refresh") is True:
        try:
            payload = _run_tracked_daily_refresh()
            status_code = (
                200 if payload.get("status") == "ok"
                else 409 if payload.get("status") == "running"
                else 500
            )
            return _json_http_response(payload, status_code, headers, request)
        except Exception as exc:
            logging.exception("Failed to run daily refresh")
            return _json_http_response({"status": "error", "message": str(exc)}, 500, headers, request)

    if params.get("warm_card_card_defaults") is True:
        try:
            payload = _warm_card_card_default_scopes()
            status_code = (
                200 if payload.get("status") == "ok"
                else 409 if payload.get("status") == "retry"
                else 500
            )
            return _json_http_response(payload, status_code, headers, request)
        except Exception as exc:
            logging.exception("Failed to warm default Card + Card scopes")
            return _json_http_response(
                {"status": "error", "message": str(exc)}, 500, headers, request
            )

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
        combination_paged = False
        combination_page = COMBINATION_PAGE_DEFAULT
        combination_page_size = COMBINATION_PAGE_SIZE_DEFAULT
        combination_min_plays = COMBINATION_DEFAULT_MIN_PLAYS
        combination_sort = "interaction"
        combination_sort_direction = "desc"
        combination_pair_types = list(COMBINATION_PAIR_TYPES)
        combination_card_types = list(DEFAULT_CARD_TYPES)
        combination_primary = ""
        combination_secondary = ""
        combination_header_maps = list(VALID_MAPS)
        combination_header_rounds = ["1", "2", "3", "4", "5", "6+"]
        if stats_page == STATS_PAGE_COMBINATIONS:
            allowed_pair_types = (
                CARD_ACTION_PAIR_TYPES
                if combinations_view == COMBINATIONS_VIEW_CARD_ACTION_CARD
                else COMBINATION_PAIR_TYPES
            )
            combination_pair_types = list(allowed_pair_types)
            combination_paged = bool(_parse_optional_bool(
                params.get("combination_paged"), "combination_paged"
            ))
            combination_page = _parse_int_param(
                params.get("combination_page"), "combination_page", COMBINATION_PAGE_DEFAULT
            )
            combination_page_size = _parse_int_param(
                params.get("combination_page_size"), "combination_page_size", COMBINATION_PAGE_SIZE_DEFAULT
            )
            combination_min_plays = _parse_int_param(
                params.get("combination_min_plays"), "combination_min_plays", COMBINATION_DEFAULT_MIN_PLAYS
            )
            if combination_page < 1:
                raise ValueError("combination_page must be at least 1")
            if combination_page_size not in COMBINATION_PAGE_SIZES:
                raise ValueError("combination_page_size must be 25, 50, or 100")
            if combination_min_plays < 0:
                raise ValueError("combination_min_plays must be non-negative")
            combination_sort = str(params.get("combination_sort") or "interaction")
            if combination_sort not in COMBINATION_SORT_FIELDS[combinations_view]:
                raise ValueError("combination_sort is not valid for this view")
            combination_sort_direction = str(params.get("combination_sort_dir") or "desc").lower()
            if combination_sort_direction not in {"asc", "desc"}:
                raise ValueError("combination_sort_dir must be asc or desc")
            combination_pair_types = _parse_combination_list(
                params.get("combination_pair_types"), "combination_pair_types", allowed_pair_types, allowed_pair_types
            )
            combination_card_types = _parse_combination_list(
                params.get("combination_card_types"), "combination_card_types", VALID_CARD_TYPES, DEFAULT_CARD_TYPES
            )
            for field_name in ("combination_primary", "combination_secondary"):
                value = params.get(field_name, "")
                if value is None:
                    value = ""
                if not isinstance(value, str):
                    raise ValueError(f"{field_name} must be a string")
                if field_name == "combination_primary":
                    combination_primary = value
                else:
                    combination_secondary = value
            combination_header_maps = _parse_combination_list(
                params.get("combination_header_maps"), "combination_header_maps", VALID_MAPS, VALID_MAPS
            )
            combination_header_rounds = _parse_combination_list(
                params.get("combination_header_rounds"), "combination_header_rounds", ["1", "2", "3", "4", "5", "6+"], ["1", "2", "3", "4", "5", "6+"]
            )
        build_view = (
            _parse_build_view(params.get("build_view"))
            if stats_page == STATS_PAGE_BUILD
            else BUILD_VIEW_ENCLOSURES
        )
        predictors_view = (
            _parse_predictors_view(params.get("predictors_view"))
            if stats_page == STATS_PAGE_PREDICTORS
            else PREDICTORS_VIEW_GENERAL
        )
        actions_view = (
            _parse_actions_view(params.get("actions_view"))
            if stats_page == STATS_PAGE_ACTIONS
            else ACTIONS_VIEW_STARTING_POSITION
        )
        conservation_view = (
            _parse_conservation_view(params.get("conservation_view"))
            if stats_page == STATS_PAGE_CONSERVATION
            else CONSERVATION_VIEW_PROJECTS
        )
        scoring_view = (
            _parse_scoring_view(params.get("scoring_view"))
            if stats_page == STATS_PAGE_SCORING
            else SCORING_VIEW_FINAL_SCORE
        )
        workers_view = (
            _parse_workers_view(params.get("workers_view"))
            if stats_page == STATS_PAGE_WORKERS
            else WORKERS_VIEW_GENERAL
        )
        players_view = (
            _parse_players_view(params.get("players_view"))
            if stats_page == STATS_PAGE_PLAYERS
            else PLAYERS_VIEW_GENERAL
        )
        arena_view = (
            _parse_arena_view(params.get("arena_view"))
            if stats_page == STATS_PAGE_ARENA
            else ARENA_VIEW_TOP_100
        )
        records_view = (
            _parse_records_view(params.get("records_view"))
            if stats_page == STATS_PAGE_RECORDS
            else RECORDS_VIEW_ELO_LEADERBOARD
        )
        mw_action_cards_view = (
            _parse_mw_action_cards_view(params.get("mw_action_cards_view"))
            if stats_page == STATS_PAGE_MW_ACTION_CARDS
            else MW_ACTION_CARDS_VIEW_GENERAL
        )
        records_player = params.get("records_player")
        if records_player is not None and not isinstance(records_player, str):
            raise ValueError("records_player must be a string or null")
        records_player = records_player.strip() if records_player else None
        records_arena_only = False
        records_tournament_only = False
        if stats_page == STATS_PAGE_RECORDS:
            records_arena_only = bool(_parse_optional_bool(params.get("records_arena_only"), "records_arena_only"))
            records_tournament_only = bool(_parse_optional_bool(params.get("records_tournament_only"), "records_tournament_only"))
            if records_arena_only and records_tournament_only:
                raise ValueError("Arena games only and Tournament games only are mutually exclusive")
        players_players = []
        players_search = False
        players_search_term = ""
        players_history = False
        players_history_metrics = []
        if stats_page == STATS_PAGE_PLAYERS:
            raw_players = params.get("players_players", [])
            if raw_players is None:
                raw_players = []
            if not isinstance(raw_players, list):
                raise ValueError("players_players must be an array")
            players_players = [
                item.strip() for item in raw_players
                if isinstance(item, str) and item.strip()
            ]
            players_limit = 8 if players_view == PLAYERS_VIEW_PERFORMANCE_BY_MAP else 5
            if len(players_players) > players_limit:
                raise ValueError(
                    f"players_players may contain at most {players_limit} players"
                )
            if len(set(players_players)) != len(players_players):
                raise ValueError("Invalid comparison player selection")
            players_search = bool(
                _parse_optional_bool(params.get("players_search"), "players_search")
            )
            players_search_term = str(
                params.get("players_search_term") or ""
            ).strip()
            players_history = bool(_parse_optional_bool(
                params.get("players_history"), "players_history"
            ))
            raw_history_metrics = params.get("players_history_metrics", [])
            if raw_history_metrics is None:
                raw_history_metrics = []
            if not isinstance(raw_history_metrics, list):
                raise ValueError("players_history_metrics must be an array")
            players_history_metrics = []
            for item in raw_history_metrics:
                key = str(item or "").strip()
                if key and key not in players_history_metrics:
                    players_history_metrics.append(key)
        is_mw = _parse_is_mw(params.get("is_mw", 1))
        raw_starting_positions = params.get("starting_positions")
        starting_positions = []
        if raw_starting_positions is not None:
            if not isinstance(raw_starting_positions, list) or not raw_starting_positions:
                raise ValueError("starting_positions must be a non-empty array")
            valid_starting_positions = {"First player", "Second player"}
            for item in raw_starting_positions:
                token = str(item or "").strip()
                if token not in valid_starting_positions:
                    raise ValueError("starting_positions contains an invalid value")
                if token not in starting_positions:
                    starting_positions.append(token)
            if len(starting_positions) == 2:
                starting_positions = []
        if stats_page == STATS_PAGE_MW_ACTION_CARDS and is_mw != 1:
            raise ValueError("MW Action Cards is only available for Marine Worlds")
        if (
            stats_page == STATS_PAGE_COMBINATIONS
            and combinations_view == COMBINATIONS_VIEW_CARD_ACTION_CARD
            and is_mw != 1
        ):
            raise ValueError("Card + Action Card is only available for Marine Worlds")
        arena_only = bool(_parse_optional_bool(params.get("arena_only"), "arena_only"))
        tournament_only = bool(_parse_optional_bool(
            params.get("tournament_only"), "tournament_only"
        ))
        if arena_only and tournament_only:
            raise ValueError("Arena games only and Tournament games only are mutually exclusive")
        synergy_ci = bool(_parse_optional_bool(
            params.get("synergy_ci"), "synergy_ci"
        ))
        players_arena_only = False
        players_arena_seasons = []
        if stats_page == STATS_PAGE_PLAYERS and players_view in (
            PLAYERS_VIEW_GENERAL,
            PLAYERS_VIEW_COMPARISON,
            PLAYERS_VIEW_PERFORMANCE_BY_MAP,
        ):
            players_arena_only = bool(_parse_optional_bool(
                params.get("players_arena_only"), "players_arena_only"
            ))
            raw_arena_seasons = params.get("players_arena_seasons", [])
            if raw_arena_seasons is None:
                raw_arena_seasons = []
            if not isinstance(raw_arena_seasons, list):
                raise ValueError("players_arena_seasons must be an array")
            players_arena_seasons = []
            for item in raw_arena_seasons:
                token = str(item or "").strip().upper()
                if token and token not in players_arena_seasons:
                    players_arena_seasons.append(token)
            if players_arena_only:
                arena_metadata = _load_arena_metadata()
                valid_seasons = {item["season"]: item for item in arena_metadata.get("seasons", [])}
                unknown = [item for item in players_arena_seasons if item not in valid_seasons]
                if unknown:
                    raise ValueError(f"Unknown Arena season: {unknown[0]}")
                incompatible = [
                    item for item in players_arena_seasons
                    if int(valid_seasons[item]["is_mw"]) != int(is_mw)
                ]
                if incompatible:
                    raise ValueError(f"Arena season {incompatible[0]} is incompatible with the selected dataset")
            else:
                players_arena_seasons = []
        if params.get("players_index") is True:
            if stats_page != STATS_PAGE_PLAYERS:
                raise ValueError("players_index is only valid for the Players page")
            # Autocomplete fallback: proxy the already-generated public index
            # through the Function's CORS/gzip response path. This reads only a
            # backend-owned cache object and never runs a BigQuery query.
            dataset = "mw" if is_mw == 1 else "base"
            index_payload = _read_cache_blob(
                f"{CACHE_PREFIX}/players/index/default-{dataset}.json",
                "players_index_proxy",
            )
            if index_payload is None:
                return _json_http_response(
                    {"status": "error", "message": "Player index snapshot is unavailable"},
                    503,
                    headers,
                    request,
                )
            index_payload["source"] = "players_index_snapshot"
            return _json_http_response(index_payload, 200, headers, request)
        if players_search:
            if (
                stats_page != STATS_PAGE_PLAYERS
                or players_view not in (
                    PLAYERS_VIEW_COMPARISON,
                    PLAYERS_VIEW_PERFORMANCE_BY_MAP,
                )
            ):
                raise ValueError(
                    "Player search is only valid for multi-player Players views"
                )
            if len(players_search_term) < 3:
                raise ValueError(
                    "players_search_term must contain at least three characters"
                )
            merge_metadata = _load_merge_players_metadata()
            selected_identities = [
                _player_identity(player, merge_metadata)
                for player in players_players
            ]
            if len(set(selected_identities)) != len(selected_identities):
                raise ValueError("Invalid comparison player selection")
            dataset = "mw" if is_mw == 1 else "base"
            index_payload = _read_cache_blob(
                f"{CACHE_PREFIX}/players/index/default-{dataset}.json",
                "players_search_index",
            )
            if index_payload is None:
                return _json_http_response(
                    {
                        "status": "error",
                        "message": "Player search is temporarily unavailable",
                    },
                    503,
                    headers,
                    request,
                )
            return _json_http_response(
                {
                    "status": "ok",
                    "players": _comparison_player_search(
                        index_payload,
                        players_search_term,
                        players_players,
                        merge_metadata,
                    ),
                    "source": "players_index_snapshot",
                },
                200,
                headers,
                request,
            )
        if stats_page == STATS_PAGE_PLAYERS and players_view == PLAYERS_VIEW_ARENA_TOP_100:
            # The page normally reads this public object directly. This proxy
            # is only a CORS-safe fallback and never runs a database query.
            arena_payload = _read_cache_blob(ARENA_TOP100_BUNDLE_BLOB, "arena_top100_proxy")
            if arena_payload is None:
                return _json_http_response(
                    {"status": "error", "message": "Arena Top 100 snapshot is unavailable"},
                    503,
                    headers,
                    request,
                )
            arena_payload["source"] = "arena_top100_snapshot"
            return _json_http_response(arena_payload, 200, headers, request)
        if stats_page == STATS_PAGE_ARENA and arena_view == ARENA_VIEW_TOP_100:
            # Standalone Arena reuses the same atomically published static
            # bundle. This fallback never scans BigQuery.
            arena_payload = _read_cache_blob(ARENA_TOP100_BUNDLE_BLOB, "arena_top100_proxy")
            if arena_payload is None:
                return _json_http_response(
                    {"status": "error", "message": "Arena Top 100 snapshot is unavailable"},
                    503,
                    headers,
                    request,
                )
            arena_payload["source"] = "arena_top100_snapshot"
            return _json_http_response(arena_payload, 200, headers, request)
        if stats_page == STATS_PAGE_RECORDS and records_view == RECORDS_VIEW_ELO_LEADERBOARD:
            # Elo Leaderboard is a daily Google-Sheets snapshot. Serving it
            # directly prevents the static table from ever starting a
            # BigQuery job or inheriting Records filter predicates.
            leaderboard_payload = _read_cached_snapshot(
                is_mw, STATS_PAGE_RECORDS, records_view=RECORDS_VIEW_ELO_LEADERBOARD
            )
            if leaderboard_payload is None:
                return _json_http_response(
                    {"status": "error", "message": "Elo Leaderboard snapshot is unavailable"},
                    503,
                    headers,
                    request,
                )
            leaderboard_payload["source"] = "records_elo_leaderboard_snapshot"
            return _json_http_response(leaderboard_payload, 200, headers, request)
        default_player_elo_min = 0 if stats_page == STATS_PAGE_HOME else None if stats_page in (STATS_PAGE_PLAYERS, STATS_PAGE_RECORDS) else 300
        default_opponent_elo_min = (
            0 if stats_page in (STATS_PAGE_HOME, STATS_PAGE_PLAYERS)
            else 300
        )
        player_elo_min = _parse_int_param(
            params.get("player_elo_min", default_player_elo_min), "player_elo_min", default_player_elo_min
        )
        player_elo_max = _parse_int_param(params.get("player_elo_max"), "player_elo_max")
        opponent_elo_min = _parse_int_param(
            params.get("opponent_elo_min", default_opponent_elo_min), "opponent_elo_min", default_opponent_elo_min
        )
        opponent_elo_max = _parse_int_param(params.get("opponent_elo_max"), "opponent_elo_max")
        default_date_from = (
            None
            if stats_page in (STATS_PAGE_HOME, STATS_PAGE_PLAYERS, STATS_PAGE_RECORDS)
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
        raw_completed_only = params["completed_only"] if "completed_only" in params else None
        completed_only = _parse_optional_bool(raw_completed_only, "completed_only")
        players_player = params.get("players_player")
        if players_player is not None and not isinstance(players_player, str):
            raise ValueError("players_player must be a string or null")
        players_player = players_player.strip() if players_player else None
        last_x_games = _parse_int_param(params.get("last_x_games"), "last_x_games")
        if last_x_games is not None and last_x_games < 1:
            raise ValueError("last_x_games must be a positive integer")
        if stats_page == STATS_PAGE_PLAYERS and last_x_games is not None and (date_from or date_to):
            raise ValueError("Players date range and last_x_games are mutually exclusive")
        if stats_page != STATS_PAGE_PLAYERS:
            players_player = None
            players_players = []
            last_x_games = None
        elif players_view == PLAYERS_VIEW_GENERAL:
            players_players = []
            if last_x_games is not None and not players_player:
                # Keep the UI value, but an empty selection has no ordered
                # player population to limit. Baselines remain available and
                # the same Last X value is reused after the next selection.
                last_x_games = None
        elif players_view == PLAYERS_VIEW_COMPARISON:
            players_player = None
            if last_x_games is not None and not players_players:
                last_x_games = None
        elif players_view == PLAYERS_VIEW_PERFORMANCE_BY_MAP:
            players_player = None
            if last_x_games is not None and not players_players:
                # Keep an empty Performance table local while retaining the
                # sidebar value. Once an alias is selected, Last X is applied
                # independently inside every identity/map partition.
                last_x_games = None
        else:
            players_player = None
            players_players = []
            last_x_games = None
        if stats_page != STATS_PAGE_RECORDS:
            records_player = None
            records_arena_only = False
            records_tournament_only = False
        players_identity = None
        players_identities = []
        if stats_page == STATS_PAGE_PLAYERS and players_view in (
            PLAYERS_VIEW_GENERAL,
            PLAYERS_VIEW_COMPARISON,
            PLAYERS_VIEW_PERFORMANCE_BY_MAP,
        ):
            merge_metadata = _load_merge_players_metadata()
            if players_view == PLAYERS_VIEW_GENERAL and players_player:
                players_identity = _player_identity(
                    players_player, merge_metadata
                )
            elif players_view in (
                PLAYERS_VIEW_COMPARISON,
                PLAYERS_VIEW_PERFORMANCE_BY_MAP,
            ):
                players_identities = [
                    _player_identity(player, merge_metadata)
                    for player in players_players
                ]
                if len(set(players_identities)) != len(players_identities):
                    raise ValueError("Invalid comparison player selection")
    except ValueError as exc:
        return _json_http_response({"status": "error", "message": str(exc)}, 400, headers, request)

    allowed_maps = (
        ALL_KNOWN_MAPS
        if stats_page in (STATS_PAGE_HOME, STATS_PAGE_PLAYERS, STATS_PAGE_RECORDS)
        else VALID_MAPS
    )
    default_maps = RECORDS_DEFAULT_MAPS if stats_page == STATS_PAGE_RECORDS else allowed_maps
    selected_maps = params.get("maps", default_maps)
    if not isinstance(selected_maps, list):
        selected_maps = allowed_maps
    selected_maps = [m for m in selected_maps if m in allowed_maps]
    if not selected_maps and stats_page not in (
        STATS_PAGE_HOME, STATS_PAGE_PLAYERS, STATS_PAGE_RECORDS
    ):
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
        STATS_PAGE_ICONS,
        STATS_PAGE_BUILD,
        STATS_PAGE_PREDICTORS,
        STATS_PAGE_ACTIONS,
        STATS_PAGE_CONSERVATION,
        STATS_PAGE_SCORING,
        STATS_PAGE_WORKERS,
        STATS_PAGE_PLAYERS,
        STATS_PAGE_MW_ACTION_CARDS,
    ):
        selected_rounds, round_filter_active = [], False
    if stats_page == STATS_PAGE_COMBINATIONS and combinations_view == COMBINATIONS_VIEW_CARD_ROUND:
        selected_rounds, round_filter_active = [], False
    if stats_page in (
        STATS_PAGE_ENDGAMES,
        STATS_PAGE_MAPS,
        STATS_PAGE_SPONSOR_ENDGAMES,
        STATS_PAGE_ICONS,
    ):
        completed_only = None
    if stats_page == STATS_PAGE_PREDICTORS:
        completed_only = None
    if stats_page == STATS_PAGE_BUILD and build_view == BUILD_VIEW_HEXES:
        # Hexes always uses the completed-table population; its UI has no toggle.
        completed_only = None
    if stats_page == STATS_PAGE_CONSERVATION and conservation_view == CONSERVATION_VIEW_PROJECTS:
        # Projects always use completed tables; the page intentionally has no toggle.
        completed_only = None
    if stats_page == STATS_PAGE_SCORING:
        # Scoring always uses the canonical completed-game population.
        completed_only = None
    if stats_page == STATS_PAGE_WORKERS and workers_view == WORKERS_VIEW_GENERAL:
        # General Workers is intentionally a hard completed-table population.
        completed_only = None
    if stats_page == STATS_PAGE_PLAYERS and players_view != PLAYERS_VIEW_PERFORMANCE_BY_MAP:
        # General and Comparison always use completed observations. Performance
        # by map is the deliberate all-game default and owns an optional toggle.
        completed_only = None
    if stats_page == STATS_PAGE_CONSERVATION and conservation_view == CONSERVATION_VIEW_CP_REWARDS:
        selected_maps = VALID_MAPS
    if stats_page == STATS_PAGE_MAPS and maps_view == MAPS_VIEW_TOURNAMENT_H2H:
        player_elo_min = 300
        player_elo_max = None
        opponent_elo_min = 300
        opponent_elo_max = None
        date_from = DEFAULT_DATE_FROM
        date_to = None
        arena_only = False
        tournament_only = False

    if synergy_ci:
        try:
            if stats_page == STATS_PAGE_COMBINATIONS:
                synergy_view = combinations_view
            elif (
                stats_page == STATS_PAGE_MW_ACTION_CARDS
                and mw_action_cards_view == MW_ACTION_CARDS_VIEW_SYNERGIES
            ):
                synergy_view = mw_action_cards_view
            else:
                raise ValueError(
                    "Synergy confidence intervals are only valid for Combinations and MW Action Cards/Synergies"
                )
            payload = _load_synergy_ci(
                _read_data_version(),
                stats_page,
                synergy_view,
                params.get("synergy_ci_rows", []),
                is_mw,
                selected_maps,
                selected_rounds if round_filter_active else [],
                player_elo_min,
                player_elo_max,
                opponent_elo_min,
                opponent_elo_max,
                date_from,
                date_to,
                completed_only,
                arena_only=arena_only,
                tournament_only=tournament_only,
                starting_positions=starting_positions,
            )
            return _json_http_response(payload, 200, headers, request)
        except ValueError as exc:
            return _json_http_response(
                {"status": "error", "message": str(exc)}, 400, headers, request
            )
        except Exception as exc:
            logging.exception("Failed to query Synergy confidence intervals")
            return _json_http_response(
                {"status": "error", "message": str(exc)}, 500, headers, request
            )

    if players_history:
        try:
            if stats_page != STATS_PAGE_PLAYERS or players_view not in (
                PLAYERS_VIEW_GENERAL, PLAYERS_VIEW_COMPARISON
            ):
                raise ValueError(
                    "Players history is only valid for General or Comparison"
                )
            catalog = _players_history_metric_catalog()
            unknown_metrics = [
                key for key in players_history_metrics if key not in catalog
            ]
            if unknown_metrics:
                raise ValueError(
                    f"Unknown Players history metric: {unknown_metrics[0]}"
                )
            if not players_history_metrics:
                raise ValueError("players_history_metrics must not be empty")
            if players_view == PLAYERS_VIEW_GENERAL:
                if not players_player or not players_identity:
                    raise ValueError("Please select a player")
                groups = {
                    catalog[key]["group"] for key in players_history_metrics
                }
                if len(groups) != 1:
                    raise ValueError(
                        "General history metrics must belong to one group"
                    )
                history_aliases = [players_player]
                history_identities = [players_identity]
            else:
                if len(players_players) < 2:
                    raise ValueError("Please select at least two players")
                if len(players_history_metrics) != 1:
                    raise ValueError(
                        "Comparison history requires exactly one metric"
                    )
                history_aliases = players_players
                history_identities = players_identities

            payload = _load_players_history(
                _read_data_version(),
                players_view,
                history_aliases,
                history_identities,
                players_history_metrics,
                is_mw,
                selected_maps,
                opponent_elo_min,
                opponent_elo_max,
                date_from,
                date_to,
                last_x_games,
                players_arena_seasons if players_arena_only else [],
                tournament_only,
                starting_positions,
            )
            return _json_http_response(payload, 200, headers, request)
        except ValueError as exc:
            return _json_http_response(
                {"status": "error", "message": str(exc)}, 400, headers, request
            )
        except Exception as exc:
            logging.exception("Failed to query Players history")
            return _json_http_response(
                {"status": "error", "message": str(exc)}, 500, headers, request
            )

    cacheable_default_request = _is_default_cache_request(
        stats_page,
        maps_view,
        build_view,
        predictors_view,
        actions_view,
        is_mw,
        selected_maps,
        player_elo_min,
        player_elo_max,
        opponent_elo_min,
        opponent_elo_max,
        date_from,
        date_to,
        completed_only,
        round_filter_active,
        players_player,
        players_view,
        players_players,
        last_x_games,
        records_view=records_view,
        mw_action_cards_view=mw_action_cards_view,
        records_player=records_player,
        records_arena_only=records_arena_only,
        records_tournament_only=records_tournament_only,
    )
    if stats_page == STATS_PAGE_PLAYERS and players_arena_only:
        cacheable_default_request = False
    if arena_only or tournament_only:
        cacheable_default_request = False
    if starting_positions:
        cacheable_default_request = False
    if stats_page == STATS_PAGE_COMBINATIONS and (
        combination_paged or combination_min_plays != COMBINATION_DEFAULT_MIN_PLAYS
    ):
        cacheable_default_request = False

    if cacheable_default_request and not refresh_data:
        cached_payload = _read_cached_snapshot(
            is_mw, stats_page, endgames_view, maps_view,
            sponsor_endgames_view, combinations_view,
            build_view, predictors_view, actions_view
            , conservation_view, scoring_view, workers_view, players_view, records_view,
            mw_action_cards_view
        )
        if cached_payload:
            if stats_page == STATS_PAGE_MW_ACTION_CARDS:
                cached_payload["mw_action_cards_view"] = mw_action_cards_view
            return _json_http_response(cached_payload, 200, headers, request)

    data_version = _read_data_version()
    filter_subview = (
        {
            "view": combinations_view,
            "paged": combination_paged,
            "page": combination_page,
            "page_size": combination_page_size,
            "min_plays": combination_min_plays,
            "sort": combination_sort,
            "sort_dir": combination_sort_direction,
            "pair_types": combination_pair_types,
            "card_types": combination_card_types,
            "primary": combination_primary,
            "secondary": combination_secondary,
            "header_maps": combination_header_maps,
            "header_rounds": combination_header_rounds,
        }
        if stats_page == STATS_PAGE_COMBINATIONS else
        endgames_view if stats_page == STATS_PAGE_ENDGAMES else
        maps_view if stats_page == STATS_PAGE_MAPS else
        sponsor_endgames_view if stats_page == STATS_PAGE_SPONSOR_ENDGAMES else
        build_view if stats_page == STATS_PAGE_BUILD else
        predictors_view if stats_page == STATS_PAGE_PREDICTORS else
        actions_view if stats_page == STATS_PAGE_ACTIONS else
        conservation_view if stats_page == STATS_PAGE_CONSERVATION else
        scoring_view if stats_page == STATS_PAGE_SCORING else
        workers_view if stats_page == STATS_PAGE_WORKERS else
        # General and Draft render different columns from one combined payload;
        # only those two share a canonical filtered cache.
        (
            MW_ACTION_CARDS_VIEW_GENERAL
            if mw_action_cards_view == MW_ACTION_CARDS_VIEW_DRAFT
            else mw_action_cards_view
        ) if stats_page == STATS_PAGE_MW_ACTION_CARDS else
        {
            "view": players_view,
            "player": players_player,
            "players": players_players,
            "last_x_games": last_x_games,
            "arena_only": players_arena_only,
            "arena_seasons": players_arena_seasons,
        } if stats_page == STATS_PAGE_PLAYERS else
        {
            "view": records_view,
            "player": records_player,
            "arena_only": records_arena_only,
            "tournament_only": records_tournament_only,
        } if stats_page == STATS_PAGE_RECORDS else
        None
    )
    filter_subview = {
        "subview": filter_subview,
        "arena_only": arena_only,
        "tournament_only": tournament_only,
        "starting_positions": sorted(starting_positions),
        "rollup_schema": 7,
    }
    filter_cache_blob_name = None
    if (
        CACHE_BUCKET
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
            completed_only,
            data_version,
            filter_subview,
            records_player,
            records_arena_only,
            records_tournament_only,
        )
        cached_payload = _read_cache_blob(filter_cache_blob_name, "filter_hit")
        if cached_payload:
            if stats_page == STATS_PAGE_MW_ACTION_CARDS:
                cached_payload["mw_action_cards_view"] = mw_action_cards_view
            return _json_http_response(cached_payload, 200, headers, request)

    try:
        query_args = (
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
            completed_only,
        )
        query_kwargs = {
            "hexes_expanded": False,
            "scoring_expanded": False,
            "combination_paged": combination_paged,
            "combination_page": combination_page,
            "combination_page_size": combination_page_size,
            "combination_min_plays": combination_min_plays,
            "combination_sort": combination_sort,
            "combination_sort_direction": combination_sort_direction,
            "combination_pair_types": combination_pair_types,
            "combination_card_types": combination_card_types,
            "combination_primary": combination_primary,
            "combination_secondary": combination_secondary,
            "combination_header_maps": combination_header_maps,
            "combination_header_rounds": combination_header_rounds,
            "endgames_view": endgames_view,
            "maps_view": maps_view,
            "sponsor_endgames_view": sponsor_endgames_view,
            "combinations_view": combinations_view,
            "build_view": build_view,
            "predictors_view": predictors_view,
            "actions_view": actions_view,
            "conservation_view": conservation_view,
            "scoring_view": scoring_view,
            "workers_view": workers_view,
            "players_view": players_view,
            "players_player": players_player,
            "players_players": players_players,
            "players_identity": players_identity,
            "players_identities": players_identities,
            "last_x_games": last_x_games,
            "players_arena_only": players_arena_only,
            "players_arena_seasons": players_arena_seasons,
            "records_view": records_view,
            "mw_action_cards_view": mw_action_cards_view,
            "records_player": records_player,
            "records_arena_only": records_arena_only,
            "records_tournament_only": records_tournament_only,
            "arena_only": arena_only,
            "tournament_only": tournament_only,
            "starting_positions": starting_positions,
            # Prepared tables are replaced atomically each day, so BigQuery's
            # own cache is safe for every view and is invalidated naturally.
            "use_query_cache": not debug_timing,
        }
        expanded_rows = None
        if (
            stats_page == STATS_PAGE_COMBINATIONS
            and combinations_view == COMBINATIONS_VIEW_CARD_CARD
            and combination_paged
        ):
            rows, timing = _query_cached_card_card_page(
                query_args, query_kwargs, data_version
            )
        elif stats_page == STATS_PAGE_PLAYERS and players_view == PLAYERS_VIEW_GENERAL:
            rows, timing = _query_players_components(
                query_args,
                query_kwargs,
                data_version,
                use_component_cache=not debug_timing,
            )
        elif (
            stats_page == STATS_PAGE_PLAYERS
            and players_view == PLAYERS_VIEW_COMPARISON
            and players_players
            and not last_x_games
            and not players_arena_only
            and not tournament_only
            and not starting_positions
            and _is_default_players_filter_scope(
                selected_maps, opponent_elo_min, opponent_elo_max, date_from,
                date_to, players_arena_only, tournament_only,
                starting_positions,
            )
        ):
            rows, timing = _query_default_players_comparison(
                is_mw, players_players, players_identities
            )
        elif stats_page == STATS_PAGE_BUILD and build_view == BUILD_VIEW_HEXES:
            rows, expanded_rows, timing = _query_hexes_both(*query_args, **query_kwargs)
        elif stats_page == STATS_PAGE_SCORING:
            rows, expanded_rows, timing = _query_scoring_both(*query_args, **query_kwargs)
        else:
            rows, timing = _query_card_stats(*query_args, **query_kwargs)
        player_response_summary = None
        comparison_response_summaries = []
        if stats_page == STATS_PAGE_PLAYERS:
            merge_metadata = _load_merge_players_metadata()
            if players_view == PLAYERS_VIEW_GENERAL and players_player:
                account_counts = (
                    rows[0].get("account_counts", []) if rows else []
                )
                player_response_summary = _selected_account_summary(
                    players_player, account_counts, merge_metadata
                )
                for row in rows:
                    row.pop("account_counts", None)
            elif players_view == PLAYERS_VIEW_COMPARISON and players_players:
                comparison_response_summaries = _decorate_comparison_rows(
                    rows,
                    players_players,
                    players_identities,
                    merge_metadata,
                )
        default_combination_floor = (
            stats_page == STATS_PAGE_COMBINATIONS
            and not combination_paged
            and combination_min_plays == COMBINATION_DEFAULT_MIN_PLAYS
        )
        default_combination_ranges = (
            _combination_ranges(rows, combinations_view)
            if default_combination_floor else None
        )
        if default_combination_floor:
            rows = [row for row in rows if int(row.get("n_played") or 0) >= COMBINATION_DEFAULT_MIN_PLAYS]
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
            "build_view": build_view if stats_page == STATS_PAGE_BUILD else None,
            "predictors_view": predictors_view if stats_page == STATS_PAGE_PREDICTORS else None,
            "actions_view": actions_view if stats_page == STATS_PAGE_ACTIONS else None,
            "conservation_view": conservation_view if stats_page == STATS_PAGE_CONSERVATION else None,
            "scoring_view": scoring_view if stats_page == STATS_PAGE_SCORING else None,
            "workers_view": workers_view if stats_page == STATS_PAGE_WORKERS else None,
            "players_view": players_view if stats_page == STATS_PAGE_PLAYERS else None,
            "records_view": records_view if stats_page == STATS_PAGE_RECORDS else None,
            "mw_action_cards_view": (
                mw_action_cards_view if stats_page == STATS_PAGE_MW_ACTION_CARDS else None
            ),
            "players_player": players_player if stats_page == STATS_PAGE_PLAYERS else None,
            "last_x_games": last_x_games if stats_page == STATS_PAGE_PLAYERS else None,
            "players_arena_only": players_arena_only if stats_page == STATS_PAGE_PLAYERS else None,
            "players_arena_seasons": players_arena_seasons if stats_page == STATS_PAGE_PLAYERS else None,
            "arena_only": arena_only,
            "tournament_only": tournament_only,
            "starting_positions": starting_positions,
            "maps": (
                ALL_MAPS_FOR_METRICS
                if stats_page in (
                    STATS_PAGE_MAPS, STATS_PAGE_BUILD, STATS_PAGE_ACTIONS,
                    STATS_PAGE_CONSERVATION, STATS_PAGE_SCORING,
                )
                else None
            ),
            "data": rows,
            "cache_status": "live",
        }
        if stats_page == STATS_PAGE_PLAYERS:
            payload["players_players"] = players_players
            if players_view == PLAYERS_VIEW_COMPARISON:
                payload["players"] = comparison_response_summaries
            elif players_view == PLAYERS_VIEW_GENERAL:
                summary = player_response_summary or {
                    "game_count": 0,
                    "selected_game_count": 0,
                    "associated_game_count": 0,
                    "is_merged": False,
                }
                payload["player_game_count"] = summary["game_count"]
                payload["player_selected_game_count"] = summary[
                    "selected_game_count"
                ]
                payload["player_associated_game_count"] = summary[
                    "associated_game_count"
                ]
                payload["player_is_merged"] = summary["is_merged"]
        if default_combination_floor:
            payload["combination_snapshot_min_plays"] = COMBINATION_DEFAULT_MIN_PLAYS
            payload["combination_ranges"] = default_combination_ranges
        combination_meta = timing.pop("combination_meta", None)
        if combination_meta:
            payload.update(combination_meta)
        if expanded_rows is not None:
            payload["expanded_data"] = expanded_rows

        if cacheable_default_request:
            cache_write_ok = _write_cached_snapshot(
                is_mw, payload, stats_page, endgames_view, maps_view,
                sponsor_endgames_view, combinations_view,
                build_view, predictors_view, actions_view, conservation_view, scoring_view, workers_view, players_view, records_view
                , mw_action_cards_view
            )
            payload["cache_status"] = "refreshed" if refresh_data and cache_write_ok else "miss"
            if not cache_write_ok:
                payload["cache_status"] = "cache_write_failed"
        elif filter_cache_blob_name and not debug_timing:
            # Persist cross-instance cache data outside the browser response
            # path. The per-instance LRU is populated synchronously first.
            cache_write_ok = _enqueue_cache_blob_write(
                filter_cache_blob_name, payload, "filter_refreshed"
            )
            payload["cache_status"] = "filter_write_queued" if cache_write_ok else "filter_cache_write_failed"

        if debug_timing:
            timing["total_ms"] = _ms_since(request_started_at)
            payload["debug_timing"] = timing

        payload["_server_timing"] = timing

        return _json_http_response(payload, 200, headers, request)

    except Exception as exc:
        logging.exception("Failed to query card stats")
        return _json_http_response({"status": "error", "message": str(exc)}, 500, headers, request)





