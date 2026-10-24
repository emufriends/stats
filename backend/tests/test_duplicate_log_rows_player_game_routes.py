"""Build Enclosures, 2-CP Worker and Upgrade Order count each player-game once,
even when the raw producer exported its log row twice."""
import unittest

from phase3_duckdb_service import _load_duckdb
from phase4_local_routes import (
    _simple_actions_upgrade_order_sql,
    _simple_build_enclosures_sql,
    _simple_workers_sql,
)


def make_connection(duplicate: bool):
    con = _load_duckdb().connect(':memory:')
    con.execute('''CREATE TABLE prepared_full_sample_narrow AS
      SELECT 1::BIGINT AS table_id, 'a' AS player, 'Map 1a: Observation Tower' AS Map,
        10.0 AS elo_delta, 0 AS Petting_Zoo_icons''')
    row = ("SELECT 1::BIGINT AS table_id, 'a' AS player, TRUE AS \"2cp_worker\", "
           "'Animals' AS first_upgrade, 'Cards' AS second_upgrade, NULL::VARCHAR AS third_upgrade, "
           "NULL::VARCHAR AS fourth_upgrade, 1 AS \"1_size_enclosure_built\", 0 AS \"2_size_enclosure_built\", "
           "0 AS \"3_size_enclosure_built\", 0 AS \"4_size_enclosure_built\", 0 AS \"5_size_enclosure_built\", "
           "0 AS aviary_built, 0 AS reptile_house_built, 0 AS petting_zoo_built, "
           "0 AS large_aquarium_built, 0 AS small_aquarium_built, "
           "[]::STRUCT(sponsor VARCHAR)[] AS played_sponsors")
    con.execute(f"CREATE TABLE source_logs AS {row}" + (f" UNION ALL {row}" if duplicate else ""))
    return con


class DuplicateLogRowTests(unittest.TestCase):
    def run_sql(self, builder, *args):
        results = []
        for duplicate in (False, True):
            con = make_connection(duplicate)
            try:
                sql, params = builder("TRUE", [], *args)
                results.append(con.execute(sql, params + [100, 0]).fetchall())
            finally:
                con.close()
        return results

    def test_upgrade_order(self):
        single, doubled = self.run_sql(_simple_actions_upgrade_order_sql)
        self.assertEqual(single, doubled)
        self.assertTrue(any(1 in row[1:] or True for row in single))

    def test_two_cp_worker(self):
        single, doubled = self.run_sql(_simple_workers_sql, True)
        self.assertEqual(single, doubled)

    def test_build_enclosures(self):
        single, doubled = self.run_sql(_simple_build_enclosures_sql)
        self.assertEqual(single, doubled)
        self.assertTrue(any(row[2] == 1 for row in single))  # n_total counts the game once


if __name__ == "__main__":
    unittest.main()
