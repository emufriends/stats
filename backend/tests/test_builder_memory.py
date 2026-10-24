import json
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from phase5_snapshot_builder import _write_json, _build_pack, build_arena_bundle, _bundle_payload, DEFAULT_PACK_SCHEMA_VERSION, OfflineDiskResponseCache, _arena_season_response, _arena_offline_histories
from phase5_refresh_metrics import rss_current_bytes
from phase5_offline_stage import invoke, execute
from phase3_duckdb_service import _load_duckdb, Phase3PersistentResponseCache, _project_arena_bundle
from phase4_local_routes import _final_arena_sql
from phase5_builder_memory_benchmark import exact_differences, table_moment_differences
from phase2_local_vertical_slice import canonical_update_scopes, create_seen_card_relation, create_card_play_filter_summary, create_card_filter_core_relation, create_mw_action_card_draft_relation, create_card_table_filter_relations, create_home_log_feature_relation
from reports.compare_snapshot_memory_20261002 import JSONReader, compare_arena, compare, normalize_record_ties, read_home_bootstrap
import phase5_refresh_worker as refresh_worker


class BuilderMemoryTests(unittest.TestCase):
    def test_home_bootstrap_comparison_parses_data_not_executable_content(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'defaults.js'
            valid = 'window.__ARK_NOVA_DATA_VERSION__="v";window.__ARK_NOVA_HOME_DEFAULTS__={"1":{"count":2}};'
            path.write_text(valid, encoding='utf-8')
            self.assertEqual(read_home_bootstrap(path), {'data_version':'v','defaults':{'1':{'count':2}}})
            path.write_text(valid + 'alert("unexpected");', encoding='utf-8')
            with self.assertRaises(ValueError):
                read_home_bootstrap(path)

    def test_home_opponent_summary_preserves_distinct_null_and_multi_player_semantics(self):
        c = _load_duckdb().connect()
        try:
            c.execute('''CREATE TABLE source_logs AS SELECT table_id, player,
              CASE WHEN proboscis THEN [{'animal':'Proboscis Monkey'}] ELSE [] END AS played_animals,
              CAST([] AS STRUCT(project VARCHAR)[]) AS played_projects,
              CAST([] AS STRUCT(sponsor VARCHAR)[]) AS played_sponsors,
              ['Primates'] AS cards_drawn, FALSE AS "2cp_worker",
              NULL::VARCHAR AS chosen_5cp_bonus, NULL::VARCHAR AS chosen_8cp_bonus,
              0 AS petting_zoo_built
              FROM (VALUES (1,'a',TRUE),(1,'a',TRUE),(1,'b',FALSE),
                (2,'a',TRUE),(2,'b',TRUE),(2,'c',FALSE),
                (3,NULL,TRUE),(3,'a',FALSE),(NULL,'a',TRUE)) t(table_id,player,proboscis)''')
            create_home_log_feature_relation(c)
            differences = c.execute('''SELECT COUNT(*) FROM (
              SELECT f.table_id, f.player,
                EXISTS(SELECT 1 FROM home_log_feature_narrow other
                  WHERE other.table_id=f.table_id AND other.player<>f.player
                    AND other.has_proboscis) AS expected,
                COALESCE(f.player IS NOT NULL AND
                  (p.proboscis_players>1 OR (p.proboscis_players=1
                    AND f.player<>p.only_proboscis_player)),FALSE) AS actual
              FROM home_log_feature_narrow f
              LEFT JOIN home_proboscis_table_narrow p ON p.table_id=f.table_id
            ) WHERE expected IS DISTINCT FROM actual''').fetchone()[0]
            self.assertEqual(differences, 0)
        finally:
            c.close()

    def test_scalar_home_lists_match_correlated_queries_with_duplicates_and_nulls(self):
        c=_load_duckdb().connect()
        try:
            c.execute('''CREATE TABLE source_logs AS SELECT * FROM (VALUES
              (1,'a',[{'animal':'Emu'},{'animal':'Emu'},{'animal':'Proboscis Monkey'},NULL],
                [{'project':'Other'},NULL],[{'sponsor':'Other'},NULL],['Primates',NULL],TRUE,'1 University','1 Partner-Zoo',1),
              (1,'b',[{'animal':'emu'}],[{'project':'Primates'}],[{'sponsor':'Horse Whisperer'}],['Primates'],NULL,NULL,NULL,1),
              (2,'a',NULL,NULL,NULL,NULL,FALSE,'Other','Other',NULL),
              (3,'a',[NULL],[NULL],[NULL],[NULL],FALSE,NULL,NULL,1),
              (4,'a',[],[],[],[],TRUE,NULL,NULL,0))
              t(table_id,player,played_animals,played_projects,played_sponsors,cards_drawn,
                "2cp_worker",chosen_5cp_bonus,chosen_8cp_bonus,petting_zoo_built)''')
            c.execute('''CREATE TABLE expected AS SELECT l.table_id,l.player,
              (SELECT COUNT(*) FROM UNNEST(COALESCE(l.played_animals,[])) a(e) WHERE e.animal='Emu')::BIGINT AS emus_played,
              COALESCE(l."2cp_worker",FALSE)::BIGINT AS two_cp_workers_taken,
              (CASE WHEN l.chosen_5cp_bonus IN ('1 University','1 Partner-Zoo') THEN 1 ELSE 0 END
                + CASE WHEN l.chosen_8cp_bonus IN ('1 University','1 Partner-Zoo') THEN 1 ELSE 0 END)::BIGINT AS free_unis_and_partner_zoos,
              (LIST_CONTAINS(COALESCE(l.cards_drawn,CAST([] AS VARCHAR[])),'Primates')
                AND NOT EXISTS(SELECT 1 FROM UNNEST(COALESCE(l.played_projects,[])) p(e) WHERE e.project='Primates')) AS primates_candidate,
              (SELECT COUNT(*) FROM UNNEST(COALESCE(l.played_animals,[])) a(e) WHERE e.animal='Proboscis Monkey')>0 AS has_proboscis,
              COALESCE(TRY_CAST(l.petting_zoo_built AS INTEGER),0)=1
                AND NOT EXISTS(SELECT 1 FROM UNNEST(COALESCE(l.played_sponsors,[])) s(e) WHERE e.sponsor='Horse Whisperer') AS empty_petting_candidate
              FROM source_logs l''')
            create_home_log_feature_relation(c)
            self.assertEqual(c.execute('''SELECT COUNT(*) FROM (
              (SELECT * FROM expected EXCEPT ALL SELECT * FROM home_log_feature_narrow)
              UNION ALL
              (SELECT * FROM home_log_feature_narrow EXCEPT ALL SELECT * FROM expected))''').fetchone()[0],0)
            self.assertEqual(c.execute('DESCRIBE expected').fetchall(),c.execute('DESCRIBE home_log_feature_narrow').fetchall())
        finally:
            c.close()

    def test_batched_table_moments_preserve_complete_table_groups_and_nulls(self):
        c = _load_duckdb().connect()
        try:
            c.execute('''CREATE TABLE game_player_narrow AS
              SELECT table_id,is_mw,elo AS pre_match_elo,map AS map_name,
                TIMESTAMP '2026-01-01' AS game_ended_at,completed AS is_completed_game,
                'S13' AS arena_season,TRUE AS is_arena_game,FALSE AS is_tournament,
                bad AS is_corrupted_game
              FROM (VALUES (1,1,700,'1a',TRUE,FALSE),(1,1,300,'1a',TRUE,FALSE),
                (2,0,NULL,'2a',FALSE,FALSE),(2,0,600,'2a',FALSE,FALSE),
                (3,1,500,'1a',TRUE,TRUE),(NULL,1,500,'1a',TRUE,FALSE))
                t(table_id,is_mw,elo,map,completed,bad)''')
            for dataset in ('mw','base'):
                c.execute(f'''CREATE TABLE card_filter_fact_{dataset}_narrow AS
                  SELECT * FROM (VALUES (1,'X','animal',2,1.25,700,1,1),
                    (1,'X','animal',1,-1.0,300,0,1),
                    (2,'Y','sponsor',1,NULL,NULL,1,1),
                    (2,'Z','project',0,0.5,600,1,1),
                    (3,'W','animal',1,2.0,500,1,1),
                    (NULL,'N','animal',1,1.0,500,1,1))
                    t(table_id,card_name,card_type,played_count,elo_delta,pre_match_elo,in_hand,seen)''')
            create_card_table_filter_relations(c,1)
            for dataset in ('mw','base'):
                c.execute(f'CREATE TABLE expected_{dataset} AS SELECT * FROM card_filter_table_fact_{dataset}_narrow')
            for batches in (2,32):
                create_card_table_filter_relations(c,batches)
                for dataset in ('mw','base'):
                    difference=c.execute(f'''SELECT COUNT(*) FROM (
                      (SELECT * FROM expected_{dataset} EXCEPT ALL SELECT * FROM card_filter_table_fact_{dataset}_narrow)
                      UNION ALL
                      (SELECT * FROM card_filter_table_fact_{dataset}_narrow EXCEPT ALL SELECT * FROM expected_{dataset}))''').fetchone()[0]
                    self.assertEqual(difference,0)
            with self.assertRaises(ValueError):
                create_card_table_filter_relations(c,0)
        finally:
            c.close()

    def test_batched_mw_draft_matches_original_table_population(self):
        c = _load_duckdb().connect()
        try:
            c.execute("""CREATE TABLE prepared_full_sample_narrow AS
                SELECT table_id, player, starting_position, elo AS pre_match_elo,
                    map AS Map, TIMESTAMP '2026-01-01' AS game_ended_at,
                    TRUE AS is_completed_game, TRUE AS is_arena_game,
                    'S13' AS arena_season, FALSE AS is_tournament,
                    first_card AS First_drafted_action_card,
                    second_card AS Second_drafted_action_card,
                    third_card AS Third_drafted_action_card, ['unused'] AS wide_unused
                FROM (VALUES
                    (1,'a','First player',700,'1a','Animals 1','Build 1','Cards 1'),
                    (1,'b','Second player',300,'2a','Cards 1','Animals 1','Sponsors 1'),
                    (2,'c','Second player',NULL,'1a','Build 1','Cards 1','Animals 1'),
                    (2,'d','First player',600,'1a','Animals 1','Cards 1','Build 1'),
                    (3,'e','First player',500,'1a','Animals 1','Build 1','Cards 1')
                ) t(table_id,player,starting_position,elo,map,first_card,second_card,third_card)""")
            c.execute("CREATE TABLE mw_action_card_eligible_tables_narrow AS SELECT * FROM (VALUES (1),(2)) t(table_id)")
            c.execute("""CREATE TABLE mw_action_card_catalog_narrow AS
                SELECT * FROM (VALUES (1,'Animals',1,'A','Animals 1'),
                    (2,'Build',1,'B','Build 1'),(3,'Cards',1,'C','Cards 1'),
                    (4,'Sponsors',1,'S','Sponsors 1'))
                t(card_order,card_type,card_number,card_name,card_key)""")
            c.execute("""CREATE TABLE mw_action_card_selection_narrow AS
                SELECT * FROM (VALUES (1,'Animals 1'),(1,'Build 1'),(1,'Cards 1'),
                    (2,'Animals 1'),(2,'Cards 1')) t(table_id,card_key)""")
            c.execute("""
            CREATE TABLE expected_draft AS
            WITH ranked AS (
              SELECT f.*,
                ROW_NUMBER() OVER (
                  PARTITION BY f.table_id
                  ORDER BY CASE f.starting_position WHEN 'First player' THEN 1 ELSE 2 END,
                    f.player
                ) AS player_position
              FROM prepared_full_sample_narrow f
              JOIN mw_action_card_eligible_tables_narrow eligible USING(table_id)
            )
            , paired AS (
              SELECT table_id,
                MAX(CASE WHEN player_position = 1 THEN pre_match_elo END) AS first_pre_match_elo,
                MAX(CASE WHEN player_position = 2 THEN pre_match_elo END) AS second_pre_match_elo,
                MAX(CASE WHEN player_position = 1 THEN Map END) AS first_map,
                MAX(CASE WHEN player_position = 2 THEN Map END) AS second_map,
                MAX(game_ended_at) AS game_ended_at,
                BOOL_AND(is_completed_game) AS is_completed_game,
                BOOL_OR(is_arena_game) AS is_arena_game,
                MAX(arena_season) AS arena_season,
                BOOL_OR(is_tournament) AS is_tournament,
                MAX(CASE WHEN player_position = 1 THEN First_drafted_action_card END) AS p1_first,
                MAX(CASE WHEN player_position = 2 THEN First_drafted_action_card END) AS p2_first,
                MAX(CASE WHEN player_position = 1 THEN Second_drafted_action_card END) AS p1_second,
                MAX(CASE WHEN player_position = 2 THEN Second_drafted_action_card END) AS p2_second,
                MAX(CASE WHEN player_position = 1 THEN Third_drafted_action_card END) AS p1_third,
                MAX(CASE WHEN player_position = 2 THEN Third_drafted_action_card END) AS p2_third
              FROM ranked GROUP BY table_id
            ), selected AS (
              SELECT table_id, LIST(card_key) AS selected_cards
              FROM mw_action_card_selection_narrow GROUP BY table_id
            )
            SELECT p.table_id, p.first_pre_match_elo, p.second_pre_match_elo,
              p.first_map, p.second_map, p.game_ended_at, p.is_completed_game,
              p.is_arena_game, p.arena_season, p.is_tournament,
              c.card_order, c.card_type, c.card_number, c.card_name, c.card_key,
              LIST_CONTAINS(s.selected_cards, c.card_key) AS picked,
              c.card_key IN (p.p1_first, p.p2_first) AS drafted_first,
              c.card_key IN (p.p1_second, p.p2_second) AS drafted_second,
              c.card_key IN (p.p1_third, p.p2_third) AS undrafted
            FROM paired p JOIN selected s USING(table_id)
            CROSS JOIN mw_action_card_catalog_narrow c
            WHERE c.card_key IN (
              p.p1_first, p.p2_first, p.p1_second, p.p2_second, p.p1_third, p.p2_third
            )
        """)
            for batches in (1,2,32):
                rows = create_mw_action_card_draft_relation(c, batches)
                self.assertEqual(rows,7)
                differences = c.execute("""SELECT COUNT(*) FROM (
                    (SELECT * FROM expected_draft EXCEPT ALL SELECT * FROM mw_action_card_draft_narrow)
                    UNION ALL
                    (SELECT * FROM mw_action_card_draft_narrow EXCEPT ALL SELECT * FROM expected_draft))""").fetchone()[0]
                self.assertEqual(differences,0)
            with self.assertRaises(ValueError):
                create_mw_action_card_draft_relation(c,0)
        finally:
            c.close()

    def test_generation_comparison_only_permits_verified_manifest_pair(self):
        with mock.patch('reports.compare_snapshot_memory_20261002.AUTHORIZED_GENERATION_CHANGE', ('old','new')):
            differences = []
            compare('old','new','payload/generation',differences)
            self.assertEqual(differences,[])
            compare('old','unexpected','payload/generation',differences)
            self.assertTrue(differences)
            differences = []
            compare('old','new','payload/data_version',differences)
            self.assertTrue(differences)

    def test_metadata_native_work_runs_in_fresh_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'tournament-metadata.json').write_text(json.dumps({'rows': [
                {'table_id': 42,'tournament_name': 'T','season': 'S'}], 'source': {'state': 'fresh'}}))
            (root/'arena.csv').write_text('Season,Start (UTC),End (UTC),Mode\nS1,2026-01-01,2026-02-01,MW\n')
            result = invoke('metadata', {'database': root/'candidate.duckdb',
                'previous_database': root/'not-needed.duckdb','moving_source_dir': root,
                'arena_settings': root/'arena.csv','threads': 1,'memory_limit': '64MB',
                'temp_directory': root/'spill'}, root/'metadata-result.json')
            self.assertEqual(result['status'],'ok')
            self.assertEqual(result['tournament_info']['state'],'fresh')
            c = _load_duckdb().connect(str(root/'candidate.duckdb'), read_only=True)
            try:
                self.assertEqual(c.execute('SELECT table_id FROM tournament_tables_metadata').fetchall(),[(42,)])
                self.assertEqual(c.execute('SELECT season,mode FROM arena_seasons_metadata').fetchall(),[('S1','mw')])
            finally:
                c.close()
            self.assertFalse((root/'metadata-result.input.json').exists())

    def test_roster_stage_returns_counts_and_closes_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = {'database': root/'candidate.duckdb','previous_database': root/'previous.duckdb',
                        'moving_source_dir': root,'threads': 1,'memory_limit': '64MB','temp_directory': root/'spill'}
            def arena(c, moving):
                c.execute('CREATE TABLE arena_fixture AS SELECT 7 AS value')
                return {'arena_fixture': 1}
            def records(c, moving, previous):
                c.execute('CREATE TABLE records_fixture AS SELECT 9 AS value')
                return {'records_fixture': 1}
            with mock.patch('phase4_materialize_route_derivatives._create_relations', side_effect=arena), \
                 mock.patch('phase5_refresh_workflow._materialize_records', side_effect=records):
                result = execute({'stage': 'rosters_records','configuration': settings})
            self.assertEqual(result['arena_counts'],{'arena_fixture': 1})
            self.assertEqual(result['record_counts'],{'records_fixture': 1})
            c = _load_duckdb().connect(str(root/'candidate.duckdb'), read_only=True)
            try:
                self.assertEqual(c.execute('SELECT value FROM records_fixture').fetchall(),[(9,)])
            finally:
                c.close()

    def test_moment_qualification_rejects_population_or_map_drift(self):
        c = _load_duckdb().connect()
        try:
            c.execute("ATTACH ':memory:' AS baseline")
            c.execute("CREATE TABLE game_player_narrow AS SELECT * FROM (VALUES (1,1,'a'),(1,1,'b')) t(table_id,is_mw,map_name)")
            c.execute('CREATE TABLE baseline.game_player_narrow AS SELECT * FROM main.game_player_narrow')
            c.execute("CREATE TABLE card_filter_table_fact_mw_narrow AS SELECT 1 AS table_id,'x' AS card_name,1 AS is_mw,'a' AS Map,2 AS played_n,1.0::DOUBLE AS played_sum,2.0::DOUBLE AS played_sumsq,3.0::DOUBLE AS pre_match_sum,4.0::DOUBLE AS hand_sum,5.0::DOUBLE AS hand_sumsq")
            c.execute('CREATE TABLE baseline.card_filter_table_fact_mw_narrow AS SELECT * FROM main.card_filter_table_fact_mw_narrow')
            c.execute("UPDATE main.card_filter_table_fact_mw_narrow SET Map='b',played_sum=1.0000000000000002")
            self.assertEqual(table_moment_differences(c,'card_filter_table_fact_mw_narrow','TRUE',[]),(0,1,1))
            for assignment in ("Map='invalid'", 'played_n=3', 'played_sum=1.01', 'played_sum=NULL'):
                c.execute('DELETE FROM main.card_filter_table_fact_mw_narrow')
                c.execute('INSERT INTO main.card_filter_table_fact_mw_narrow SELECT * FROM baseline.card_filter_table_fact_mw_narrow')
                c.execute('UPDATE main.card_filter_table_fact_mw_narrow SET '+assignment)
                self.assertEqual(table_moment_differences(c,'card_filter_table_fact_mw_narrow','TRUE',[])[0],1)
        finally:
            c.close()

    def test_fast_exact_reconciliation_matches_multiset_nulls_and_duplicates(self):
        connection = _load_duckdb().connect()
        try:
            connection.execute("ATTACH ':memory:' AS baseline")
            connection.execute("CREATE TABLE card_seen_narrow(table_id INTEGER,player VARCHAR,card_name VARCHAR,value INTEGER)")
            connection.execute("CREATE TABLE baseline.card_seen_narrow AS SELECT * FROM main.card_seen_narrow")
            for rows_before, rows_after in (
                ([(1,'a','x',None),(None,'b','y',1)],[(None,'b','y',1),(1,'a','x',None)]),
                ([(1,'a','x',1)],[(1,'a','x',2)]),
                ([(1,'a','x',1)],[(2,'a','x',1)]),
                ([(1,'a','x',1),(1,'a','x',2)],[(1,'a','x',2),(1,'a','x',1)]),
                ([(1,'a','x',1),(1,'a','x',1)],[(1,'a','x',1)]),
            ):
                connection.execute('DELETE FROM main.card_seen_narrow')
                connection.execute('DELETE FROM baseline.card_seen_narrow')
                connection.executemany('INSERT INTO main.card_seen_narrow VALUES (?,?,?,?)', rows_before)
                connection.executemany('INSERT INTO baseline.card_seen_narrow VALUES (?,?,?,?)', rows_after)
                reference = connection.execute('''SELECT COUNT(*) FROM (
                    (SELECT * FROM main.card_seen_narrow EXCEPT ALL SELECT * FROM baseline.card_seen_narrow)
                    UNION ALL
                    (SELECT * FROM baseline.card_seen_narrow EXCEPT ALL SELECT * FROM main.card_seen_narrow))''').fetchone()[0]
                self.assertEqual(exact_differences(connection, 'card_seen_narrow', 'TRUE', []), reference)
        finally:
            connection.close()

    def test_history_only_sql_matches_full_arena_population_and_series(self):
        connection = _load_duckdb().connect()
        try:
            connection.execute("CREATE TABLE arena_seasons_metadata AS SELECT 'S1' AS season,'mw' AS mode,TIMESTAMPTZ '2026-01-01' AS start_utc,TIMESTAMPTZ '2026-02-01' AS end_utc")
            connection.execute("CREATE TABLE arena_roster_narrow AS SELECT * FROM (VALUES ('S1',1,'c',3,100),('S1',2,'a',1,200),('S1',3,'b',2,300)) t(season,rank,player,player_id,ending_rating)")
            connection.execute('''CREATE TABLE prepared_full_sample_narrow AS SELECT
                table_id,player,player_id,is_mw,TIMESTAMPTZ '2026-01-01' + day*INTERVAL 1 DAY AS game_ended_at,
                rating::DOUBLE AS post_match_arena_rating,1.0 AS arena_rating_delta,
                1 AS Game_result,300.0 AS opponent_pre_match_elo,30 AS Number_of_turns,
                2.0 AS points_per_turn,TRUE AS is_completed_game FROM (VALUES
                (1,'a',1,1,3,111),(2,'a',1,1,1,110),(3,'b',2,1,2,NULL),
                (4,'c',3,1,4,333),(5,'c',3,1,5,999),(6,'a',1,0,2,888),
                (7,'b',2,1,31,777)) t(table_id,player,player_id,is_mw,day,rating)''')
            connection.execute('CREATE TABLE corrupted_tables_narrow AS SELECT 5 AS table_id')
            class Store:
                def query(self, sql, parameters):
                    cursor = connection.execute(sql, parameters)
                    columns = [entry[0] for entry in cursor.description]
                    return {'columns': columns, 'rows': [dict(zip(columns, row)) for row in cursor.fetchall()]}
            class Adapter:
                store = Store()
            def full(ids):
                sql, parameters = _final_arena_sql({'arena_series_player_ids': ids})
                return {'data_version': 'v', 'data': _project_arena_bundle(Adapter.store.query(sql, parameters)['rows'])}
            expected, roster = full([1,2,3]), full([])
            with mock.patch.dict('os.environ', {'DUCKDB_ARENA_SERIES_BATCH': '2'}):
                result = _arena_offline_histories(Adapter(), roster, 'S1', [1,2,3])
            self.assertEqual(result['data'], expected['data'])
            self.assertEqual(result['data']['S1']['series'][1]['ratings'], [110.0,111.0])
            self.assertEqual(result['data']['S1']['series'][2]['ratings'], [])
            self.assertEqual(roster['data']['S1']['series'][0]['ratings'], [])
            with self.assertRaises(ValueError):
                _final_arena_sql({}, histories_only=True)
        finally:
            connection.close()

    def test_arena_history_batches_keep_full_roster_points_and_rank_order(self):
        ids = [3, 1, 2, None]
        rows = [{'rank': rank, 'player_id': player, 'player': str(player), 'games': 10}
                for rank, player in enumerate(ids, 1)]
        calls = []
        class Adapter:
            def execute(self, request):
                selected = request['arena_series_player_ids']
                calls.append(selected)
                series = [{**{key: row[key] for key in ('rank','player_id','player')},
                           'timestamps': ['date'] if row['player_id'] in selected else [],
                           'ratings': [row['player_id']] if row['player_id'] in selected else []}
                          for row in rows]
                return {'data_version': 'v', 'data': {'S1': {'rows': rows, 'series': series}}}
        expected = Adapter().execute({'arena_series_player_ids': [1,2,3]})
        calls.clear()
        actual = _arena_season_response(Adapter(), {}, 'S1', [1,2,3], chunk=2)
        self.assertEqual(actual, expected)
        self.assertEqual(calls, [[1,2],[3]])
        self.assertEqual(_arena_season_response(Adapter(), {}, 'S1', [], chunk=2),
                         Adapter().execute({'arena_series_player_ids': []}))
        with self.assertRaises(ValueError):
            _arena_season_response(Adapter(), {}, 'S1', [1], chunk=0)

    def test_card_core_batches_preserve_union_antijoins_and_null_behavior(self):
        connection = _load_duckdb().connect()
        try:
            connection.execute("CREATE TABLE game_player_narrow AS SELECT * FROM (VALUES (1,'a',1),(1,'b',0),(2,'a',1),(NULL,'c',1)) t(table_id,player,is_mw)")
            connection.execute("CREATE TABLE card_seen_narrow AS SELECT * FROM (VALUES (1,'a','X'),(1,'a','S'),(1,'a',NULL),(3,'a','stray')) t(table_id,player,card_name)")
            connection.execute("CREATE TABLE card_in_hand_narrow AS SELECT * FROM (VALUES (1,'a','X'),(1,'a','H'),(1,'a',NULL),(3,'a','stray')) t(table_id,player,card_name)")
            connection.execute("CREATE TABLE card_play_narrow AS SELECT * FROM (VALUES (1,'a','X','animal',1),(1,'a','X','animal',2),(1,'a','P','sponsor',3),(1,'a',NULL,'project',1),(1,'b','B','animal',1),(2,'a','Q','animal',2),(NULL,'c','Z','animal',3)) t(table_id,player,card_name,card_type,played_round)")
            create_card_play_filter_summary(connection, 1)
            count = create_card_filter_core_relation(connection, 1)
            connection.execute('CREATE TABLE expected AS SELECT * FROM card_filter_fact_narrow')
            for batches in (2, 32):
                self.assertEqual(create_card_filter_core_relation(connection, batches), count)
                different = connection.execute('''SELECT COUNT(*) FROM (
                    (SELECT * FROM expected EXCEPT ALL SELECT * FROM card_filter_fact_narrow)
                    UNION ALL
                    (SELECT * FROM card_filter_fact_narrow EXCEPT ALL SELECT * FROM expected))''').fetchone()[0]
                self.assertEqual(different, 0)
            row = connection.execute("SELECT played_count,played_r1,played_r2,in_hand,seen FROM card_filter_fact_narrow WHERE card_name='X'").fetchone()
            self.assertEqual(row, (2, 1, 1, 1, 1))
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM card_filter_fact_narrow WHERE table_id IS NULL OR table_id=3').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM card_filter_fact_narrow WHERE card_name IS NULL').fetchone()[0], 3)
        finally:
            connection.close()

    def test_offline_cache_reuses_disk_without_retaining_decoded_copies(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = OfflineDiskResponseCache(persistent=Phase3PersistentResponseCache(Path(directory)/'cache.sqlite3'))
            value = {'generation': 'g', 'data_version': 'v', 'data': [{'value': 1}]}
            cache.put('key', value)
            value['data'][0]['value'] = 2
            first = cache.get('key')
            self.assertEqual(first['data'][0]['value'], 1)
            first['data'][0]['value'] = 3
            self.assertEqual(cache.get('key')['data'][0]['value'], 1)
            self.assertEqual(cache._items, {})
            self.assertEqual(cache._order, [])
            self.assertIsNone(cache.get('absent'))

    def test_round_component_half_boundary_requires_matching_mean_and_count(self):
        before = {'delta_round': -.083, 'delta_round_ci_mean': -.08250000000000002,
                  'delta_round_ci_n': 42}
        after = {'delta_round': -.082, 'delta_round_ci_mean': -.08249999999999998,
                 'delta_round_ci_n': 42}
        differences, ties = [], []
        compare(before, after, 'row', differences, ties)
        self.assertEqual(differences, [])
        self.assertEqual(ties[0]['path'], 'row/delta_round')
        differences, ties = [], []
        compare(before, {**after, 'delta_round_ci_n': 41}, 'row', differences, ties)
        self.assertTrue(differences)
        self.assertEqual(ties, [])

    def test_record_order_classification_requires_exact_tied_row_multisets(self):
        first = {'n': 10, 'turns': 20, 'player': 'a', 'table_id': 1, 'icon': 'birds'}
        second = {**first, 'icon': 'reptiles'}
        third = {**first, 'n': 9, 'table_id': 2}
        before, after, changes = normalize_record_ties([first, second, third], [second, first, third])
        self.assertEqual(before, after)
        self.assertEqual(len(changes), 1)
        for altered in ([second, {**first, 'icon': 'fish'}, third],
                        [third, second, first], [second, first]):
            old, new, changes = normalize_record_ties([first, second, third], altered)
            self.assertNotEqual(old, new)
            self.assertEqual(changes, [])

    def test_external_rounding_proof_is_path_and_value_specific(self):
        proof = {'path': 'row/pr', 'before': 226, 'after': 227, 'verified': True}
        differences, ties = [], []
        compare({'pr': 226}, {'pr': 227}, 'row', differences, ties, {'row/pr': proof})
        self.assertEqual(differences, [])
        self.assertEqual(ties, [proof])
        for path, before, after in (('other', 226, 227), ('row', 225, 227), ('row', 226, 228)):
            differences, ties = [], []
            compare({'pr': before}, {'pr': after}, path, differences, ties, {'row/pr': proof})
            self.assertTrue(differences)
            self.assertEqual(ties, [])

    def test_rounding_classification_requires_same_raw_mean_count_and_half_boundary(self):
        before = {'delta_actual': .55, 'delta_actual_ci_mean': .5504999999999998,
                  'delta_actual_ci_n': 1240}
        after = {'delta_actual': .551, 'delta_actual_ci_mean': .5505000000000001,
                 'delta_actual_ci_n': 1240}
        differences, ties = [], []
        compare(before, after, 'row', differences, ties)
        self.assertEqual(differences, [])
        self.assertEqual(len(ties), 1)
        for changed in ({**after, 'delta_actual_ci_n': 1239},
                        {**after, 'delta_actual_ci_mean': .55049},
                        {**after, 'delta_actual': .552}):
            differences, ties = [], []
            compare(before, changed, 'row', differences, ties)
            self.assertTrue(differences)
            self.assertEqual(ties, [])

    def test_play_summary_preserves_repeated_rounds_sorted_lists_and_nulls(self):
        connection = _load_duckdb().connect()
        try:
            connection.execute('''CREATE TABLE card_play_narrow AS SELECT * FROM (VALUES
                (1,'a','X','animal',1),(1,'a','X','animal',1),
                (1,'a','X','animal',7),(1,'a','X','animal',NULL),
                (2,'a','Y','sponsor',2),(NULL,'b','Z','project',8))
                t(table_id,player,card_name,card_type,played_round)''')
            create_card_play_filter_summary(connection, 1)
            connection.execute('CREATE TABLE expected AS SELECT * FROM card_play_filter_summary')
            for batches in (2, 32):
                self.assertEqual(create_card_play_filter_summary(connection, batches), 3)
                different = connection.execute('''SELECT COUNT(*) FROM (
                    (SELECT * FROM expected EXCEPT ALL SELECT * FROM card_play_filter_summary)
                    UNION ALL
                    (SELECT * FROM card_play_filter_summary EXCEPT ALL SELECT * FROM expected))''').fetchone()[0]
                self.assertEqual(different, 0)
                row = connection.execute("SELECT played_count,played_r1,played_r6plus,played_rounds FROM card_play_filter_summary WHERE card_name='X'").fetchone()
                self.assertEqual(row, (4, 2, 1, [1, 7, None]))
        finally:
            connection.close()

    def test_linux_timeout_stops_offline_child_process_group(self):
        process = mock.Mock(pid=12345)
        with mock.patch.object(refresh_worker.os, 'name', 'posix'), \
             mock.patch.object(refresh_worker.signal, 'SIGKILL', 9, create=True), \
             mock.patch.object(refresh_worker.os, 'killpg', create=True) as kill:
            refresh_worker.kill_workflow(process)
            kill.assert_called_once_with(12345, refresh_worker.signal.SIGKILL)
            process.kill.assert_not_called()

    def test_incremental_arena_reader_handles_chunk_boundaries(self):
        class TinyReader(io.StringIO):
            def read(self, size=-1):
                return super().read(min(size, 7))
        payload = {'row_count': 1234567890123, 'data': {
            'S2': {'rows': [{'name': 'é\\\"雨', 'value': None}], 'values': [1.234e-20, True]},
            'S1': {'rows': [], 'values': [False, 17.5]}}, 'generated_at': 'now'}
        text = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
        self.assertEqual(list(JSONReader(TinyReader(text)).entries(nested_data=True)),
                         [('row_count', payload['row_count']),
                          ('data/S2', payload['data']['S2']), ('data/S1', payload['data']['S1']),
                          ('generated_at', 'now')])

    def test_arena_comparison_ignores_time_but_not_values(self):
        with tempfile.TemporaryDirectory() as directory:
            left, right = Path(directory)/'left.json', Path(directory)/'right.json'
            first = {'data': {'S1': {'rows': [{'value': 1.25}]}}, 'generated_at': 'old'}
            second = {'data': {'S1': {'rows': [{'value': 1.25}]}}, 'generated_at': 'new'}
            _write_json(left, first)
            _write_json(right, second)
            differences = []
            compare_arena(left, right, differences)
            self.assertEqual(differences, [])
            second['data']['S1']['rows'][0]['value'] = 1.3
            _write_json(right, second)
            compare_arena(left, right, differences)
            self.assertEqual(differences, ['data/S1/rows/0/value: number differs (1.25 != 1.3)'])

    def test_streamed_json_has_identical_bytes(self):
        payload = {'value': 'é雨', 'rows': [{'x': 1.234, 'missing': None, 'ok': True}] * 100}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'x.json'
            _write_json(path, payload)
            self.assertEqual(path.read_text(encoding='utf-8'), json.dumps(payload, ensure_ascii=False, separators=(',', ':'))+'\n')

    def test_pack_streaming_preserves_schema_order_values_and_membership(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entries = []
            snapshots = {}
            for index in range(3):
                payload = {'data_version': 'v', 'data': [{'card': 'é', 'mean': index/3}]}
                path = root/f'{index}.json'
                _write_json(path, payload)
                key = f'card-stats/test/{index}.json'
                snapshots[key] = payload
                entries.append({'path': str(path), 'object_key': key})
            result = _build_pack(root, entries, 'v', 'release')
            expected = {'status': 'ok', 'schema_version': DEFAULT_PACK_SCHEMA_VERSION,
                        'data_version': 'v', 'release_version': 'release', 'snapshots': snapshots}
            self.assertEqual(Path(result['path']).read_text(encoding='utf-8'), json.dumps(expected, ensure_ascii=False, separators=(',', ':'))+'\n')
            self.assertEqual(result['snapshot_count'], 3)
            self.assertTrue(all(item['pack_member'] for item in entries))

    def test_stale_member_does_not_replace_existing_pack(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            member = root/'member.json'
            _write_json(member, {'data_version': 'old'})
            pack = root/'card-stats/bootstrap/default-pack.json'
            pack.parent.mkdir(parents=True)
            pack.write_text('existing')
            with self.assertRaises(RuntimeError):
                _build_pack(root, [{'path': str(member), 'object_key': 'card-stats/test.json'}], 'new', 'r')
            self.assertEqual(pack.read_text(), 'existing')
            self.assertFalse(pack.with_suffix('.json.tmp').exists())

    def test_rss_is_optional_and_nonnegative(self):
        value = rss_current_bytes()
        self.assertTrue(value is None or value > 0)

    def test_arena_spools_preserve_complete_bundle_and_latest(self):
        def bucket(number):
            return {'season': f'S{number}', 'number': number, 'mode': 'mw', 'is_mw': 1,
                    'start_utc': 'start', 'end_utc': 'end', 'rows': [{'player_id': number, 'name': 'é'}],
                    'series': [{'dates': ['day'], 'values': [12.34]}]}
        response = {'status': 'ok', 'source': 'duckdb_private', 'generation': 'g',
                    'data_version': 'v', 'generated_at': 'now',
                    'data': {'S2': bucket(2), 'S1': bucket(1)}, 'row_count': 2}
        class Adapter:
            def execute(self, request):
                if request.get('arena_season'):
                    name = request['arena_season']
                    return {**response, 'data': {name: response['data'][name]}}
                return response
        with tempfile.TemporaryDirectory() as directory:
            paths = build_arena_bundle(Adapter(), Path(directory))
            expected = _bundle_payload(response)
            expected['generated_at'] = 'now'
            self.assertEqual(Path(paths[0]['path']).read_text(encoding='utf-8'), json.dumps(expected, ensure_ascii=False, separators=(',', ':'))+'\n')
            latest = {**expected, 'data': {'S2': expected['data']['S2']}, 'row_count': 1}
            self.assertEqual(json.loads(Path(paths[1]['path']).read_text(encoding='utf-8')), latest)
            self.assertFalse(list(Path(directory).glob('arena-spool-*')))

    def test_unknown_child_stage_is_rejected_before_execution(self):
        with mock.patch('phase5_offline_stage.subprocess.run') as run:
            with self.assertRaises(ValueError):
                invoke('arbitrary-code', {}, Path('unused.json'))
            run.assert_not_called()

    def test_child_failure_propagates_and_removes_specification(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            result = Path(directory)/'stage.json'
            with mock.patch('phase5_offline_stage.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'child')):
                with self.assertRaises(subprocess.CalledProcessError):
                    invoke('source', {'source_root': directory}, result)
            self.assertFalse(result.with_suffix('.input.json').exists())

    def test_real_source_child_imports_into_inactive_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'source'
            source.mkdir()
            (source/'manifest.json').write_text('{"status":"ok","mode":"fixture","generation":"fixture"}')
            connection = _load_duckdb().connect()
            try:
                for name in ('full_sample', 'logs'):
                    target = str(source/f'{name}-0.parquet').replace("'", "''")
                    connection.execute(f"COPY (SELECT 1 AS table_id) TO '{target}' (FORMAT PARQUET)")
            finally:
                connection.close()
            result = invoke('source', {'source_root': source, 'database': root/'inactive.duckdb',
                                      'threads': 1, 'memory_limit': '100MB', 'temp_directory': root/'spill'}, root/'result.json')
            self.assertEqual(result['relations']['source_full_sample']['rows'], 1)
            self.assertTrue((root/'inactive.duckdb').is_file())
            self.assertIn('stage_process_rss_highwater_bytes', result)

    def test_update_ranges_cover_every_nonnull_row_once_including_ties(self):
        connection = _load_duckdb().connect()
        try:
            connection.execute('CREATE TABLE game_player_narrow AS SELECT * FROM (VALUES (-5),(-5),(0),(8),(8),(100),(NULL)) t(table_id)')
            for batches in (1, 2, 32):
                covered = []
                for scope, target, parameters in canonical_update_scopes(connection, batches):
                    values = parameters[:len(parameters)//2]
                    covered.extend(row[0] for row in connection.execute(f'SELECT rowid FROM game_player_narrow WHERE {scope} AND table_id IS NOT NULL', values).fetchall())
                self.assertEqual(sorted(covered), list(range(6)))
                self.assertEqual(len(set(covered)), 6)
            with self.assertRaises(ValueError):
                canonical_update_scopes(connection, 0)
        finally:
            connection.close()

    def test_batched_seen_set_matches_original_with_nulls_trimming_and_duplicates(self):
        connection = _load_duckdb().connect()
        try:
            connection.execute('''CREATE TABLE card_log_narrow AS SELECT * FROM (VALUES
                (1,'a',[' X','X',NULL,''],['Y',' X ',' X',NULL]),
                (1,'a',[' X','X',NULL,''],['Y',' X ',' X',NULL]),
                (1,'b',NULL,['Y']), (2,'a',[],NULL), (NULL,'a',['Z'],['Z'])) t(table_id,player,cards_drawn,display_cards)''')
            connection.execute("CREATE TABLE card_in_hand_narrow AS SELECT DISTINCT table_id,player,TRIM(c.card) AS card_name FROM card_log_narrow CROSS JOIN UNNEST(COALESCE(cards_drawn, [])) c(card) WHERE TRIM(c.card) <> ''")
            connection.execute("CREATE TABLE expected_seen AS SELECT DISTINCT table_id,player,TRIM(c.card) AS card_name FROM card_log_narrow CROSS JOIN UNNEST(ARRAY_CONCAT(COALESCE(cards_drawn, []),COALESCE(display_cards, []))) c(card) WHERE TRIM(c.card) <> ''")
            for batches in (1, 16, 32):
                rows = create_seen_card_relation(connection, batches)
                differences = connection.execute('''SELECT COUNT(*) FROM (
                    (SELECT * FROM expected_seen EXCEPT ALL SELECT * FROM card_seen_narrow)
                    UNION ALL
                    (SELECT * FROM card_seen_narrow EXCEPT ALL SELECT * FROM expected_seen))''').fetchone()[0]
                self.assertEqual(differences, 0)
                self.assertEqual(rows, 4)
        finally:
            connection.close()


if __name__ == '__main__':
    unittest.main()
