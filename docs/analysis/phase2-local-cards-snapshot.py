"""Build a local Cards default snapshot from one private DuckDB generation.

This is a Phase 2 prototype producer, not a production publishing command. It
keeps the dashboard's current default scope and Cards moment semantics while
avoiding any BigQuery query. Output is written atomically when requested.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
import time
from datetime import datetime, timezone
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


def confidence(mean: float | None, sd: float | None, n: int) -> tuple[float | None, float | None]:
    if mean is None or sd is None or n < 2:
        return None, None
    margin = 1.96 * sd / math.sqrt(n)
    return mean - margin, mean + margin


def build(database_path: Path, output_path: Path | None, generation: str) -> dict:
    private_root = database_path.parent.parent
    package_dir = private_root / "python314"
    if not package_dir.exists():
        package_dir = private_root / "python"
    sys.path.insert(0, str(package_dir))
    import duckdb

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
    ), eligible_players AS (
      SELECT DISTINCT gp.*
      FROM game_player_narrow gp
      JOIN game_player_narrow opponent
        ON opponent.table_id = gp.table_id AND opponent.player <> gp.player
      LEFT JOIN corrupted bad ON bad.table_id = gp.table_id
      WHERE bad.table_id IS NULL AND gp.is_mw = 1
        AND gp.map_name IN {maps}
        AND gp.game_date >= DATE '2025-01-01'
        AND COALESCE(gp.pre_match_elo, 0) >= 300
        AND COALESCE(opponent.pre_match_elo, 0) >= 300
    ), played AS (
      SELECT DISTINCT cp.table_id, cp.player, cp.card_name, cp.card_type,
        cp.elo_delta, cp.pre_match_elo
      FROM card_play_narrow cp JOIN eligible_players ep
        ON ep.table_id = cp.table_id AND ep.player = cp.player
      WHERE NOT (cp.card_type = 'project' AND LOWER(cp.card_name) IN {projects})
    ), card_catalog AS (
      SELECT card_name, MIN(card_type) AS card_type
      FROM played GROUP BY card_name
    ), in_hand_rows AS (
      SELECT DISTINCT ep.table_id, ep.player, TRIM(ih.card_name) AS card_name,
        ep.elo_delta
      FROM eligible_players ep
      JOIN card_in_hand_narrow ih
        ON ih.table_id = ep.table_id AND ih.player = ep.player
      JOIN card_catalog cc ON cc.card_name = TRIM(ih.card_name)
      WHERE LOWER(TRIM(ih.card_name)) NOT IN {projects}
    ), seen_rows AS (
      SELECT DISTINCT ep.table_id, TRIM(s.card_name) AS card_name
      FROM eligible_players ep
      JOIN card_seen_narrow s
        ON s.table_id = ep.table_id AND s.player = ep.player
      JOIN card_catalog cc ON cc.card_name = TRIM(s.card_name)
      WHERE LOWER(TRIM(s.card_name)) NOT IN {projects}
    ), played_agg AS (
      SELECT card_name, card_type,
        COUNT(DISTINCT table_id) AS n_played,
        AVG(elo_delta) AS delta_played,
        STDDEV_SAMP(elo_delta) AS delta_played_sd,
        COUNT(elo_delta) AS delta_played_n,
        ROUND(AVG(pre_match_elo), 0) AS avg_elo
      FROM played GROUP BY card_name, card_type
    ), in_hand_agg AS (
      SELECT card_name, AVG(elo_delta) AS delta_in_hand,
        STDDEV_SAMP(elo_delta) AS delta_in_hand_sd,
        COUNT(elo_delta) AS delta_in_hand_n
      FROM in_hand_rows GROUP BY card_name
    ), seen_agg AS (
      SELECT card_name, COUNT(DISTINCT table_id) AS n_seen
      FROM seen_rows GROUP BY card_name
    )
    SELECT p.card_type, p.card_name, p.n_played, p.delta_played,
      p.delta_played_sd, p.delta_played_n, p.avg_elo,
      h.delta_in_hand, h.delta_in_hand_sd, h.delta_in_hand_n,
      s.n_seen,
      CASE WHEN s.n_seen IS NULL OR s.n_seen = 0 THEN NULL
        ELSE ROUND(100.0 * p.n_played / s.n_seen, 2) END AS playrate_pct
    FROM played_agg p
    LEFT JOIN in_hand_agg h USING (card_name)
    LEFT JOIN seen_agg s USING (card_name)
    ORDER BY p.card_type, playrate_pct DESC NULLS LAST, p.n_played DESC
    """
    started = time.perf_counter()
    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        rows = connection.execute(query).fetchall()
    finally:
        connection.close()

    data = []
    for row in rows:
        (
            card_type, card_name, n_played, delta_played, delta_played_sd,
            delta_played_n, avg_elo, delta_in_hand, delta_in_hand_sd,
            delta_in_hand_n, n_seen, playrate_pct,
        ) = row
        delta_played = None if delta_played is None else float(delta_played)
        delta_in_hand = None if delta_in_hand is None else float(delta_in_hand)
        played_low, played_high = confidence(
            delta_played,
            None if delta_played_sd is None else float(delta_played_sd),
            int(delta_played_n or 0),
        )
        hand_low, hand_high = confidence(
            delta_in_hand,
            None if delta_in_hand_sd is None else float(delta_in_hand_sd),
            int(delta_in_hand_n or 0),
        )
        data.append({
            "card_type": card_type,
            "card_name": card_name,
            "delta_played": None if delta_played is None else round(delta_played, 3),
            "delta_in_hand": None if delta_in_hand is None else round(delta_in_hand, 3),
            "avg_elo": None if avg_elo is None else int(round(float(avg_elo))),
            "n_played": int(n_played or 0),
            "n_seen": None if n_seen is None else int(n_seen),
            "playrate_pct": None if playrate_pct is None else float(playrate_pct),
            "avg_cp": None,
            "delta_played_ci95_low": played_low,
            "delta_played_ci95_high": played_high,
            "delta_played_ci95_n": int(delta_played_n or 0),
            "delta_in_hand_ci95_low": hand_low,
            "delta_in_hand_ci95_high": hand_high,
            "delta_in_hand_ci95_n": int(delta_in_hand_n or 0),
        })

    payload = {
        "status": "ok",
        "data_version": generation,
        "stats_page": "cards",
        "is_mw": 1,
        "round_filter_active": False,
        "cache_status": "local_prototype",
        "source": "phase2_local_duckdb",
        "row_count": len(data),
        "total_ms": round((time.perf_counter() - started) * 1000, 3),
        "data": data,
    }
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output_path.parent,
            prefix=f".{output_path.name}.", suffix=".tmp", delete=False,
        ) as temporary:
            json.dump(payload, temporary, ensure_ascii=False, separators=(",", ":"))
            temporary.write("\n")
            temporary_path = Path(temporary.name)
        temporary_path.replace(output_path)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database_path", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--generation", default="phase2-20260915-b57235ad65db")
    args = parser.parse_args()
    payload = build(args.database_path, args.output, args.generation)
    print(json.dumps({key: payload[key] for key in payload if key != "data"}, indent=2))


if __name__ == "__main__":
    main()
