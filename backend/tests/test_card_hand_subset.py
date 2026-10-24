"""The canonical hand-subset fast path must not alter generic helper semantics."""
import unittest

from phase3_duckdb_service import _load_duckdb
from phase2_local_vertical_slice import create_card_filter_core_relation


class CardHandSubsetTests(unittest.TestCase):
    def setUp(self):
        self.c=_load_duckdb().connect(':memory:')
        self.c.execute('SET threads=1')
        self.c.execute("CREATE TABLE game_player_narrow AS SELECT 1 AS table_id,'a' AS player,1 AS is_mw")
        self.c.execute("CREATE TABLE card_seen_narrow AS SELECT * FROM (VALUES (1,'a','X'),(1,'a','S')) t(table_id,player,card_name)")
        self.c.execute("CREATE TABLE card_in_hand_narrow AS SELECT 1 AS table_id,'a' AS player,'X' AS card_name")
        self.c.execute("""CREATE TABLE card_play_filter_summary AS SELECT
            1 AS table_id,'a' AS player,'X' AS card_name,'animal' AS card_type,
            2::BIGINT AS played_count,1::BIGINT AS played_r1,1::BIGINT AS played_r2,
            0::BIGINT AS played_r3,0::BIGINT AS played_r4,0::BIGINT AS played_r5,
            0::BIGINT AS played_r6plus""")

    def tearDown(self):
        self.c.close()

    def test_generic_retains_hand_only_and_null_card(self):
        self.c.execute("INSERT INTO card_in_hand_narrow VALUES (1,'a','H'),(1,'a',NULL)")
        create_card_filter_core_relation(self.c,2)
        self.assertEqual(self.c.execute("SELECT in_hand,seen FROM card_filter_fact_narrow WHERE card_name='H'").fetchone(),(1,0))
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM card_filter_fact_narrow WHERE card_name IS NULL').fetchone()[0],1)

    def test_trusted_subset_preserves_exact_schema_and_row_multiplicity(self):
        create_card_filter_core_relation(self.c,2)
        self.c.execute('ALTER TABLE card_filter_fact_narrow RENAME TO expected')
        create_card_filter_core_relation(self.c,2,hand_is_subset_of_seen=True)
        self.assertEqual(self.c.execute('DESCRIBE expected').fetchall(),
                         self.c.execute('DESCRIBE card_filter_fact_narrow').fetchall())
        differences=self.c.execute('''SELECT COUNT(*) FROM (
            (SELECT * FROM expected EXCEPT ALL SELECT * FROM card_filter_fact_narrow)
            UNION ALL (SELECT * FROM card_filter_fact_narrow EXCEPT ALL SELECT * FROM expected))''').fetchone()[0]
        self.assertEqual(differences,0)
        self.assertEqual(self.c.execute("SELECT played_count,in_hand,seen FROM card_filter_fact_narrow WHERE card_name='X'").fetchone(),(2,1,1))


if __name__=='__main__': unittest.main()
