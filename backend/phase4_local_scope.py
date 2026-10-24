"""Shared DuckDB filter scope for every production analytical route.

This module deliberately contains no page-specific metric logic. Routes share
normalization and predicate semantics, not an identical statistical population:
each route additionally owns its completion, log/event and telemetry eligibility.
Prequalified derivatives may omit a repeated eligibility predicate only when
their producer already enforced it. The public request cannot supply those
internal qualification flags.

Arena-season and tournament dimensions are evaluated from the metadata
relations materialized in the active immutable generation. They are never
looked up from Google Sheets during a request.
"""

from __future__ import annotations

import math
import re
from typing import Any, Mapping, Sequence


VALID_STARTING_POSITIONS = ("First player", "Second player")
VALID_ROUNDS = ("1", "2", "3", "4", "5", "6+")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Public filter controls use compact map codes while the immutable DuckDB
# source keeps the canonical Full Sample labels.  Accept canonical labels too
# because the snapshot builder uses them directly.  Normalize once here so
# every local route receives the same map population.
MAP_CODE_TO_NAME = {
    "1a": "Map 1a: Observation Tower",
    "2a": "Map 2a: Outdoor Areas",
    "3a": "Map 3a: Silver Lake",
    "4a": "Map 4a: Commercial Harbor",
    "5a": "Map 5a: Park Restaurant",
    "6a": "Map 6a: Research Institute",
    "7a": "Map 7a: Ice Cream Parlors",
    "8a": "Map 8a: Hollywood Hills",
    "9": "Map 9: Geographical Zoo",
    "10": "Map 10: Rescue Station",
    "11": "Map 11: Caves",
    "12": "Map 12: Artificial Intelligence",
    "13": "Map 13: Drawing Board",
    "14": "Map 14: Lagoon",
    "T1": "Map T1: Tournament 1",
    "1": "Map 1: Observation Tower",
    "2": "Map 2: Outdoor Areas",
    "3": "Map 3: Silver Lake",
    "4": "Map 4: Commercial Harbor",
    "5": "Map 5: Park Restaurant",
    "6": "Map 6: Research Institute",
    "7": "Map 7: Ice Cream Parlors",
    "8": "Map 8: Hollywood Hills",
    "A": "Map A",
    "0": "Map 0",
}
MAP_NAME_SET = frozenset(MAP_CODE_TO_NAME.values())


def _canonical_map(value: Any) -> str:
    text = str(value).strip()
    if text in MAP_NAME_SET:
        return text
    if text.upper() in ("T1", "A"):
        return MAP_CODE_TO_NAME[text.upper()]
    return MAP_CODE_TO_NAME.get(text.lower(), text)


def _number(request: Mapping[str, Any], key: str, default: float | None) -> float | None:
    value = request.get(key, default)
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be numeric") from exc
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{key} must be non-negative")
    return result


