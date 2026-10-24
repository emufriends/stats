import pathlib
import sys
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
DUCKDB_PACKAGE = ROOT / "phase2_private_data" / "python314"
if DUCKDB_PACKAGE.exists():
    sys.path.insert(0, str(DUCKDB_PACKAGE))

from phase2_local_vertical_slice import create_canonical_player_relations
from phase4_metadata import materialize_metadata_tables


class CanonicalPopulationTests(unittest.TestCase):
    def setUp(self):
        try:
            import duckdb
        except ImportError:  # pragma: no cover - environment-specific
            self.skipTest("duckdb unavailable")
        self.duckdb = duckdb

    def _connection(self):
        connection = self.duckdb.connect(":memory:")
        connection.execute("""
            CREATE TABLE source_full_sample(
              table_id BIGINT, player VARCHAR, player_id BIGINT, is_mw BIGINT,
              Map VARCHAR, game_ended_at TIMESTAMP,
              Starting_position_in_first_round VARCHAR,
              pre_match_elo DOUBLE, post_match_elo DOUBLE, opponent_elo DOUBLE,
              elo_delta DOUBLE, Game_result BIGINT, concede BIGINT,
              end_game_triggered BOOLEAN, arena_rating_delta BIGINT,
              Number_of_turns BIGINT, Animals_actions BIGINT,
              Association_actions BIGINT, Build_actions BIGINT,
              Cards_actions BIGINT, Sponsors_actions BIGINT,
              X_Tokens_gained_instead_of_action BIGINT
            )
        """)
        rows = [
            (1, "Alice", 11, 1, "Map 1a: Observation Tower", "2026-08-01 12:00:00", " first PLAYER ", 700, 705, 999, 5, 1, 0, True, 10, 10, 2, 2, 2, 2, 2, 0),
            (1, "Bob", 12, 1, "Map 1a: Observation Tower", "2026-08-01 12:00:00", "SECOND player", 300, 295, 111, -5, 2, 0, True, -10, 10, 2, 2, 2, 2, 2, 0),
            # Exact action gap two on the loser corrupts both rows of table 2.
            (2, "Quitter", 21, 0, "Map 1: Observation Tower", "2026-08-02 12:00:00", "First player", 400, 390, 1, -10, 2, 0, True, None, 10, 2, 2, 1, 1, 2, 0),
            (2, "Runner", 22, 0, "Map 1: Observation Tower", "2026-08-02 12:00:00", "Second player", 420, 430, 1, 10, 1, 0, True, None, 10, 2, 2, 2, 2, 2, 0),
            # A three-player malformed table has no unique canonical opponent.
            (3, "One", 31, 1, "Map 2a: Outdoor Areas", "2026-08-03 12:00:00", "unknown", 500, 501, 1, 1, 1, 0, True, None, 10, 2, 2, 2, 2, 2, 0),
            (3, "Two", 32, 1, "Map 2a: Outdoor Areas", "2026-08-03 12:00:00", "First player", 510, 509, 1, -1, 2, 0, True, None, 10, 2, 2, 2, 2, 2, 0),
            (3, "Three", 33, 1, "Map 2a: Outdoor Areas", "2026-08-03 12:00:00", "Second player", 520, 520, 1, 0, 2, 0, True, None, 10, 2, 2, 2, 2, 2, 0),
        ]
        connection.executemany(
            "INSERT INTO source_full_sample VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        materialize_metadata_tables(
            connection,
            [{"table_id": 1, "tournament_name": "Cup", "season": "1"}],
            [{
                "season": "S14", "start_utc": "2026-07-01T00:00:00+00:00",
                "end_utc": "2026-09-01T00:00:00+00:00", "mode": "mw",
            }],
        )
        return connection

    def test_canonical_boundary_preserves_raw_and_materializes_shared_facts(self):
            connection = self._connection()
            create_canonical_player_relations(connection, None)

            alice = connection.execute("""
                SELECT opponent_pre_match_elo, starting_position, is_completed_game,
                  is_corrupted_game, arena_season, is_arena_game, is_tournament,
                  player_identity
                FROM game_player_narrow WHERE table_id = 1 AND player = 'Alice'
            """).fetchone()
            self.assertEqual(alice[:7], (300.0, "First player", True, False, "S14", True, True))
            self.assertEqual(alice[7], "player:Alice")
            self.assertEqual(
                connection.execute(
                    "SELECT opponent_elo FROM source_full_sample WHERE table_id=1 AND player='Alice'"
                ).fetchone()[0],
                999.0,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT opponent_elo FROM prepared_full_sample_narrow WHERE table_id=1 AND player='Alice'"
                ).fetchone()[0],
                300.0,
            )

            corrupted = connection.execute(
                "SELECT DISTINCT is_corrupted_game FROM game_player_narrow WHERE table_id=2"
            ).fetchall()
            self.assertEqual(corrupted, [(True,)])
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM source_full_sample WHERE table_id=2").fetchone()[0],
                2,
            )
            self.assertIsNone(connection.execute(
                "SELECT opponent_pre_match_elo FROM game_player_narrow WHERE table_id=3 AND player='One'"
            ).fetchone()[0])
            self.assertFalse(connection.execute(
                "SELECT is_completed_game FROM game_player_narrow WHERE table_id=3 LIMIT 1"
            ).fetchone()[0])
            connection.close()


    def test_batched_canonical_values_match_single_transaction(self):
        connection = self._connection()
        try:
            with mock.patch.dict('os.environ', {'DUCKDB_CANONICAL_UPDATE_BATCHES': '1'}):
                create_canonical_player_relations(connection)
            connection.execute('CREATE TABLE expected_canonical AS SELECT * FROM prepared_full_sample_narrow')
            with mock.patch.dict('os.environ', {'DUCKDB_CANONICAL_UPDATE_BATCHES': '32'}):
                create_canonical_player_relations(connection)
            differences = connection.execute('''SELECT COUNT(*) FROM (
                (SELECT * FROM expected_canonical EXCEPT ALL SELECT * FROM prepared_full_sample_narrow)
                UNION ALL
                (SELECT * FROM prepared_full_sample_narrow EXCEPT ALL SELECT * FROM expected_canonical))''').fetchone()[0]
            self.assertEqual(differences, 0)
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
