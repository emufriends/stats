"""Independent standard-library oracles for the migration contract fixture.

This module must not import production query builders or prepared derivatives.
It intentionally computes expectations from raw fixture rows so that production
and oracle cannot share the same population bug.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import fmean
from typing import Any


def game_index(fixture: dict[str, Any]) -> dict[tuple[int, str], dict[str, Any]]:
    return {(int(row["table_id"]), str(row["player"])): row for row in fixture["games"]}


def canonical_opponent_elos(fixture: dict[str, Any]) -> dict[str, float | None]:
    by_table: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in fixture["games"]:
        by_table[int(row["table_id"])].append(row)
    result: dict[str, float | None] = {}
    for table_id, rows in by_table.items():
        for row in rows:
            opponents = {
                float(other["pre_match_elo"])
                for other in rows
                if other["player"] != row["player"] and other.get("pre_match_elo") is not None
            }
            result[f"{table_id}/{row['player']}"] = next(iter(opponents)) if len(opponents) == 1 else None
    return result


def card_event_ev(fixture: dict[str, Any], card: str, rounds: set[int] | None = None) -> float:
    games = game_index(fixture)
    values = [
        float(games[(int(event["table_id"]), str(event["player"]))]["elo_delta"])
        for event in fixture["card_events"]
        if event["card"] == card and (rounds is None or int(event["round"]) in rounds)
    ]
    return fmean(values)


def unique_card_player_games(fixture: dict[str, Any], card: str) -> int:
    return len({
        (int(event["table_id"]), str(event["player"]))
        for event in fixture["card_events"] if event["card"] == card
    })


def opening_stats(fixture: dict[str, Any], card: str) -> dict[str, float | int]:
    games = game_index(fixture)
    dealt = [row for row in fixture["opening_hands"] if card in row["dealt"]]
    kept = [row for row in dealt if card in row["kept"]]
    dealt_ev = fmean(float(games[(int(row["table_id"]), str(row["player"]))]["elo_delta"]) for row in dealt)
    kept_ev = fmean(float(games[(int(row["table_id"]), str(row["player"]))]["elo_delta"]) for row in kept)
    return {
        "dealt_n": len(dealt),
        "kept_n": len(kept),
        "dealt_ev": dealt_ev,
        "kept_ev": kept_ev,
        "keep_rate_pct": 100.0 * len(kept) / len(dealt),
    }


def visible_table_ids(fixture: dict[str, Any], *, home: bool) -> list[int]:
    return sorted({
        int(row["table_id"])
        for row in fixture["games"]
        if home or not bool(row.get("corrupted"))
    })
