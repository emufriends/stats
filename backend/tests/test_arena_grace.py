import ast
import csv
import io
import pathlib
import unittest
from datetime import datetime, timedelta, timezone


ROOT = pathlib.Path(__file__).resolve().parents[1]
MAIN_PATH = ROOT / "main.py"
S13_PATH = ROOT / "arena" / "s13.csv"


def sql_string(value):
    return "'" + str(value).replace("'", "''") + "'"


def load_functions(*names):
    tree = ast.parse(MAIN_PATH.read_text(encoding="utf-8"))
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    namespace = {
        "csv": csv,
        "datetime": datetime,
        "io": io,
        "timedelta": timedelta,
        "timezone": timezone,
        "ARENA_END_GRACE": timedelta(hours=2),
        "_sql_string": sql_string,
    }
    exec(
        compile(ast.Module(body=selected, type_ignores=[]), str(MAIN_PATH), "exec"),
        namespace,
    )
    return namespace


class ArenaGraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.functions = load_functions(
            "_arena_season_number",
            "_parse_arena_settings",
            "_parse_arena_ranking",
            "_arena_season_case_sql",
        )

    def test_effective_end_adds_two_hours_without_changing_official_end(self):
        metadata = self.functions["_parse_arena_settings"](
            "Season,Start (UTC),End (UTC),Mode\n"
            "S13,2026-04-14 14:00:00,2026-07-15 12:00:00,MW\n"
        )
        season = metadata[0]
        self.assertEqual(season["end_utc"], "2026-07-15T12:00:00Z")
        self.assertEqual(season["effective_end_utc"], "2026-07-15T14:00:00Z")

    def test_assignment_sql_uses_end_exclusive_grace_boundary(self):
        seasons = self.functions["_parse_arena_settings"](
            "Season,Start (UTC),End (UTC),Mode\n"
            "S13,2026-04-14 14:00:00,2026-07-15 12:00:00,MW\n"
        )
        source = self.functions["_arena_season_case_sql"]({"seasons": seasons})
        self.assertIn("2026-07-15T14:00:00Z", source)
        self.assertIn("game_ended_at AS TIMESTAMP) < TIMESTAMP", source)

    def test_effective_grace_may_not_overlap_next_season(self):
        with self.assertRaisesRegex(ValueError, "overlap"):
            self.functions["_parse_arena_settings"](
                "Season,Start (UTC),End (UTC),Mode\n"
                "S1,2026-01-01 00:00:00,2026-01-02 12:00:00,MW\n"
                "S2,2026-01-02 13:00:00,2026-01-03 12:00:00,MW\n"
            )

    def test_packaged_s13_ranking_is_complete(self):
        rows = self.functions["_parse_arena_ranking"](
            S13_PATH.read_text(encoding="utf-8-sig"),
            "S13",
        )
        self.assertGreater(len(rows), 100)
        self.assertEqual(rows[0]["rank"], 1)
        self.assertEqual(rows[-1]["rank"], len(rows))


if __name__ == "__main__":
    unittest.main()
