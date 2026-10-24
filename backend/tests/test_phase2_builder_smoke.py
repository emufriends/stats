import json
import pathlib
import sys
import unittest
import uuid
import shutil


ROOT = pathlib.Path(__file__).resolve().parents[1]
DUCKDB_PACKAGE = ROOT / "phase2_private_data" / "python314"
if DUCKDB_PACKAGE.exists():
    sys.path.insert(0, str(DUCKDB_PACKAGE))

from phase2_local_vertical_slice import run
from phase3_duckdb_service import Phase3RequestAdapter
from phase4_metadata import materialize_metadata_tables
from phase4_materialize_route_derivatives import _create_relations as create_arena_relations
from phase5_refresh_workflow import _materialize_records
from phase5_refresh_dependencies import LOG_RELATIONS
from phase4_local_routes import (
    _players_metric_sql, _next_opening_hand_sql, _next_predictor_sql,
    _next_route_sql, _remaining_route_sql, _simple_metric_sql,
    _final_route_sql, endgames_general_sql, maps_metrics_sql, scoring_sql,
)
from phase4_combo_mw_contracts import combination_sql, component_ci_sql, mw_action_cards_sql


class Phase2BuilderSmokeTests(unittest.TestCase):
    @staticmethod
    def _row_dicts(cursor):
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def test_real_schema_sample_builds_all_increment2_relations(self):
        try:
            import duckdb
        except ImportError:  # pragma: no cover - environment-specific
            self.skipTest("duckdb unavailable")
        generations = ROOT / "phase2_private_data" / "generations"
        candidates = sorted(generations.glob("*.duckdb"), key=lambda path: path.stat().st_mtime)
        if not candidates:
            self.skipTest("no local immutable generation")
        token = uuid.uuid4().hex
        database = ROOT / f".increment2-builder-{token}.duckdb"
        report = ROOT / f".increment2-builder-{token}.json"
        reuse_db = ROOT / f'.increment2-reuse-{token}.duckdb'
        reuse_report_path = ROOT / f'.increment2-reuse-{token}.json'
        fresh_db = ROOT / f'.increment2-fresh-{token}.duckdb'
        fresh_report_path = ROOT / f'.increment2-fresh-{token}.json'
        source = None
        for candidate in reversed(candidates):
            probe = duckdb.connect(str(candidate), read_only=True)
            try:
                tables = {row[0] for row in probe.execute(
                    'SELECT table_name FROM information_schema.tables'
                ).fetchall()}
                required = {'source_full_sample','source_logs','card_play_narrow'}
                if required.issubset(tables):
                    source = candidate
                    break
            finally:
                probe.close()
        if source is None:
            self.skipTest('No complete local source generation')
        connection = duckdb.connect(str(database))
        try:
            quoted_source = str(source).replace("'", "''")
            connection.execute(f"ATTACH '{quoted_source}' AS source (READ_ONLY)")
            connection.execute("""
                CREATE TEMP TABLE selected_ids AS
                SELECT DISTINCT table_id
                FROM source.card_play_narrow
                WHERE table_id IS NOT NULL AND is_mw = 1
                ORDER BY table_id DESC
                LIMIT 100
            """)
            connection.execute("""
                CREATE TABLE source_full_sample AS
                SELECT * FROM source.source_full_sample
                WHERE table_id IN (SELECT table_id FROM selected_ids)
            """)
            connection.execute("""
                CREATE TABLE source_logs AS
                SELECT * FROM source.source_logs
                WHERE table_id IN (SELECT table_id FROM selected_ids)
            """)
            materialize_metadata_tables(connection, [], [])
            moving = ROOT / "phase2_private_data" / "moving_sources"
            create_arena_relations(connection, ROOT)
            _materialize_records(connection, moving)
            connection.execute("DETACH source")
        finally:
            connection.close()
        try:
            self.assertEqual(
                run(
                    database,
                    report,
                    threads=1,
                    memory_limit="1200MB",
                    merge_players_path=ROOT / "merge_players.csv",
                ),
                0,
            )
            payload = json.loads(report.read_text(encoding="utf-8"))
            expected = {
                "game_player_narrow", "prepared_full_sample_narrow",
                "card_play_event_narrow",
                "opening_hand_narrow", "endgame_score_event_narrow",
                "mw_action_card_eligible_tables_narrow",
                "mw_action_card_selection_narrow",
            }
            self.assertTrue(expected.issubset(payload["relations"]))
            retired = {'sponsor_endgame_event_narrow', 'project_reward_event_narrow',
                       'action_history_event_narrow'}
            self.assertTrue(retired.isdisjoint(payload['relations']))
            self.assertTrue(
                payload["relations"]["prepared_full_sample_narrow"]["materialized"]
            )
            check = duckdb.connect(str(database), read_only=True)
            try:
                self.assertEqual(
                    check.execute(
                        "SELECT table_type FROM information_schema.tables "
                        "WHERE table_name = 'prepared_full_sample_narrow'"
                    ).fetchone()[0],
                "BASE TABLE",
                )
                self.assertEqual(check.execute("""
                    SELECT COUNT(*) FROM (
                      SELECT table_id, player, COUNT(*) AS dealt,
                        SUM(CASE WHEN kept THEN 1 ELSE 0 END) AS kept_n
                      FROM opening_hand_narrow GROUP BY table_id, player
                      HAVING dealt <> 8 OR kept_n > dealt
                    )
                """).fetchone()[0], 0)
                self.assertEqual(check.execute("""
                    SELECT COUNT(*) FROM (
                      SELECT table_id, player, COUNT(*) AS selected_n
                      FROM mw_action_card_selection_narrow
                      GROUP BY table_id, player HAVING selected_n <> 2
                    )
                """).fetchone()[0], 0)
                self.assertEqual(check.execute("""
                    SELECT COUNT(*) FROM (
                      SELECT table_id, player, card_type, card_name,
                        played_round, played_move, played_order, COUNT(*) AS n
                      FROM card_play_narrow
                      GROUP BY ALL HAVING n > 1
                    )
                """).fetchone()[0], 0)
                selected_player, selected_identity = check.execute(
                    """SELECT player, player_identity FROM game_player_narrow
                       WHERE is_mw = 1 ORDER BY table_id, player LIMIT 1"""
                ).fetchone()
                cards_request = Phase3RequestAdapter.normalize_request({
                    "stats_page": "cards", "is_mw": 1,
                    "rounds": ["1"], "player_elo_min": 0,
                    "opponent_elo_min": 0,
                })
                cards_sql, cards_parameters = Phase3RequestAdapter._cards_sql(cards_request)
                cards_cursor = check.execute(
                    cards_sql, [*cards_parameters, 100000, 0]
                )
                cards_rows = self._row_dicts(cards_cursor)
                self.assertTrue(cards_rows)
                card_row = cards_rows[0]
                direct_card = check.execute(
                    """SELECT AVG(cp.elo_delta), COUNT(DISTINCT cp.table_id)
                       FROM card_play_narrow cp
                       JOIN prepared_full_sample_narrow g USING(table_id, player)
                       WHERE g.is_mw = 1 AND NOT g.is_corrupted_game
                         AND cp.played_round = 1
                         AND cp.card_name = ? AND cp.card_type = ?""",
                    [card_row["card_name"], card_row["card_type"]],
                ).fetchone()
                # SQL sums and direct AVG may straddle a floating-point half
                # rounding boundary; Python round also has different tie rules.
                # Reconcile the unrounded mean and require correct 3dp accuracy.
                self.assertLessEqual(abs(card_row["delta_played"] - direct_card[0]), 0.0005 + 1e-12)
                self.assertAlmostEqual(card_row["delta_played_ci_mean"], direct_card[0])
                self.assertEqual(card_row["n_played"], direct_card[1])
                self.assertIsNone(card_row["delta_in_hand"])
                self.assertIsNone(card_row["n_seen"])
                players_request = Phase3RequestAdapter.normalize_request({
                    "stats_page": "players", "players_view": "general",
                    "is_mw": 1, "players_player": selected_player,
                })
                players_sql, players_parameters = _players_metric_sql(
                    players_request, "general"
                )
                players_cursor = check.execute(
                    players_sql, [*players_parameters, 100000, 0]
                )
                players_rows = self._row_dicts(players_cursor)
                self.assertTrue(players_rows)
                self.assertEqual(players_rows[0]["metric"], "Turns")
                self.assertNotIn("Games", {row["metric"] for row in players_rows})
                self.assertNotIn("Rounds", {row["metric"] for row in players_rows})
                turns_row = next(row for row in players_rows if row["metric"] == "Turns")
                direct_turns = check.execute(
                    """SELECT AVG(TRY_CAST(Number_of_turns AS DOUBLE)), COUNT(*)
                       FROM players_metrics_narrow
                       WHERE is_mw = 1 AND player_identity = ?""",
                    [selected_identity],
                ).fetchone()
                self.assertAlmostEqual(turns_row["player"], direct_turns[0])
                self.assertEqual(turns_row["count_player"], direct_turns[1])
                self.assertEqual(turns_row["player_identity"], selected_identity)

                opening_request = Phase3RequestAdapter.normalize_request({
                    "stats_page": "opening_hand", "is_mw": 1,
                    "player_elo_min": 0, "opponent_elo_min": 0,
                })
                opening_sql, opening_parameters = _next_opening_hand_sql(opening_request)
                opening_cursor = check.execute(
                    opening_sql, [*opening_parameters, 100000, 0]
                )
                opening_rows = self._row_dicts(opening_cursor)
                self.assertTrue(opening_rows)
                opening_row = next(row for row in opening_rows if row["n_seen"] > 0)
                direct_opening = check.execute(
                    """SELECT COUNT(*), COUNT(*) FILTER (WHERE h.kept),
                              AVG(g.elo_delta), AVG(g.elo_delta) FILTER (WHERE h.kept)
                       FROM opening_hand_narrow h
                       JOIN prepared_full_sample_narrow g USING(table_id, player)
                       WHERE g.is_mw = 1 AND NOT g.is_corrupted_game
                         AND h.card_name = ?""",
                    [opening_row["card_name"]],
                ).fetchone()
                self.assertEqual(opening_row["n_seen"], direct_opening[0])
                self.assertEqual(opening_row["n_played"], direct_opening[1])
                self.assertEqual(opening_row["delta_played"], round(direct_opening[2], 3))
                if direct_opening[3] is not None:
                    self.assertEqual(opening_row["delta_in_hand"], round(direct_opening[3], 3))

                players = [row[0] for row in check.execute(
                    """SELECT ANY_VALUE(player) AS player FROM game_player_narrow
                       WHERE is_mw = 1 GROUP BY player_identity
                       ORDER BY MIN(CAST(table_id AS VARCHAR)) LIMIT 2"""
                ).fetchall()]
                comparison_request = Phase3RequestAdapter.normalize_request({
                    "stats_page": "players", "players_view": "comparison",
                    "is_mw": 1, "players_players": players,
                })
                comparison_sql, comparison_parameters = _players_metric_sql(
                    comparison_request, "comparison"
                )
                comparison_rows = check.execute(
                    comparison_sql, [*comparison_parameters, 100000, 0]
                ).fetchall()
                self.assertTrue(comparison_rows)

                performance_request = Phase3RequestAdapter.normalize_request({
                    "stats_page": "players", "players_view": "performance_by_map",
                    "is_mw": 1, "players_players": players,
                })
                performance_sql, performance_parameters = _players_metric_sql(
                    performance_request, "performance_by_map"
                )
                check.execute(
                    performance_sql, [*performance_parameters, 100000, 0]
                ).fetchall()

                history_request = Phase3RequestAdapter.normalize_request({
                    "stats_page": "players", "players_view": "general",
                    "players_history": True, "players_player": selected_player,
                    "players_history_metrics": ["turns"], "is_mw": 1,
                })
                history_sql, history_parameters = Phase3RequestAdapter._players_history_sql(
                    history_request
                )
                check.execute(
                    history_sql, [*history_parameters, 100000, 0]
                ).fetchall()
                predictor_sql, predictor_parameters = _next_predictor_sql(
                    {"is_mw": 1}, "general"
                )
                check.execute(
                    predictor_sql, [*predictor_parameters, 100000, 0]
                ).fetchall()
                specific_sql, specific_parameters = _next_predictor_sql(
                    {"is_mw": 1}, "specific"
                )
                specific_rows = self._row_dicts(check.execute(
                    specific_sql, [*specific_parameters, 100000, 0]
                ))
                self.assertEqual(len(specific_rows), 19)
                self.assertNotIn("Round 1: Humphead Wrasse", {
                    row["condition"] for row in specific_rows
                })

                route_builders = [
                    (maps_metrics_sql, {"is_mw": 1}),
                    (endgames_general_sql, {"is_mw": 1}),
                    (scoring_sql, {"is_mw": 1, "scoring_view": "final_score"}),
                    *[(
                        _simple_metric_sql,
                        {"is_mw": 1, "simple_view": view},
                    ) for view in (
                        "build_enclosures", "build_hexes", "icons_default",
                        "conservation_projects", "conservation_project_rewards",
                        "workers_general", "workers_two_cp_worker",
                    )],
                    *[(
                        _next_route_sql,
                        {"is_mw": 1, "next_view": view},
                    ) for view in (
                        "endgames_cp_distribution", "endgames_cp_by_map",
                        "sponsor_endgames_cp", "sponsor_endgames_appeal",
                        "actions_starting_position", "conservation_cp_rewards",
                    )],
                    (_remaining_route_sql, {"remaining_view": "home"}),
                    *[(
                        _final_route_sql,
                        {"is_mw": 1, "final_view": f"records_{view}"},
                    ) for view in (
                        "elo_leaderboard", "fastest_games", "highest_scores",
                        "biggest_turns", "most_icons",
                    )],
                ]
                route_results = {}
                for builder, route_request in route_builders:
                    route_sql, route_parameters = builder(route_request)
                    rows = self._row_dicts(check.execute(
                        route_sql, [*route_parameters, 100000, 0]
                    ))
                    route_results[str(route_request)] = rows
                self.assertEqual(len(route_results[str({"remaining_view": "home"})]), 12)
                self.assertEqual(len(route_results[str({"is_mw": 1, "simple_view": "conservation_project_rewards"})]), 22)
                arena_sql, arena_parameters = _final_route_sql({
                    "final_view": "arena_top_100", "arena_season": "S13",
                    "arena_series_player_ids": [],
                })
                check.execute(arena_sql, arena_parameters).fetchall()

                combo_requests = {
                    view: {
                        "stats_page": "combinations", "combinations_view": view,
                        "is_mw": 1, "player_elo_min": 0, "opponent_elo_min": 0,
                        "combination_min_plays": 1,
                    }
                    for view in ("card_card", "card_map", "card_round", "card_endgame", "card_action_card")
                }
                combo_rows = {}
                for view, combo_request in combo_requests.items():
                    combo_sql, combo_parameters = combination_sql(combo_request, view)
                    combo_rows[view] = self._row_dicts(check.execute(
                        combo_sql, [*combo_parameters, 100000, 0]
                    ))
                    self.assertTrue(combo_rows[view], view)
                    self.assertNotIn("interaction_ci95_low", combo_rows[view][0])
                card_pair = combo_rows["card_card"][0]
                direct_pair = check.execute("""
                    WITH p AS (
                      SELECT DISTINCT table_id, player, card_name, elo_delta
                      FROM card_play_narrow
                      WHERE is_mw = 1 AND card_name IN (?, ?)
                    )
                    SELECT AVG(a.elo_delta), COUNT(*)
                    FROM p a JOIN p b USING(table_id, player)
                    WHERE a.card_name = ? AND b.card_name = ?
                """, [card_pair["card_1"], card_pair["card_2"], card_pair["card_1"], card_pair["card_2"]]).fetchone()
                self.assertEqual(card_pair["delta_actual"], round(direct_pair[0], 3))
                self.assertEqual(card_pair["n_played"], direct_pair[1])

                card_map = combo_rows["card_map"][0]
                direct_map = check.execute("""
                    WITH p AS (
                      SELECT DISTINCT table_id, player, card_name, map_name, elo_delta
                      FROM card_play_narrow WHERE is_mw = 1
                    )
                    SELECT AVG(elo_delta),
                      AVG(elo_delta) FILTER (WHERE map_name = ?),
                      COUNT(*) FILTER (WHERE map_name = ?)
                    FROM p WHERE card_name = ?
                """, [card_map["map_name"], card_map["map_name"], card_map["card_name"]]).fetchone()
                self.assertEqual(card_map["delta_general"], round(direct_map[0], 3))
                self.assertEqual(card_map["delta_map"], round(direct_map[1], 3))
                self.assertEqual(card_map["n_played"], direct_map[2])

                card_round = combo_rows["card_round"][0]
                direct_round = check.execute("""
                    WITH events AS (
                      SELECT DISTINCT table_id, player, card_name, played_round, elo_delta
                      FROM card_play_narrow WHERE is_mw = 1
                    ), cards AS (
                      SELECT DISTINCT table_id, player, card_name, elo_delta FROM events
                    )
                    SELECT (SELECT AVG(elo_delta) FROM cards WHERE card_name = ?),
                      AVG(elo_delta), COUNT(*)
                    FROM events WHERE card_name = ?
                      AND CASE WHEN played_round >= 6 THEN '6+' ELSE CAST(played_round AS VARCHAR) END = ?
                """, [card_round["card_name"], card_round["card_name"], card_round["round_name"]]).fetchone()
                self.assertEqual(card_round["delta_general"], round(direct_round[0], 3))
                self.assertEqual(card_round["delta_round"], round(direct_round[1], 3))
                self.assertEqual(card_round["n_played"], direct_round[2])

                card_endgame = combo_rows["card_endgame"][0]
                direct_endgame = check.execute("""
                    WITH p AS (
                      SELECT DISTINCT table_id, player, card_name, elo_delta
                      FROM card_play_narrow WHERE is_mw = 1
                    )
                    SELECT AVG(p.elo_delta), COUNT(*)
                    FROM p JOIN endgame_score_event_narrow e USING(table_id, player)
                    WHERE p.card_name = ? AND e.endgame_name = ?
                """, [card_endgame["card_name"], card_endgame["endgame_name"]]).fetchone()
                self.assertEqual(card_endgame["delta_actual"], round(direct_endgame[0], 3))
                self.assertEqual(card_endgame["n_played"], direct_endgame[1])

                card_action = combo_rows["card_action_card"][0]
                direct_action = check.execute("""
                    WITH p AS (
                      SELECT DISTINCT cp.table_id, cp.player, cp.card_name, cp.elo_delta
                      FROM card_play_narrow cp
                      JOIN mw_action_card_eligible_tables_narrow e USING(table_id)
                      WHERE cp.card_name = ?
                    )
                    SELECT AVG(p.elo_delta), COUNT(*)
                    FROM p JOIN mw_action_card_selection_narrow a USING(table_id, player)
                    WHERE a.card_key = ?
                """, [card_action["card_name"], card_action["action_card_key"]]).fetchone()
                self.assertEqual(card_action["delta_actual"], round(direct_action[0], 3))
                self.assertEqual(card_action["n_played"], direct_action[1])

                ci_descriptor = {"card_1": card_pair["card_1"], "card_2": card_pair["card_2"]}
                ci_sql, ci_parameters = component_ci_sql(
                    combo_requests["card_card"], "combinations", "card_card", [ci_descriptor]
                )
                ci_row = self._row_dicts(check.execute(
                    ci_sql, [*ci_parameters, 100, 0]
                ))[0]
                self.assertGreaterEqual(ci_row["component_1_ci95_cluster_n"], 2)
                self.assertGreaterEqual(ci_row["component_2_ci95_cluster_n"], 2)
                self.assertIsNotNone(ci_row["component_1_ci95_low"])
                self.assertIsNotNone(ci_row["component_2_ci95_high"])

                def assert_shared_component_batch(page, view, request, descriptor):
                    # Repeated first/second identities and absent observations
                    # must retain precisely the single-descriptor population.
                    keys = list(descriptor)
                    descriptors = [descriptor,
                        {**descriptor, keys[0]: 'No such component'},
                        {**descriptor, keys[1]: 'No such component'}]
                    sql, parameters = component_ci_sql(request, page, view, descriptors)
                    combined = self._row_dicts(check.execute(sql, [*parameters, 100, 0]))
                    by_key = {row['row_key']: row for row in combined}
                    self.assertEqual(len(by_key), 3)
                    for item in descriptors:
                        sql, parameters = component_ci_sql(request, page, view, [item])
                        expected = self._row_dicts(check.execute(sql, [*parameters, 100, 0]))[0]
                        observed = by_key[expected['row_key']]
                        self.assertEqual(set(expected), set(observed))
                        for key, value in expected.items():
                            if isinstance(value, float):
                                self.assertAlmostEqual(value, observed[key], places=12, msg=f'{view}/{key}')
                            else:
                                self.assertEqual(value, observed[key], f'{view}/{key}')

                assert_shared_component_batch('combinations', 'card_card',
                                              combo_requests['card_card'], ci_descriptor)

                component_descriptors = {
                    "card_map": {
                        "card_name": card_map["card_name"],
                        "map_name": card_map["map_name"],
                    },
                    "card_round": {
                        "card_name": card_round["card_name"],
                        "round_name": card_round["round_name"],
                    },
                    "card_endgame": {
                        "card_name": card_endgame["card_name"],
                        "endgame_name": card_endgame["endgame_name"],
                    },
                    "card_action_card": {
                        "card_name": card_action["card_name"],
                        "action_card_key": card_action["action_card_key"],
                    },
                }
                for ci_view, descriptor in component_descriptors.items():
                    ci_sql, ci_parameters = component_ci_sql(
                        combo_requests[ci_view], "combinations", ci_view, [descriptor]
                    )
                    ci_result = self._row_dicts(check.execute(
                        ci_sql, [*ci_parameters, 100, 0]
                    ))[0]
                    self.assertGreater(ci_result["component_1_ci95_n"], 0, ci_view)
                    self.assertGreater(ci_result["component_2_ci95_n"], 0, ci_view)
                    assert_shared_component_batch('combinations', ci_view,
                                                  combo_requests[ci_view], descriptor)

                mw_payloads = {}
                for view in ("general", "draft", "by_map", "synergies"):
                    mw_sql, mw_parameters = mw_action_cards_sql({
                        "stats_page": "mw_action_cards", "mw_action_cards_view": view,
                        "is_mw": 1, "player_elo_min": 0, "opponent_elo_min": 0,
                    }, view)
                    mw_rows = self._row_dicts(check.execute(
                        mw_sql, [*mw_parameters, 100000, 0]
                    ))
                    self.assertTrue(mw_rows, view)
                    mw_payloads[view] = mw_rows
                    if view in {"general", "draft", "by_map"}:
                        self.assertEqual(len(mw_rows), 20)
                        self.assertEqual([row["card_order"] for row in mw_rows], list(range(1, 21)))
                self.assertEqual(mw_payloads["general"], mw_payloads["draft"])
                general = next(row for row in mw_payloads["general"] if row["picked_n"] > 0)
                direct_general = check.execute(
                    "SELECT AVG(elo_delta), COUNT(*) FROM mw_action_card_selection_narrow WHERE card_order = ?",
                    [general["card_order"]],
                ).fetchone()
                self.assertEqual(general["delta_picked"], round(direct_general[0], 3))
                self.assertEqual(general["delta_picked_ci_n"], direct_general[1])
                synergy = mw_payloads["synergies"][0]
                assert_shared_component_batch('mw_action_cards', 'synergies', {
                    'stats_page': 'mw_action_cards', 'is_mw': 1,
                    'player_elo_min': 0, 'opponent_elo_min': 0,
                }, {'card_1_key': synergy['card_1_key'], 'card_2_key': synergy['card_2_key']})
                direct_synergy = check.execute("""
                    SELECT AVG(elo_delta), COUNT(*) FROM mw_action_card_pair_narrow
                    WHERE card_1_key = ? AND card_2_key = ?
                """, [synergy["card_1_key"], synergy["card_2_key"]]).fetchone()
                self.assertEqual(synergy["delta_actual"], round(direct_synergy[0], 3))
                self.assertEqual(synergy["n_picked"], direct_synergy[1])
            finally:
                check.close()
            # New Full Sample games without new Logs must not force a rebuild
            # of unchanged card/log facts. Compare reuse against a fresh producer,
            # not merely against the parent's cached output.
            shutil.copy2(database,reuse_db)
            change = duckdb.connect(str(reuse_db))
            try:
                new_id = change.execute('SELECT MAX(table_id)+1 FROM source_full_sample').fetchone()[0]
                template = change.execute('SELECT table_id FROM source_full_sample GROUP BY table_id HAVING COUNT(*)=2 LIMIT 1').fetchone()[0]
                change.execute('INSERT INTO source_full_sample SELECT * REPLACE(? AS table_id) FROM source_full_sample WHERE table_id=?',[new_id,template])
            finally:
                change.close()
            self.assertEqual(run(reuse_db,reuse_report_path,threads=1,memory_limit='1200MB',
                                 merge_players_path=ROOT/'merge_players.csv',
                                 reuse_database=database,reuse_report=payload),0)
            reused_payload=json.loads(reuse_report_path.read_text())
            self.assertEqual(set(reused_payload['reused_relations']),set(LOG_RELATIONS))
            shutil.copy2(reuse_db,fresh_db)
            self.assertEqual(run(fresh_db,fresh_report_path,threads=1,memory_limit='1200MB',
                                 merge_players_path=ROOT/'merge_players.csv'),0)
            compare=duckdb.connect(str(reuse_db),read_only=True)
            try:
                quoted=str(fresh_db).replace("'","''")
                compare.execute(f"ATTACH '{quoted}' AS fresh (READ_ONLY)")
                for name in reused_payload['relations']:
                    difference=compare.execute(f'''SELECT COUNT(*) FROM (
                        (SELECT * FROM main.{name} EXCEPT ALL SELECT * FROM fresh.{name})
                        UNION ALL
                        (SELECT * FROM fresh.{name} EXCEPT ALL SELECT * FROM main.{name}))''').fetchone()[0]
                    self.assertEqual(difference,0,name)
            finally:
                compare.close()
        finally:
            database.unlink(missing_ok=True)
            report.unlink(missing_ok=True)
            for path in (reuse_db,reuse_report_path,fresh_db,fresh_report_path):
                path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
