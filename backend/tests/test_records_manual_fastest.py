import ast
import csv
import io
import pathlib
import unittest


MAIN_PATH = pathlib.Path(__file__).resolve().parents[1] / "main.py"
MAIN_SOURCE = MAIN_PATH.read_text(encoding="utf-8")
MAIN_TREE = ast.parse(MAIN_SOURCE)


def load_fastest_parser():
    names = {"_records_sheet_int", "_parse_records_fastest_sheet"}
    selected = [
        node for node in MAIN_TREE.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    namespace = {
        "csv": csv,
        "io": io,
        "RECORDS_VIEW_FASTEST_GAMES": "fastest_games",
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(MAIN_PATH), "exec"), namespace)
    return namespace["_parse_records_fastest_sheet"]


class RecordsManualFastestTests(unittest.TestCase):
    def setUp(self):
        self.parse = load_fastest_parser()

    def test_five_column_schema_is_complete_without_derived_metadata(self):
        rows = self.parse(
            "Turns,Player,Score,ID,EPT\n"
            "22,Gnaver,109,771325871,5\n"
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["table_id"], "771325871")
        self.assertEqual(rows[0]["turns"], 22)
        self.assertEqual(rows[0]["score"], 109)
        self.assertEqual(rows[0]["ept"], 5)
        for derived in ("Map", "map_code", "game_date", "mode", "is_mw"):
            self.assertNotIn(derived, rows[0])

    def test_old_map_date_and_mode_columns_are_not_required(self):
        with self.assertRaisesRegex(ValueError, "missing columns: EPT"):
            self.parse("Turns,Player,Score,ID\n22,Gnaver,109,771325871\n")

    def test_duplicate_identity_is_case_insensitive(self):
        with self.assertRaisesRegex(ValueError, "duplicate ID/Player"):
            self.parse(
                "Turns,Player,Score,ID,EPT\n"
                "22,Gnaver,109,771325871,5\n"
                "21,gnaver,110,771325871,4\n"
            )

    def test_games_to_add_gid_is_explicit(self):
        self.assertIn("gid=1836311698", MAIN_SOURCE)

    def test_enrichment_allows_sheet_owned_player_spelling(self):
        self.assertIn(
            "metadata_rows = [match] if match is not None else table_matches",
            MAIN_SOURCE,
        )
        self.assertNotIn("has no Full Sample row for player", MAIN_SOURCE)


if __name__ == "__main__":
    unittest.main()
