"""Focused Phase 2 reconciliation for the local Cards vertical slice.

This is deliberately read-only.  It compares the current published Cards
snapshot with the same default scope calculated from the private DuckDB
generation, while reporting the two known moving parts separately:

* the snapshot's data version may lag the export;
* the local narrow slice does not yet materialize the corruption flag, so this
  script derives the table-level predicate from the retained source relation.

It is not a production validator and must not be imported by the function.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


VALID_MAPS = [
    "Map 1a: Observation Tower",
    "Map 2a: Outdoor Areas",
    "Map 3a: Silver Lake",
    "Map 4a: Commercial Harbor",
    "Map 5a: Park Restaurant",
    "Map 6a: Research Institute",
    "Map 7a: Ice Cream Parlors",
    "Map 8a: Hollywood Hills",
    "Map 9: Geographical Zoo",
    "Map 10: Rescue Station",
    "Map 11: Caves",
    "Map 12: Artificial Intelligence",
    "Map 13: Drawing Board",
    "Map 14: Lagoon",
    "Map T1: Tournament 1",
]

EXCLUDED_PROJECTS = {
    "reptiles", "europe", "predators", "americas", "australia",
    "birds", "sea animals", "africa", "herbivores", "asia",
    "primates", "habitat diversity", "species diversity",
}


def _load_snapshot(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sql_list(values: list[str]) -> str:
    return "[" + ", ".join("'" + value.replace("'", "''") + "'" for value in values) + "]"


def reconcile(db_path: Path, snapshot_path: Path) -> dict:
    try:
        import duckdb
    except ImportError as exc:  # pragma: no cover - environment guidance
        private_root = db_path.parents[1]
        private_site = private_root / "python314"
        if not private_site.exists():
            private_site = private_root / "python"
        if private_site.exists():
            sys.path.insert(0, str(private_site))
            try:
                import duckdb
            except ImportError:
                raise SystemExit(
                    "Install/use DuckDB in the private Phase 2 environment before running this script."
                ) from exc
        else:
            raise SystemExit(
                "Install/use DuckDB in the private Phase 2 environment before running this script."
            ) from exc

    snapshot = _load_snapshot(snapshot_path)
    connection = duckdb.connect(str(db_path), read_only=True)
    maps = _sql_list(VALID_MAPS)
    excluded_projects = _sql_list(sorted(EXCLUDED_PROJECTS))

    query = f"""
    WITH corrupted AS (
      SELECT table_id
      FROM source_full_sample
      GROUP BY table_id
      HAVING BOOL_OR(
        Game_result = 2
        AND Number_of_turns IS NOT NULL
        AND Animals_actions IS NOT NULL
        AND Association_actions IS NOT NULL
        AND Build_actions IS NOT NULL
        AND Cards_actions IS NOT NULL
        AND Sponsors_actions IS NOT NULL
        AND X_Tokens_gained_instead_of_action IS NOT NULL
        AND Number_of_turns - (
          Animals_actions + Association_actions + Build_actions
          + Cards_actions + Sponsors_actions
          + X_Tokens_gained_instead_of_action
        ) >= 2
      )
    ),
    scoped AS (
      SELECT
        cp.card_name,
        cp.elo_delta,
        cp.table_id
      FROM card_play_narrow cp
      JOIN game_player_narrow player_row
        ON player_row.table_id = cp.table_id
       AND player_row.player = cp.player
      JOIN game_player_narrow opponent_row
        ON opponent_row.table_id = cp.table_id
       AND opponent_row.player <> cp.player
      LEFT JOIN corrupted bad ON bad.table_id = cp.table_id
      WHERE cp.is_mw = 1
        AND cp.map_name IN {maps}
        AND cp.game_date >= DATE '2025-01-01'
        AND NOT (
          cp.card_type = 'project'
          AND LOWER(cp.card_name) IN {excluded_projects}
        )
        AND COALESCE(player_row.pre_match_elo, 0) >= 300
        AND COALESCE(opponent_row.pre_match_elo, 0) >= 300
        AND cp.elo_delta IS NOT NULL
        AND bad.table_id IS NULL
    ),
    aggregate AS (
      SELECT
        card_name,
        AVG(elo_delta) AS delta_played,
        COUNT(DISTINCT table_id) AS n_played,
        COUNT(*) AS delta_observations
      FROM scoped
      GROUP BY card_name
    )
    SELECT
      a.card_name,
      a.delta_played,
      a.n_played,
      a.delta_observations
    FROM aggregate a
    ORDER BY a.card_name
    """
    local_rows = {
        row[0]: {
            "delta_played": float(row[1]),
            "n_played": int(row[2]),
            "delta_observations": int(row[3]),
        }
        for row in connection.execute(query).fetchall()
    }
    # Keep the corruption summary independent so an empty future generation is
    # still diagnosable.
    summary = connection.execute(
        f"""
        WITH corrupted AS (
          SELECT table_id
          FROM source_full_sample
          GROUP BY table_id
          HAVING BOOL_OR(
            Game_result = 2
            AND Number_of_turns IS NOT NULL
            AND Animals_actions IS NOT NULL
            AND Association_actions IS NOT NULL
            AND Build_actions IS NOT NULL
            AND Cards_actions IS NOT NULL
            AND Sponsors_actions IS NOT NULL
            AND X_Tokens_gained_instead_of_action IS NOT NULL
            AND Number_of_turns - (
              Animals_actions + Association_actions + Build_actions
              + Cards_actions + Sponsors_actions
              + X_Tokens_gained_instead_of_action
            ) >= 2
          )
        )
        SELECT
          (SELECT COUNT(*) FROM corrupted) AS corrupted_tables,
          (SELECT COUNT(DISTINCT c.table_id)
             FROM corrupted c
             JOIN card_play_narrow cp USING (table_id)
            WHERE cp.is_mw = 1 AND cp.map_name IN {maps}) AS corrupted_card_tables,
          (SELECT COUNT(*)
             FROM card_play_narrow cp
             JOIN corrupted c USING (table_id)
            WHERE cp.is_mw = 1 AND cp.map_name IN {maps}) AS corrupted_card_observations
        """
    ).fetchone()

    snapshot_rows = {
        row["card_name"]: {
            "delta_played": float(row["delta_played"]),
            "n_played": int(row["n_played"]),
        }
        for row in snapshot.get("data", [])
        if row.get("card_name") and row.get("delta_played") is not None
    }
    comparison = []
    for name in sorted(set(local_rows) | set(snapshot_rows)):
        local = local_rows.get(name)
        published = snapshot_rows.get(name)
        item = {
            "card_name": name,
            "local": local,
            "published": published,
        }
        if local and published:
            item["delta_difference"] = local["delta_played"] - published["delta_played"]
            item["count_difference"] = local["n_played"] - published["n_played"]
        comparison.append(item)
    comparison.sort(
        key=lambda item: abs(item.get("delta_difference", 0)), reverse=True
    )
    shared = [item for item in comparison if "delta_difference" in item]
    count_mismatches = [item for item in shared if item["count_difference"] != 0]
    absolute_differences = [abs(item["delta_difference"]) for item in shared]
    return {
        "status": "ok",
        "snapshot": {
            "path": str(snapshot_path),
            "data_version": snapshot.get("data_version"),
            "rows": len(snapshot.get("data", [])),
        },
        "local": {
            "db": str(db_path),
            "cards": len(local_rows),
            "total_n_played": sum(item["n_played"] for item in local_rows.values()),
            "total_delta_observations": sum(
                item["delta_observations"] for item in local_rows.values()
            ),
            "local_only_cards": sorted(set(local_rows) - set(snapshot_rows)),
            "published_only_cards": sorted(set(snapshot_rows) - set(local_rows)),
            "corrupted_tables": int(summary[0]),
            "corrupted_card_tables": int(summary[1]),
            "corrupted_card_observations": int(summary[2]),
        },
        "numeric_comparison": {
            "shared_cards": len(shared),
            "count_mismatch_cards": len(count_mismatches),
            "max_absolute_delta_difference": max(absolute_differences, default=0),
            "mean_absolute_delta_difference": (
                sum(absolute_differences) / len(absolute_differences)
                if absolute_differences else 0
            ),
        },
        "comparison": comparison,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = reconcile(args.db, args.snapshot)
    result["comparison"] = result["comparison"][: max(args.top, 0)]
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
