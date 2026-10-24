"""Default Players snapshots reuse exact cohorts, never individual summaries."""
import math
import re
import unittest

from phase3_duckdb_service import _load_duckdb, Phase3RequestAdapter
from phase4_local_routes import _players_metric_sql, PLAYERS_METRICS, PLAYERS_MONEY_FIELDS
from phase5_snapshot_builder import _request, STANDARD_MAPS


class PlayersSnapshotReuseTests(unittest.TestCase):
    def setUp(self):
        self.c = _load_duckdb().connect()
        expressions = ' '.join(metric[-1] for metric in PLAYERS_METRICS)
        expressions = re.sub(r"'[^']*'", '', expressions)
        keywords = {'AVG', 'TRY_CAST', 'AS', 'DOUBLE', 'NULLIF', 'CASE',
                    'WHEN', 'THEN', 'ELSE', 'END', 'IN', 'NULL', 'TRUE', 'FALSE'}
        fields = {n for n in re.findall(r'\b[A-Za-z_]\w*\b', expressions)
                  if n.upper() not in keywords}
        fields.update(('pre_match_elo', 'Game_result', *PLAYERS_MONEY_FIELDS.values()))
        fields.discard('Map')
        values = [f'CAST(i+1 AS DOUBLE) AS {n}' for n in sorted(fields)]
        self.c.execute(f"""CREATE TABLE players_metrics_narrow AS SELECT
            {', '.join(values)}, i AS table_id, 'a' AS player,
            'player:a' AS player_identity, (i % 2)::INTEGER AS is_mw,
            CASE WHEN i % 11 = 0 THEN 'Map A: Beginner'
                 ELSE 'Map 1a: Observation Tower' END AS Map,
            TIMESTAMP '2026-01-01' + i * INTERVAL 1 DAY AS game_ended_at,
            'First player' AS starting_position, NULL::VARCHAR AS arena_season,
            FALSE AS is_arena_game, FALSE AS is_tournament,
            600.0 AS opponent_pre_match_elo
            FROM range(32) r(i)""")
        self.c.execute("""UPDATE players_metrics_narrow SET pre_match_elo =
            CASE table_id % 8 WHEN 0 THEN NULL WHEN 1 THEN -1
                 WHEN 2 THEN 499 WHEN 3 THEN 500 WHEN 4 THEN 699 ELSE 700 END,
            Game_result = CASE WHEN table_id % 3 = 0 THEN 1 ELSE 2 END,
            Number_of_turns = CASE WHEN table_id % 5 = 0 THEN NULL ELSE 42 END,
            Money_spent_on_animals = CASE WHEN table_id % 7 = 0 THEN NULL ELSE 12 END,
            Money_spent_on_enclosures = CASE WHEN table_id % 6 = 0 THEN NULL ELSE 8 END,
            Money_spent_on_donations = 3,
            Money_spent_for_playing_cards_from_reputation_range = 2""")
        self.c.execute('CREATE TABLE players_by_identity_narrow AS SELECT * FROM players_metrics_narrow')
        self.c.execute("""CREATE TABLE player_identity_metadata AS SELECT
            'a' AS player_casefold, 'player:a' AS player_identity""")
        self.prepare_cohorts()

    def tearDown(self):
        self.c.close()

    def prepare_cohorts(self):
        # Independent direct aggregates, matching the producer's exact scope.
        fields = ['COUNT(*) AS observation_count',
                  *[f'{e} AS {k}' for k, *_, e in PLAYERS_METRICS],
                  *[f'AVG(TRY_CAST({col} AS DOUBLE)) AS raw_{k}'
                    for k, col in PLAYERS_MONEY_FIELDS.items()]]
        self.c.execute('DROP TABLE IF EXISTS players_default_cohorts_narrow')
        for index, (cohort, predicate) in enumerate((('all', 'TRUE'),
                ('winners', 'Game_result=1'), ('experts', 'pre_match_elo>=500'),
                ('masters', 'pre_match_elo>=700'))):
            statement = ('CREATE TABLE players_default_cohorts_narrow AS' if index == 0
                         else 'INSERT INTO players_default_cohorts_narrow')
            self.c.execute(f"""{statement} SELECT is_mw, '{cohort}' AS cohort,
                {', '.join(fields)} FROM players_metrics_narrow
                WHERE Map IN ({','.join('?' for _ in STANDARD_MAPS)})
                  AND pre_match_elo >= 0 AND opponent_pre_match_elo >= 0
                  AND {predicate} GROUP BY is_mw""", list(STANDARD_MAPS))

    def request(self, dataset=1, **changes):
        raw = _request('players', 'general', dataset, 1000, 0)
        raw.update(changes)
        return Phase3RequestAdapter.normalize_request(raw)

    def run_query(self, request, prepared):
        sql, params = _players_metric_sql({**request, '_players_filter_facts': prepared}, 'general')
        result = self.c.execute(sql, [*params, request['limit'], request['offset']])
        return [dict(zip([d[0] for d in result.description], r)) for r in result.fetchall()]

    def assert_same(self, fast, direct):
        self.assertEqual(len(fast), len(PLAYERS_METRICS))
        self.assertEqual(len(fast), len(direct))
        for a, b in zip(fast, direct):
            self.assertEqual(set(a), set(b))
            for key in a:
                if isinstance(a[key], float) and isinstance(b[key], (int, float)):
                    self.assertTrue(math.isclose(a[key], b[key], rel_tol=2e-12, abs_tol=1e-12),
                                    (a['metric'], key, a[key], b[key]))
                else:
                    self.assertEqual(a[key], b[key], (a['metric'], key))

    def test_default_snapshot_and_selected_identity_match_direct_aggregates(self):
        for dataset in (0, 1):
            for player in (None, 'a', 'unknown'):
                with self.subTest(dataset=dataset, player=player):
                    req = self.request(dataset, players_player=player)
                    sql, _ = _players_metric_sql({**req, '_players_filter_facts': True}, 'general')
                    self.assertNotIn('cohort_buckets AS', sql)
                    if player is None:
                        self.assertIn('WHERE FALSE', sql)
                        self.assertNotIn('players_by_identity_narrow', sql)
                        self.assertNotIn('players_metrics_narrow', sql)
                    fast = self.run_query(req, True)
                    self.assert_same(fast, self.run_query(req, False))
                    if player != 'a':
                        self.assertTrue(all(r['player'] is None and r['count_player'] == 0 for r in fast))

    def test_missing_cohorts_and_empty_dataset_keep_all_metric_rows(self):
        self.c.execute('UPDATE players_metrics_narrow SET pre_match_elo=400, Game_result=2')
        self.c.execute('DELETE FROM players_metrics_narrow WHERE is_mw=0')
        self.c.execute('DELETE FROM players_by_identity_narrow')
        self.c.execute('INSERT INTO players_by_identity_narrow SELECT * FROM players_metrics_narrow')
        self.prepare_cohorts()
        for dataset in (0, 1):
            req = self.request(dataset)
            fast = self.run_query(req, True)
            self.assert_same(fast, self.run_query(req, False))
            self.assertTrue(all(r['experts'] is None and r['count_experts'] == 0 for r in fast))

    def test_default_snapshot_does_not_bind_any_individual_player_relation(self):
        req = self.request()
        expected = self.run_query(req, True)
        for name in ('players_metrics_narrow', 'players_by_identity_narrow', 'player_identity_metadata'):
            self.c.execute(f'DROP TABLE {name}')
        self.assert_same(self.run_query(req, True), expected)

    def test_restrictive_scopes_never_use_default_cohorts(self):
        for change in ({'maps': ['1a']}, {'maps': []}, {'player_elo_min': 500},
                {'player_elo_max': 700}, {'opponent_elo_min': 300},
                {'opponent_elo_max': 800}, {'date_from': '2026-01-01'},
                {'date_to': '2026-02-01'}, {'starting_positions': ['First player']},
                {'arena_seasons': ['S13']}, {'arena_only': True}, {'tournament_only': True}):
            req = self.request(**change)
            with self.subTest(change=change):
                sql, _ = _players_metric_sql({**req, '_players_filter_facts': True}, 'general')
                self.assertIn('cohort_buckets AS', sql)
                self.assertNotIn('LEFT JOIN players_default_cohorts_narrow', sql)

    def test_last_x_limits_only_selected_player_not_global_cohorts(self):
        req = self.request(players_player='a', last_x_games=2)
        fast = self.run_query(req, True)
        self.assert_same(fast, self.run_query(req, False))
        self.assertTrue(all(r['count_player'] == 2 for r in fast))
        no_last_x = self.run_query(self.request(players_player='a'), True)
        self.assertEqual([r['count_all'] for r in fast], [r['count_all'] for r in no_last_x])


if __name__ == '__main__':
    unittest.main()
