"""Independently reconcile the current Card + Card default snapshot.

This gate deliberately spells out the default population from immutable player
games and card-play facts.  It does not import the production combination SQL.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from phase3_duckdb_service import GenerationManager, _load_duckdb


STANDARD_MAPS = (
    "Map 1a: Observation Tower", "Map 2a: Outdoor Areas",
    "Map 3a: Silver Lake", "Map 4a: Commercial Harbor",
    "Map 5a: Park Restaurant", "Map 6a: Research Institute",
    "Map 7a: Ice Cream Parlors", "Map 8a: Hollywood Hills",
    "Map 9: Geographical Zoo", "Map 10: Rescue Station",
    "Map 11: Caves", "Map 12: Artificial Intelligence",
    "Map 13: Drawing Board", "Map 14: Lagoon",
    "Map T1: Tournament 1",
)
EXCLUDED_PROJECTS = (
    "africa", "americas", "asia", "australia", "birds", "europe",
    "habitat diversity", "herbivores", "predators", "primates", "reptiles",
    "sea animals", "species diversity",
)


def _close(left, right, tolerance: float = 1e-9) -> bool:
    if left is None or right is None:
        return left is right
    return math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=tolerance)


def _rounded_match(expected, actual, raw, digits: int) -> bool:
    """Permit a one-unit display difference only at a proven rounding tie."""
    if _close(expected, actual):
        return True
    if expected is None or actual is None or raw is None:
        return False
    unit = 10.0 ** -digits
    if abs(float(expected) - float(actual)) > unit + 1e-9:
        return False
    scaled = abs(float(raw)) / unit
    midpoint = math.floor(scaled) + 0.5
    return abs(scaled - midpoint) <= 128 * math.ulp(scaled)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/home/ascri"))
    parser.add_argument("--report", type=Path)
    parser.add_argument("--generation-id", help="Reconcile an inactive candidate without changing serving pointers")
    args = parser.parse_args()

    manager = GenerationManager(
        args.root / "phase2_private_data/generations",
        args.root / "phase3_private_serving/current.json",
    )
    generation = manager.inspect(args.generation_id) if args.generation_id else manager.current()
    if generation is None:
        raise RuntimeError("no generation available for Card+Card reconciliation")
    snapshot_path = (
        args.root / "phase2_private_data/snapshots" / generation.generation_id
        / "card-stats/combinations/card-card/default-mw.json"
    )
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    placeholders = ", ".join("?" for _ in STANDARD_MAPS)
    excluded = ", ".join("?" for _ in EXCLUDED_PROJECTS)
    sql = f"""
    WITH scoped_players AS (
      SELECT table_id, player, elo_delta, pre_match_elo
      FROM prepared_full_sample_narrow
      WHERE is_mw = TRUE AND NOT is_corrupted_game
        AND Map IN ({placeholders})
        AND pre_match_elo >= 300 AND opponent_elo >= 300
        AND CAST(game_ended_at AS DATE) >= DATE '2025-01-01'
    ), played AS (
      SELECT DISTINCT p.table_id, p.player, cp.card_name, cp.card_type,
        p.elo_delta, p.pre_match_elo
      FROM scoped_players p JOIN card_play_narrow cp USING(table_id, player)
      WHERE NOT (cp.card_type = 'project' AND LOWER(cp.card_name) IN ({excluded}))
    ), components AS (
      SELECT card_name, ANY_VALUE(card_type) AS card_type, AVG(elo_delta) AS delta
      FROM played GROUP BY card_name
    ), pairs AS (
      SELECT a.card_name AS card_1, ANY_VALUE(a.card_type) AS type_1,
        b.card_name AS card_2, ANY_VALUE(b.card_type) AS type_2,
        AVG(a.elo_delta) AS delta_actual,
        STDDEV_SAMP(a.elo_delta) AS delta_actual_ci_sd,
        COUNT(a.elo_delta) AS delta_actual_ci_n,
        AVG(a.pre_match_elo) AS avg_elo, COUNT(*) AS n_played
      FROM played a JOIN played b
        ON b.table_id = a.table_id AND b.player = a.player
       AND a.card_name < b.card_name
      GROUP BY a.card_name, b.card_name
    )
    SELECT p.card_1, p.type_1, p.card_2, p.type_2,
      ROUND(c1.delta, 3) AS delta_1, ROUND(c2.delta, 3) AS delta_2,
      c1.delta AS component_1_mean, c2.delta AS component_2_mean,
      c1.delta + c2.delta AS delta_combined_raw,
      ROUND(c1.delta + c2.delta, 3) AS delta_combined,
      ROUND(p.delta_actual, 3) AS delta_actual,
      p.delta_actual AS delta_actual_ci_mean,
      p.delta_actual_ci_sd, p.delta_actual_ci_n,
      ROUND(p.delta_actual - c1.delta - c2.delta, 3) AS interaction,
      p.delta_actual - c1.delta - c2.delta AS interaction_raw,
      p.avg_elo AS avg_elo_raw,
      ROUND(p.avg_elo, 0) AS avg_elo, p.n_played,
      LEAST(UPPER(SUBSTR(p.type_1,1,1)) || SUBSTR(p.type_1,2),
            UPPER(SUBSTR(p.type_2,1,1)) || SUBSTR(p.type_2,2)) || ' + ' ||
      GREATEST(UPPER(SUBSTR(p.type_1,1,1)) || SUBSTR(p.type_1,2),
               UPPER(SUBSTR(p.type_2,1,1)) || SUBSTR(p.type_2,2)) AS pair_type
    FROM pairs p JOIN components c1 ON c1.card_name = p.card_1
    JOIN components c2 ON c2.card_name = p.card_2
    WHERE p.n_played >= 1000
    """
    columns = (
        "card_1", "type_1", "card_2", "type_2", "delta_1", "delta_2",
        "component_1_mean", "component_2_mean", "delta_combined_raw",
        "delta_combined", "delta_actual", "delta_actual_ci_mean",
        "delta_actual_ci_sd", "delta_actual_ci_n", "interaction",
        "interaction_raw", "avg_elo_raw", "avg_elo", "n_played", "pair_type",
    )
    duckdb = _load_duckdb()
    connection = duckdb.connect(str(generation.database_path), read_only=True)
    try:
        rows = connection.execute(sql, [*STANDARD_MAPS, *EXCLUDED_PROJECTS]).fetchall()
    finally:
        connection.close()
    direct = {tuple(row[:1] + row[2:3]): dict(zip(columns, row)) for row in rows}
    published_rows = snapshot.get("data") or []
    published = {(row.get("card_1"), row.get("card_2")): row for row in published_rows}
    missing = sorted(set(direct) - set(published))
    unexpected = sorted(set(published) - set(direct))
    mismatches = []
    rounded_numeric = {
        "delta_1": ("component_1_mean", 3), "delta_2": ("component_2_mean", 3),
        "delta_combined": ("delta_combined_raw", 3),
        "delta_actual": ("delta_actual_ci_mean", 3),
        "interaction": ("interaction_raw", 3), "avg_elo": ("avg_elo_raw", 0),
    }
    raw_numeric = (
        "delta_actual_ci_mean", "delta_actual_ci_sd",
        "component_1_mean", "component_2_mean",
    )
    exact_numeric = ("delta_actual_ci_n", "n_played")
    rounding_ties = []
    textual = ("type_1", "type_2", "pair_type")
    for key in sorted(set(direct) & set(published)):
        expected, actual = direct[key], published[key]
        # DuckDB may reduce floating AVG partitions in a different order on
        # separate executions.  At an exact half-thousandth boundary that can
        # move a presentation-only ROUND(..., 3) by one display unit even
        # while the unrounded mean agrees to the strict tolerance below.
        fields = [
            field for field, (raw_field, digits) in rounded_numeric.items()
            if not _rounded_match(expected[field], actual.get(field), expected[raw_field], digits)
        ]
        fields += [
            field for field in raw_numeric
            if not _close(expected[field], actual.get(field))
        ]
        fields += [field for field in textual if expected[field] != actual.get(field)]
        fields += [field for field in exact_numeric if expected[field] != actual.get(field)]
        for field, (raw_field, digits) in rounded_numeric.items():
            if not _close(expected[field], actual.get(field)) and field not in fields:
                rounding_ties.append({"key": key, "field": field, "raw": expected[raw_field],
                                      "expected": expected[field], "actual": actual.get(field)})
        if fields:
            mismatches.append({
                "key": key,
                "fields": fields,
                "expected": {field: expected.get(field) for field in fields},
                "actual": {field: actual.get(field) for field in fields},
            })
    current_version = generation.data_version
    report = {
        "status": "pass" if not (missing or unexpected or mismatches) else "fail",
        "generation": generation.generation_id,
        "data_version": current_version,
        "snapshot_data_version": snapshot.get("data_version"),
        "direct_rows": len(direct),
        "snapshot_rows": len(published),
        "missing": missing[:10],
        "unexpected": unexpected[:10],
        "mismatches": mismatches[:10],
        "rounded_field_rule": "exact display match or one display unit at a proven 128-ULP rounding midpoint",
        "rounding_ties": rounding_ties,
        "raw_field_tolerance": 1e-9,
    }
    if snapshot.get("data_version") != current_version:
        report["status"] = "fail"
    encoded = json.dumps(report, indent=2, sort_keys=True, default=str)
    print(encoded)
    if args.report:
        args.report.write_text(encoded + "\n", encoding="utf-8")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
