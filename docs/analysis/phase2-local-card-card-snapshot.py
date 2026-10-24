"""Build a private default Card + Card snapshot from one DuckDB generation.

Pair observations stay in staged temporary aggregates. The prototype retains
ordinary standalone component and Actual EV intervals; additive Synergy
intervals are intentionally not calculated.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
import time
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
    return "[" + ", ".join(
        "'" + value.replace("'", "''") + "'" for value in values
    ) + "]"


def ci(mean: float | None, se: float | None) -> tuple[float | None, float | None]:
    if mean is None or se is None or not math.isfinite(se):
        return None, None
    margin = 1.96 * se
    return mean - margin, mean + margin


def pair_type(type_1: str, type_2: str) -> str:
    if type_1 == type_2:
        return f"{type_1.title()} + {type_2.title()}"
    return " + ".join(sorted((type_1.title(), type_2.title())))


def build(database_path: Path, output_path: Path | None, generation: str) -> dict:
    private_root = database_path.parent.parent
    package_dir = private_root / "python314"
    if not package_dir.exists():
        package_dir = private_root / "python"
    sys.path.insert(0, str(package_dir))
    import duckdb

    maps = sql_list(VALID_MAPS)
    projects = sql_list(sorted(EXCLUDED_PROJECTS))
    started = time.perf_counter()
    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        connection.execute("PRAGMA threads = 4")
        connection.execute("PRAGMA preserve_insertion_order = false")
        connection.execute("PRAGMA memory_limit = '6GB'")
        connection.execute("""
            CREATE OR REPLACE TEMP TABLE component_by_table AS
            SELECT card_name, table_id, delta_count, delta_sum,
              delta_sum_squares
            FROM card_component_by_table_narrow
        """)
        connection.execute("""
            CREATE OR REPLACE TEMP TABLE component_totals AS
            SELECT card_name, SUM(delta_count) AS delta_n,
              SUM(delta_sum) AS delta_sum,
              SUM(delta_sum_squares) AS delta_sum_squares
            FROM component_by_table GROUP BY card_name
        """)
        connection.execute("""
            CREATE OR REPLACE TEMP TABLE component_stats AS
            SELECT t.card_name, t.delta_n,
              t.delta_sum / t.delta_n AS mean_delta,
              SQRT(GREATEST(0, (
                t.delta_sum_squares - POW(t.delta_sum, 2) / t.delta_n
              ) / NULLIF(t.delta_n - 1, 0))) AS sd,
              SQRT(
                COUNT(*) / NULLIF(COUNT(*) - 1, 0)
                * SUM(POW(
                  b.delta_sum - b.delta_count * (t.delta_sum / t.delta_n), 2
                )) / POW(t.delta_n, 2)
              ) AS clustered_se
            FROM component_by_table b JOIN component_totals t USING (card_name)
            GROUP BY t.card_name, t.delta_n, t.delta_sum, t.delta_sum_squares
        """)
        # The serving builder stores Card + Card moments directly at pair
        # level.  Additive Synergy CIs are out of scope, so retaining the much
        # larger table/player pair relation would only duplicate work.
        connection.execute("""
            CREATE OR REPLACE TEMP TABLE pair_by_table AS
            SELECT * FROM card_pair_aggregate_narrow
        """)
        connection.execute("""
            CREATE OR REPLACE TEMP TABLE pair_agg AS
            SELECT card_1, ANY_VALUE(type_1) AS type_1,
              card_2, ANY_VALUE(type_2) AS type_2,
              SUM(observation_count) AS n_played, SUM(delta_count) AS actual_n,
              SUM(delta_sum) / NULLIF(SUM(delta_count), 0) AS actual_mean,
              SQRT(GREATEST(0, (
                SUM(delta_sum_squares)
                  - POW(SUM(delta_sum), 2) / NULLIF(SUM(delta_count), 0)
              ) / NULLIF(SUM(delta_count) - 1, 0))) AS actual_sd,
              SUM(elo_sum) / NULLIF(SUM(elo_count), 0) AS avg_elo
            FROM pair_by_table GROUP BY card_1, card_2
            HAVING SUM(observation_count) >= 1000
        """)
        pair_rows = connection.execute("""
            SELECT p.card_1, p.type_1, c1.mean_delta, c1.clustered_se, c1.delta_n,
              p.card_2, p.type_2, c2.mean_delta, c2.clustered_se, c2.delta_n,
              p.n_played, p.actual_mean, p.actual_sd, p.actual_n, p.avg_elo
            FROM pair_agg p
            JOIN component_stats c1 ON c1.card_name = p.card_1
            JOIN component_stats c2 ON c2.card_name = p.card_2
            ORDER BY p.actual_mean - c1.mean_delta - c2.mean_delta DESC,
              p.n_played DESC, p.card_1, p.card_2
        """).fetchall()

    finally:
        connection.close()

    data = []
    for row in pair_rows:
        (
            card_1, type_1, delta_1, component_1_se, component_1_n,
            card_2, type_2, delta_2, component_2_se, component_2_n,
            n_played, actual, actual_sd, actual_n, avg_elo,
        ) = row
        delta_1 = None if delta_1 is None else float(delta_1)
        delta_2 = None if delta_2 is None else float(delta_2)
        actual = None if actual is None else float(actual)
        component_1_se = None if component_1_se is None else float(component_1_se)
        component_2_se = None if component_2_se is None else float(component_2_se)
        actual_sd = None if actual_sd is None else float(actual_sd)
        actual_se = None
        if actual_sd is not None and actual_n and int(actual_n) > 0:
            actual_se = actual_sd / math.sqrt(int(actual_n))
        synergy = None
        if delta_1 is not None and delta_2 is not None and actual is not None:
            synergy = actual - delta_1 - delta_2
        actual_low, actual_high = ci(actual, actual_se)
        component_1_low, component_1_high = ci(delta_1, component_1_se)
        component_2_low, component_2_high = ci(delta_2, component_2_se)
        data.append({
            "card_1": card_1, "type_1": type_1,
            "delta_1": None if delta_1 is None else round(delta_1, 3),
            "card_2": card_2, "type_2": type_2,
            "delta_2": None if delta_2 is None else round(delta_2, 3),
            "delta_combined": None if delta_1 is None or delta_2 is None else round(delta_1 + delta_2, 3),
            "delta_actual": None if actual is None else round(actual, 3),
            "interaction": None if synergy is None else round(synergy, 3),
            "avg_elo": None if avg_elo is None else int(round(float(avg_elo))),
            "n_played": int(n_played or 0), "pair_type": pair_type(type_1, type_2),
            "delta_actual_ci95_low": actual_low,
            "delta_actual_ci95_high": actual_high,
            "delta_actual_ci95_n": int(actual_n or 0),
            "component_1_ci95_low": component_1_low,
            "component_1_ci95_high": component_1_high,
            "component_1_ci95_se": component_1_se,
            "component_1_ci95_n": int(component_1_n or 0),
            "component_2_ci95_low": component_2_low,
            "component_2_ci95_high": component_2_high,
            "component_2_ci95_se": component_2_se,
            "component_2_ci95_n": int(component_2_n or 0),
        })

    payload = {
        "status": "ok", "data_version": generation,
        "stats_page": "combinations", "combinations_view": "card_card",
        "is_mw": 1, "round_filter_active": False,
        "cache_status": "local_prototype", "source": "phase2_local_duckdb",
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
