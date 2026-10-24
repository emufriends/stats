import tempfile
import unittest
from pathlib import Path

from phase3_duckdb_service import _load_duckdb
from phase4_combo_mw_contracts import component_ci_sql
from phase5_component_ci import OfflineComponentCIs, FIELDS
from phase5_snapshot_builder import _attach_component_cis


class OfflineComponentCITests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.c = _load_duckdb().connect()
        self.c.execute('''CREATE TABLE prepared_full_sample_narrow AS
          SELECT table_id,player,is_mw,700.0 AS pre_match_elo,300.0 AS opponent_pre_match_elo,
            'Map 1a: Observation Tower' AS Map,TIMESTAMP '2026-01-01' AS game_ended_at,
            position AS starting_position,'S13' AS arena_season,TRUE AS is_arena_game,
            TRUE AS is_tournament,TRUE AS is_completed_game,bad AS is_corrupted_game,delta AS elo_delta
          FROM (VALUES (1,'a',1,'First player',FALSE,0.5),(1,'b',1,'Second player',FALSE,0.2),
            (2,'a',1,'First player',FALSE,NULL),(2,'b',1,'Second player',FALSE,-0.4),
            (3,'a',0,'First player',FALSE,0.3),(3,'b',0,'Second player',FALSE,-0.3),
            (4,'a',1,'First player',TRUE,9.0),(4,'b',1,'Second player',TRUE,-9.0))
            t(table_id,player,is_mw,position,bad,delta)''')
        self.c.execute('''CREATE TABLE card_play_narrow AS SELECT * FROM (VALUES
          (1,'a','X','animal',1),(1,'a','X','animal',1),(1,'a','X','animal',2),
          (1,'a','Y','sponsor',2),(1,'b','X','animal',1),
          (2,'a','X','animal',1),(2,'b','X','animal',6),(2,'b','Y','sponsor',1),
          (3,'a','X','animal',1),(3,'b','Y','sponsor',2),(4,'a','X','animal',1),
          (1,'a','Africa','project',1)) t(table_id,player,card_name,card_type,played_round)''')
        self.c.execute('CREATE TABLE mw_action_card_eligible_tables_narrow AS SELECT 1 AS table_id UNION ALL SELECT 2')
        self.c.execute('''CREATE TABLE mw_action_card_selection_narrow AS
          SELECT table_id,player,'Animals 1' AS card_key,elo_delta FROM prepared_full_sample_narrow
          UNION ALL SELECT table_id,player,'Cards 1',elo_delta FROM prepared_full_sample_narrow''')
        self.c.execute('''CREATE TABLE endgame_score_event_narrow AS
          SELECT table_id,player,'E' AS endgame_name FROM prepared_full_sample_narrow''')
        connection = self.c
        class Store:
            def query(self, sql, parameters):
                cursor = connection.execute(sql, parameters)
                columns = [value[0] for value in cursor.description]
                return {'rows': [dict(zip(columns, row)) for row in cursor.fetchall()]}
        self.store = Store()
        self.provider = OfflineComponentCIs(self.store, Path(self.directory.name) / 'ci.sqlite3')

    def tearDown(self):
        self.provider.close()
        self.c.close()
        self.directory.cleanup()

    def test_all_retained_components_match_independent_public_queries(self):
        cases = [
            ('combinations', 'card_card', {'card_1': 'X', 'card_2': 'Y'}, [('card', 'X'), ('card', 'Y')]),
            ('combinations', 'card_map', {'card_name': 'X', 'map_name': 'Map 1a: Observation Tower'}, [('card', 'X')]),
            ('combinations', 'card_round', {'card_name': 'X', 'round_name': '1'}, [('card', 'X')]),
            ('combinations', 'card_endgame', {'card_name': 'X', 'endgame_name': 'E'}, [('card', 'X'), ('endgame', 'E')]),
            ('combinations', 'card_action_card', {'card_name': 'X', 'action_card_key': 'Animals 1'}, [('card', 'X'), ('action_card', 'Animals 1')]),
            ('mw_action_cards', 'synergies', {'card_1_key': 'Animals 1', 'card_2_key': 'Cards 1'}, [('action_card', 'Animals 1'), ('action_card', 'Cards 1')]),
        ]
        filters = [{}, {'player_elo_min': 600, 'opponent_elo_min': 200},
                   {'starting_positions': ['First player']}, {'rounds': ['1']},
                   {'rounds': ['6+']}, {'completed_only': True, 'arena_seasons': ['S13'], 'tournament_only': True},
                   {'date_from': '2027-01-01'}, {'is_mw': 0}]
        for page, view, descriptor, identities in cases:
            for extra in filters:
                request = {'is_mw': 1, **extra}
                if page == 'mw_action_cards' or view == 'card_action_card':
                    request['is_mw'] = 1
                sql, params = component_ci_sql(request, page, view, [descriptor])
                reference = self.store.query(sql, params + [100, 0])['rows'][0]
                for index, (kind, name) in enumerate(identities, 1):
                    actual = self.provider.values(request, telemetry=page == 'mw_action_cards' or view == 'card_action_card',
                                                  kind=kind, names=[name])[name]
                    for field in FIELDS:
                        expected = reference[f'component_{index}_{field}']
                        with self.subTest(page=page, view=view, filters=extra, field=field):
                            if expected is None:
                                self.assertIsNone(actual[field])
                            else:
                                self.assertAlmostEqual(actual[field], expected, places=12)

    def test_views_and_roles_share_population_but_telemetry_does_not(self):
        request = {'is_mw': 1}
        self.provider.values(request, telemetry=False, kind='card', names=['X'])
        self.provider.values(request, telemetry=False, kind='card', names=['Y', 'missing'])
        self.assertEqual(self.provider.population_queries, 1)
        self.provider.values(request, telemetry=True, kind='card', names=['X'])
        self.assertEqual(self.provider.population_queries, 2)
        self.provider.values({**request, 'rounds': ['1']}, telemetry=False, kind='card', names=['X'])
        self.assertEqual(self.provider.population_queries, 3)

    def test_attachment_does_not_calculate_or_overwrite_context_intervals(self):
        adapter = type('Adapter', (), {'offline_component_cis': self.provider})()
        rows = [{'card_name': 'X', 'map_name': 'Map 1a: Observation Tower', 'delta_map_ci95_low': 123}]
        _attach_component_cis(adapter, 'combinations', 'card_map', 1, rows)
        self.assertEqual(self.provider.population_queries, 1)
        self.assertEqual(rows[0]['delta_map_ci95_low'], 123)
        self.assertEqual(rows[0]['component_2_ci95_n'], 0)
        self.assertIsNone(rows[0]['component_2_ci95_low'])
