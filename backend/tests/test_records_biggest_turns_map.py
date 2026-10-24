"""Biggest Turns map name: Full Sample first, sheet code translated to full name otherwise."""
import pathlib
import sys
import unittest

import duckdb

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from phase4_local_routes import _final_records_sql  # noqa: E402


class BiggestTurnsMapTests(unittest.TestCase):
    def setUp(self):
        self.db = duckdb.connect(":memory:")
        self.db.execute("""CREATE TABLE records_manual_narrow(
          record_view VARCHAR, source_row BIGINT, table_id BIGINT, player VARCHAR, mode VARCHAR,
          turns DOUBLE, score DOUBLE, ept BIGINT, flat BIGINT, "end" BIGINT, total BIGINT,
          move BIGINT, actions BIGINT, map_code VARCHAR, result_code VARCHAR, game_date VARCHAR)""")
        self.db.execute("""CREATE TABLE prepared_full_sample_narrow(
          table_id BIGINT, player VARCHAR, is_mw INTEGER, Map VARCHAR, game_ended_at VARCHAR,
          opponent_elo DOUBLE, Starting_position_in_first_round INTEGER)""")
        self.db.execute("CREATE TABLE corrupted_tables_narrow(table_id BIGINT)")
        self.db.execute("CREATE TABLE arena_seasons_metadata(start_utc TIMESTAMPTZ, end_utc TIMESTAMPTZ, mode VARCHAR)")
        self.db.execute("CREATE TABLE tournament_tables_metadata(table_id BIGINT)")
        # Row 1 matches the Full Sample (its Map must win); row 2 does not (sheet code 3a).
        self.db.execute("INSERT INTO records_manual_narrow VALUES "
                        "('biggest_turns',1,100,'Ann','Base',20,100,1,1,1,50,1,1,'1a',NULL,'2026-01-01'),"
                        "('biggest_turns',2,200,'Bob','Base',20,100,1,1,1,40,1,1,'3a',NULL,'2026-01-02')")
        self.db.execute("INSERT INTO prepared_full_sample_narrow VALUES "
                        "(100,'Ann',0,'Map 2a: Outdoor Areas','2026-01-01 10:00:00+00',500,1)")

    def test_map_name(self):
        sql, params = _final_records_sql({}, "biggest_turns")
        rows = self.db.execute(sql, params + [10, 0]).fetchall()
        cols = [d[0] for d in self.db.description]
        by_player = {r[cols.index("player")]: r[cols.index("map_name")] for r in rows}
        self.assertEqual(by_player["Ann"], "Map 2a: Outdoor Areas")   # Full Sample wins over sheet '1a'
        self.assertEqual(by_player["Bob"], "Map 3a: Silver Lake")      # unmatched: full name, not '3a'


if __name__ == "__main__":
    unittest.main()
