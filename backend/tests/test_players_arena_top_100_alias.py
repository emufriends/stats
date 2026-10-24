"""players/arena_top_100 returns the roster fields its contract promises."""
import json
import pathlib
import unittest

from phase3_duckdb_service import Phase3RequestAdapter, _load_duckdb
from phase4_local_routes import _next_players_arena_sql

CONTRACT = json.loads((pathlib.Path(__file__).resolve().parents[1] / "contracts" / "dashboard-routes.v1.json").read_text(encoding="utf-8"))


class PlayersArenaTop100AliasTests(unittest.TestCase):
    def setUp(self):
        self.con = _load_duckdb().connect(':memory:')
        self.con.execute("""CREATE TABLE arena_roster_narrow AS
          SELECT * FROM (VALUES ('S13',1,'Ann',11,1900.0),('S13',2,'Bob',12,1800.0),('S14',1,'Cy',13,2000.0))
          t(season, rank, player, player_id, ending_rating)""")

    def run_sql(self, request):
        sql, params = _next_players_arena_sql(request)
        result = self.con.execute(sql, params + [100, 0])
        cols = [d[0] for d in result.description]
        return cols, result.fetchall()

    def test_columns_match_contract(self):
        route = next(r for r in CONTRACT["routes"] if r["id"] == "players/arena_top_100")
        cols, rows = self.run_sql({})
        self.assertEqual(set(route["required_fields"]) - set(cols), set())
        self.assertEqual(len(rows), 3)

    def test_arena_season_filter(self):
        _, rows = self.run_sql({"arena_season": "S14"})
        self.assertEqual([r[2] for r in rows], ["Cy"])

    def test_service_keeps_arena_season(self):
        normalized = Phase3RequestAdapter.normalize_request(
            {"stats_page": "players", "players_view": "arena_top_100", "arena_season": " S14 "})
        self.assertEqual(normalized["arena_season"], "S14")


if __name__ == "__main__":
    unittest.main()
