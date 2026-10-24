"""Read-only focused Card + Card reconciliation for the Phase 2 DuckDB slice.

The published snapshot is intentionally compared as a structural reference: the
private export is newer than the last successful public pack, so small numeric
differences are expected until a same-version snapshot is available. Additive
Synergy intervals are not part of the serving contract and are not reconciled.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


VALID_MAPS = [
    "Map 1a: Observation Tower", "Map 2a: Outdoor Areas",
    "Map 3a: Silver Lake", "Map 4a: Commercial Harbor",
    "Map 5a: Park Restaurant", "Map 6a: Research Institute",
    "Map 7a: Ice Cream Parlors", "Map 8a: Hollywood Hills",
    "Map 9: Geographical Zoo", "Map 10: Rescue Station",
    "Map 11: Caves", "Map 12: Artificial Intelligence",
    "Map 13: Drawing Board", "Map 14: Lagoon", "Map T1: Tournament 1",
]
EXCLUDED_PROJECTS = {
    "reptiles", "europe", "predators", "americas", "australia",
    "birds", "sea animals", "africa", "herbivores", "asia",
    "primates", "habitat diversity", "species diversity",
}


def sql_list(values: list[str]) -> str:
    return "[" + ", ".join("'" + value.replace("'", "''") + "'" for value in values) + "]"


def reconcile(db_path: Path, snapshot_path: Path, card_1: str, card_2: str) -> dict:
    private_root = db_path.parents[1]
    package_dir = private_root / "python314"
    if not package_dir.exists():
        package_dir = private_root / "python"
    sys.path.insert(0, str(package_dir))
    import duckdb

    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    published = next(
        (
            row for row in snapshot.get("data", [])
            if row.get("card_1") == card_1 and row.get("card_2") == card_2
        ),
        None,
    )
    maps = sql_list(VALID_MAPS)
    projects = sql_list(sorted(EXCLUDED_PROJECTS))
    query = f"""
    WITH corrupted AS (
      SELECT table_id
      FROM source_full_sample
      GROUP BY table_id
      HAVING BOOL_OR(
        TRY_CAST(Game_result AS BIGINT) = 2
        AND TRY_CAST(Number_of_turns AS DOUBLE) IS NOT NULL
        AND TRY_CAST(Animals_actions AS DOUBLE) IS NOT NULL
        AND TRY_CAST(Association_actions AS DOUBLE) IS NOT NULL
        AND TRY_CAST(Build_actions AS DOUBLE) IS NOT NULL
        AND TRY_CAST(Cards_actions AS DOUBLE) IS NOT NULL
        AND TRY_CAST(Sponsors_actions AS DOUBLE) IS NOT NULL
        AND TRY_CAST(X_Tokens_gained_instead_of_action AS DOUBLE) IS NOT NULL
        AND TRY_CAST(Number_of_turns AS DOUBLE) - (
          TRY_CAST(Animals_actions AS DOUBLE) + TRY_CAST(Association_actions AS DOUBLE)
          + TRY_CAST(Build_actions AS DOUBLE) + TRY_CAST(Cards_actions AS DOUBLE)
          + TRY_CAST(Sponsors_actions AS DOUBLE)
          + TRY_CAST(X_Tokens_gained_instead_of_action AS DOUBLE)
        ) >= 2
      )
    ), scoped AS (
      SELECT DISTINCT cp.table_id, cp.player, cp.card_name, cp.elo_delta,
        cp.game_date, gp.pre_match_elo
      FROM card_play_narrow cp
      JOIN game_player_narrow gp
        ON gp.table_id = cp.table_id AND gp.player = cp.player
      JOIN game_player_narrow opponent
        ON opponent.table_id = cp.table_id AND opponent.player <> cp.player
      LEFT JOIN corrupted bad ON bad.table_id = cp.table_id
      WHERE bad.table_id IS NULL
        AND cp.is_mw = 1
        AND cp.map_name IN {maps}
        AND cp.game_date >= DATE '2025-01-01'
        AND NOT (cp.card_type = 'project' AND LOWER(cp.card_name) IN {projects})
        AND COALESCE(gp.pre_match_elo, 0) >= 300
        AND COALESCE(opponent.pre_match_elo, 0) >= 300
    ), individual AS (
      SELECT card_name, AVG(elo_delta) AS mean_delta
      FROM scoped
      WHERE elo_delta IS NOT NULL AND card_name IN ('{card_1}', '{card_2}')
      GROUP BY card_name
    ), pair AS (
      SELECT DISTINCT a.table_id, a.player, a.elo_delta, a.pre_match_elo
      FROM scoped a
      JOIN scoped b
        ON b.table_id = a.table_id AND b.player = a.player
      WHERE a.card_name = '{card_1}' AND b.card_name = '{card_2}'
    )
    SELECT
      (SELECT mean_delta FROM individual WHERE card_name = '{card_1}') AS delta_1,
      (SELECT mean_delta FROM individual WHERE card_name = '{card_2}') AS delta_2,
      AVG(pair.elo_delta) AS delta_actual,
      AVG(pair.pre_match_elo) AS avg_elo,
      COUNT(*) AS n_played,
      COUNT(DISTINCT pair.table_id) AS table_clusters
    FROM pair
    """
    connection = duckdb.connect(str(db_path), read_only=True)
    try:
        row = connection.execute(query).fetchone()
    finally:
        connection.close()
    keys = ["delta_1", "delta_2", "delta_actual", "avg_elo", "n_played", "table_clusters"]
    local = {
        key: (None if value is None else (int(value) if key in {"n_played", "table_clusters"} else float(value)))
        for key, value in zip(keys, row)
    }
    if local["delta_1"] is not None and local["delta_2"] is not None and local["delta_actual"] is not None:
        local["delta_combined"] = local["delta_1"] + local["delta_2"]
        local["interaction"] = local["delta_actual"] - local["delta_combined"]
    else:
        local["delta_combined"] = None
        local["interaction"] = None
    selected_published = None
    if published:
        published_keys = [
            "delta_1", "delta_2", "delta_combined", "delta_actual", "interaction",
            "avg_elo", "n_played",
        ]
        selected_published = {key: published.get(key) for key in published_keys}
    return {
        "status": "ok",
        "scope": {
            "dataset": "MW",
            "maps": "standard maps",
            "date_from": "2025-01-01",
            "player_and_opponent_pre_match_elo_min": 300,
            "corrupted_tables_excluded": True,
        },
        "pair": {"card_1": card_1, "card_2": card_2},
        "local": local,
        "reference_snapshot": {
            "data_version": snapshot.get("data_version"),
            "row": selected_published,
        },
        "interpretation": "The supplied reference snapshot is compared with the private local query. Use a matching data_version for exact numeric parity; a generated local snapshot from this same generation is a same-version producer check, not a production comparison.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--card-1", default="Bamboo Forest")
    parser.add_argument("--card-2", default="Expert In Herbivores")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = reconcile(args.db, args.snapshot, args.card_1, args.card_2)
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
