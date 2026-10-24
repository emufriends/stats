"""Compare compact combination routes with their pre-optimization SQL.

Private, read-only regression check for the default completed-MW scope. It
does not query BigQuery or change the active generation.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from phase3_duckdb_service import GenerationManager, _load_duckdb
from phase4_local_routes import _next_card_action_sql, _next_card_endgame_sql
from phase4_local_scope import normalize_scope, scope_predicates


def _old_card_endgame(scope: dict) -> tuple[str, list[object]]:
    predicates, parameters = scope_predicates(scope, "g", hard_completed=False)
    return f"""
    WITH played AS (
      SELECT cp.card_name, cp.card_type, g.table_id, g.player, g.elo_delta, g.pre_match_elo
      FROM card_play_narrow cp JOIN source_full_sample g USING(table_id, player)
      WHERE {predicates}
    ), scored AS (
      SELECT p.*, TRIM(e.score.endgame) AS endgame_name
      FROM played p JOIN source_logs l USING(table_id, player)
      CROSS JOIN UNNEST(COALESCE(l.endgame_scores, [])) AS e(score)
      WHERE e.score.endgame IS NOT NULL
    ), cards AS (
      SELECT card_name, AVG(elo_delta) AS delta_card FROM played GROUP BY card_name
    ), endgames AS (
      SELECT endgame_name, AVG(elo_delta) AS delta_endgame FROM scored GROUP BY endgame_name
    ), pairs AS (
      SELECT card_name, ANY_VALUE(card_type) AS card_type, endgame_name,
        AVG(elo_delta) AS delta_actual, AVG(pre_match_elo) AS avg_elo, COUNT(*) AS n_played,
        STDDEV_SAMP(elo_delta) AS delta_actual_ci_sd, COUNT(elo_delta) AS delta_actual_ci_n
      FROM scored GROUP BY card_name, endgame_name
    )
    SELECT p.card_name, p.card_type, c.delta_card, p.endgame_name, e.delta_endgame,
      c.delta_card + e.delta_endgame AS delta_combined, p.delta_actual,
      p.delta_actual AS delta_actual_ci_mean, p.delta_actual_ci_sd, p.delta_actual_ci_n,
      p.delta_actual - c.delta_card - e.delta_endgame AS interaction,
      p.avg_elo, p.n_played
    FROM pairs p JOIN cards c USING(card_name) JOIN endgames e USING(endgame_name)
    ORDER BY interaction DESC NULLS LAST, n_played DESC, card_name, endgame_name
    LIMIT ? OFFSET ?
    """, parameters


def _old_card_action(scope: dict) -> tuple[str, list[object]]:
    predicates, parameters = scope_predicates(scope, "g", hard_completed=False)
    values = ", ".join(f"({n}, '{label}')" for n, label in (
        (1, "Animals"), (2, "Association"), (3, "Build"), (4, "Cards"), (5, "Sponsors")
    ))
    return f"""
    WITH actions AS (SELECT * FROM (VALUES {values}) v(action_number, action_card_name)),
    played AS (
      SELECT cp.card_name, cp.card_type, g.table_id, g.player, g.elo_delta, g.pre_match_elo,
        a.action_card_name
      FROM card_play_narrow cp JOIN source_full_sample g USING(table_id, player)
      CROSS JOIN actions a
      WHERE {predicates}
        AND TRY_CAST(CASE a.action_card_name
          WHEN 'Animals' THEN g.Animals_Action_Card_Number
          WHEN 'Association' THEN g.Association_Action_Card_Number
          WHEN 'Build' THEN g.Build_Action_Card_Number
          WHEN 'Cards' THEN g.Cards_Action_Card_Number
          ELSE g.Sponsors_Action_Card_Number END AS INTEGER) IS NOT NULL
    ), cards AS (SELECT card_name, AVG(elo_delta) AS delta_card FROM played GROUP BY card_name),
    actions_avg AS (SELECT action_card_name, AVG(elo_delta) AS delta_action FROM played GROUP BY action_card_name),
    pairs AS (
      SELECT card_name, ANY_VALUE(card_type) AS card_type, action_card_name,
        AVG(elo_delta) AS delta_actual, AVG(pre_match_elo) AS avg_elo, COUNT(*) AS n_played,
        STDDEV_SAMP(elo_delta) AS delta_actual_ci_sd, COUNT(elo_delta) AS delta_actual_ci_n
      FROM played GROUP BY card_name, action_card_name
    )
    SELECT p.card_name, p.card_type, c.delta_card, p.action_card_name,
      a.delta_action, c.delta_card + a.delta_action AS delta_combined, p.delta_actual,
      p.delta_actual AS delta_actual_ci_mean, p.delta_actual_ci_sd, p.delta_actual_ci_n,
      p.delta_actual - c.delta_card - a.delta_action AS interaction,
      p.avg_elo, p.n_played
    FROM pairs p JOIN cards c USING(card_name) JOIN actions_avg a USING(action_card_name)
    ORDER BY interaction DESC NULLS LAST, n_played DESC, card_name, action_card_name
    LIMIT ? OFFSET ?
    """, parameters


def _compare(connection, old_sql, old_params, new_sql, new_params, key_indices):
    # Fetch the complete bounded result rather than only the first page; tiny
    # floating-point ordering differences must not look like population drift.
    old_rows = connection.execute(old_sql, old_params + [100000, 0]).fetchall()
    new_rows = connection.execute(new_sql, new_params + [100000, 0]).fetchall()
    old_map = {tuple(row[index] for index in key_indices): row for row in old_rows}
    new_map = {tuple(row[index] for index in key_indices): row for row in new_rows}
    missing = sorted(set(old_map) - set(new_map), key=str)
    extra = sorted(set(new_map) - set(old_map), key=str)
    max_diff = 0.0
    for key in set(old_map) & set(new_map):
        for left, right in zip(old_map[key], new_map[key]):
            if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                if left is None or right is None:
                    continue
                if not (isinstance(left, float) and math.isnan(left)) and not (isinstance(right, float) and math.isnan(right)):
                    max_diff = max(max_diff, abs(float(left) - float(right)))
    sample_key = next(iter(set(old_map) & set(new_map)), None)
    return {
        "old_rows": len(old_rows),
        "new_rows": len(new_rows),
        "missing": missing[:5],
        "extra": extra[:5],
        "max_numeric_difference": max_diff,
        "sample_key": sample_key,
        "sample_old": old_map.get(sample_key),
        "sample_new": new_map.get(sample_key),
    }


def main() -> int:
    root = Path(__file__).resolve().parent
    manager = GenerationManager(root / "phase2_private_data" / "generations", root / "phase3_private_serving" / "current.json")
    generation = manager.current()
    duckdb = _load_duckdb()
    connection = duckdb.connect(str(generation.database_path), read_only=True)
    try:
        request = {
            "is_mw": 1,
            "completed_only": True,
            "maps": ["Map 1a: Observation Tower"],
        }
        scope = normalize_scope(request)
        new_endgame_sql, new_endgame_params = _next_card_endgame_sql(request)
        new_action_sql, new_action_params = _next_card_action_sql(request)
        report = {
            "generation": generation.generation_id,
            "data_version": generation.data_version,
            "scope": "mw_completed_map_1a",
            "card_endgame": _compare(connection, *_old_card_endgame(scope), new_endgame_sql, new_endgame_params, (0, 3)),
            "card_action_card": _compare(connection, *_old_card_action(scope), new_action_sql, new_action_params, (0, 3)),
        }
        output = root.parent / "ark-nova-stats-dashboard" / "analysis" / "phase4-combo-equivalence.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