def normalize_scope(request: Mapping[str, Any], *, require_dataset: bool = True) -> dict[str, Any]:
    """Validate common dashboard filters and return a canonical scope object."""

    raw_dataset = request.get("is_mw")
    if raw_dataset is None and require_dataset:
        raise ValueError("is_mw is required for this private route")
    if raw_dataset is None:
        dataset = None
    else:
        try:
            dataset = int(raw_dataset)
        except (TypeError, ValueError) as exc:
            raise ValueError("is_mw must be 0 or 1") from exc
        if dataset not in (0, 1):
            raise ValueError("is_mw must be 0 or 1")

    maps = request.get("maps")
    if maps is None:
        map_values: list[str] = []
    elif isinstance(maps, Sequence) and not isinstance(maps, (str, bytes)):
        map_values = sorted({_canonical_map(value) for value in maps if str(value).strip()})
    else:
        raise ValueError("maps must be an array")
    if len(map_values) > 64:
        raise ValueError("maps contains too many values")

    positions = request.get("starting_positions")
    if positions is None:
        starting_positions = list(VALID_STARTING_POSITIONS)
    elif isinstance(positions, Sequence) and not isinstance(positions, (str, bytes)):
        starting_positions = list(dict.fromkeys(str(value).strip() for value in positions))
        if not starting_positions or any(value not in VALID_STARTING_POSITIONS for value in starting_positions):
            raise ValueError("starting_positions must contain one or both valid positions")
    else:
        raise ValueError("starting_positions must be an array")

    date_from = request.get("date_from") or None
    date_to = request.get("date_to") or None
    for key, value in (("date_from", date_from), ("date_to", date_to)):
        if value is not None and not DATE_RE.fullmatch(str(value)):
            raise ValueError(f"{key} must use YYYY-MM-DD")
    if date_from and date_to and str(date_from) > str(date_to):
        raise ValueError("date_from cannot be after date_to")

    raw_arena_seasons = request.get("arena_seasons") or request.get("players_arena_seasons")
    singular_arena_season = request.get("arena_season")
    if raw_arena_seasons is None and singular_arena_season not in (None, ""):
        raw_arena_seasons = [singular_arena_season]
    if raw_arena_seasons is None:
        arena_seasons: list[str] = []
    elif isinstance(raw_arena_seasons, Sequence) and not isinstance(raw_arena_seasons, (str, bytes)):
        arena_seasons = sorted({str(value).strip() for value in raw_arena_seasons if str(value).strip()})
        if not arena_seasons or len(arena_seasons) > 32:
            raise ValueError("arena_seasons must contain between one and 32 values")
    else:
        raise ValueError("arena_seasons must be an array")
    arena_only = request.get("arena_only")
    if arena_only is None:
        arena_only = request.get("players_arena_only")
    if arena_only not in (None, True, False):
        raise ValueError("arena_only must be boolean or null")
    if arena_seasons:
        arena_only = True

    raw_rounds = request.get("rounds")
    if raw_rounds is None:
        rounds: list[str] = []
    elif isinstance(raw_rounds, Sequence) and not isinstance(raw_rounds, (str, bytes)):
        rounds = list(dict.fromkeys(str(value).strip() for value in raw_rounds))
        if any(value not in VALID_ROUNDS for value in rounds):
            raise ValueError("rounds contains an unknown round")
        if set(rounds) == set(VALID_ROUNDS):
            rounds = []
    else:
        raise ValueError("rounds must be an array")
    tournament_only = request.get("tournament_only") or request.get("is_tournament")
    if tournament_only not in (None, True, False):
        raise ValueError("tournament_only must be boolean or null")

    completed = request.get("completed_only")
    if completed not in (None, True, False):
        raise ValueError("completed_only must be boolean or null")

    return {
        "is_mw": dataset,
        "maps": map_values,
        "player_elo_min": _number(request, "player_elo_min", 0),
        "player_elo_max": _number(request, "player_elo_max", None),
        "opponent_elo_min": _number(request, "opponent_elo_min", 0),
        "opponent_elo_max": _number(request, "opponent_elo_max", None),
        "date_from": str(date_from) if date_from else None,
        "date_to": str(date_to) if date_to else None,
        "starting_positions": starting_positions,
        "completed_only": completed,
        "arena_seasons": arena_seasons,
        "arena_only": bool(arena_only),
        "rounds": rounds,
        "tournament_only": bool(tournament_only),
    }


def scope_predicates(
    scope: Mapping[str, Any], alias: str = "f", *, hard_completed: bool = False,
    population_prepared: bool = False, include_corrupted: bool = False,
) -> tuple[str, list[Any]]:
    """Return parameterized predicates for canonical rows/qualified facts.

    Completion is table-level.  This matters when an asymmetric Elo range
    filters one player out: eligibility is still evaluated from both source
    rows, then the selected focal rows are filtered.
    """

    predicates = []
    if not population_prepared and not include_corrupted:
        predicates.append(f"NOT {alias}.is_corrupted_game")
    parameters: list[Any] = []
    if scope.get("is_mw") is not None:
        predicates.append(f"{alias}.is_mw = ?")
        parameters.append(scope["is_mw"])
    if scope.get("maps"):
        placeholders = ", ".join("?" for _ in scope["maps"])
        predicates.append(f"{alias}.Map IN ({placeholders})")
        parameters.extend(scope["maps"])
    for key, column, operator in (
        ("player_elo_min", "pre_match_elo", ">="),
        ("player_elo_max", "pre_match_elo", "<="),
        ("opponent_elo_min", "opponent_pre_match_elo", ">="),
        ("opponent_elo_max", "opponent_pre_match_elo", "<="),
    ):
        if scope.get(key) is not None:
            predicates.append(f"{alias}.{column} {operator} ?")
            parameters.append(scope[key])
    if scope.get("date_from"):
        predicates.append(f"CAST({alias}.game_ended_at AS DATE) >= CAST(? AS DATE)")
        parameters.append(scope["date_from"])
    if scope.get("date_to"):
        predicates.append(f"CAST({alias}.game_ended_at AS DATE) <= CAST(? AS DATE)")
        parameters.append(scope["date_to"])
    positions = scope.get("starting_positions") or []
    if len(positions) < len(VALID_STARTING_POSITIONS):
        placeholders = ", ".join("?" for _ in positions)
        predicates.append(f"{alias}.starting_position IN ({placeholders})")
        parameters.extend(positions)
    if scope.get("arena_seasons"):
        placeholders = ", ".join("?" for _ in scope["arena_seasons"])
        predicates.append(f"{alias}.arena_season IN ({placeholders})")
        parameters.extend(scope["arena_seasons"])
    elif scope.get("arena_only"):
        predicates.append(f"{alias}.is_arena_game")
    if scope.get("tournament_only"):
        predicates.append(f"{alias}.is_tournament")
    if (hard_completed or scope.get("completed_only") is True) and not population_prepared:
        predicates.append(f"{alias}.is_completed_game")
    return " AND ".join(predicates), parameters
