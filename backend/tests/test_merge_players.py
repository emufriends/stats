import ast
import csv
import hashlib
import io
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MAIN_PATH = ROOT / "main.py"
CSV_PATH = ROOT / "merge_players.csv"


def load_functions(*names):
    tree = ast.parse(MAIN_PATH.read_text(encoding="utf-8"))
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    namespace = {
        "csv": csv,
        "hashlib": hashlib,
        "io": io,
        "_load_merge_players_metadata": lambda: {"groups": []},
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(MAIN_PATH), "exec"), namespace)
    return namespace


class MergePlayersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.functions = load_functions(
            "_parse_merge_players_csv",
            "_merge_players_maps",
            "_player_identity",
            "_player_merge_members",
            "_selected_account_summary",
            "_comparison_player_search",
        )

    def parse(self, text):
        return self.functions["_parse_merge_players_csv"](text)

    def test_current_csv_and_utf8_are_valid(self):
        metadata = self.parse(CSV_PATH.read_text(encoding="utf-8-sig"))
        propaganda_group = next(
            group
            for group in metadata["groups"]
            if "Propaganda Panda" in group["members"]
        )
        self.assertEqual(
            propaganda_group["members"],
            ["Propaganda Panda", "Guerilla Gorilla", "Badass Wrasse"],
        )
        self.assertTrue(
            any("Gillis Grafström" in group["members"] for group in metadata["groups"])
        )

    def test_trailing_empty_cells_are_ignored(self):
        metadata = self.parse("Alpha,Beta,,,\n")
        self.assertEqual(metadata["groups"][0]["members"], ["Alpha", "Beta"])

    def test_single_name_and_cross_group_duplicates_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "at least two"):
            self.parse("Alpha,,\n")
        with self.assertRaisesRegex(ValueError, "occurs in rows"):
            self.parse("Alpha,Beta\nalpha,Gamma\n")

    def test_aliases_resolve_to_one_identity(self):
        metadata = self.parse("Alpha,Beta,Gamma\n")
        identity = self.functions["_player_identity"]("Alpha", metadata)
        self.assertEqual(identity, self.functions["_player_identity"]("Beta", metadata))
        self.assertNotEqual(identity, self.functions["_player_identity"]("Other", metadata))

    def test_count_summary_splits_selected_and_associated_accounts(self):
        metadata = self.parse("Propaganda Panda,Guerilla Gorilla,Badass Wrasse\n")
        summary = self.functions["_selected_account_summary"](
            "Propaganda Panda",
            [
                {"name": "Propaganda Panda", "game_count": 1000},
                {"name": "Guerilla Gorilla", "game_count": 100},
                {"name": "Badass Wrasse", "game_count": 10},
            ],
            metadata,
        )
        self.assertEqual(summary["game_count"], 1110)
        self.assertEqual(summary["selected_game_count"], 1000)
        self.assertEqual(summary["associated_game_count"], 110)
        self.assertTrue(summary["is_merged"])
        self.assertNotIn("merge_members", summary)

    def test_comparison_search_excludes_all_aliases_of_selected_identity(self):
        metadata = self.parse("Alpha,Beta,Gamma\n")
        matches = self.functions["_comparison_player_search"](
            {"players": ["Alpha", "Beta", "Gamma", "Alphabet", "Other"]},
            "alp",
            ["Beta"],
            metadata,
        )
        self.assertEqual(matches, ["Alphabet"])

    def test_public_payloads_do_not_publish_merge_members(self):
        source = MAIN_PATH.read_text(encoding="utf-8")
        self.assertNotIn('"merge_groups": active_groups', source)
        self.assertNotIn('payload["player_merge_members"]', source)
        self.assertIn('raise ValueError("Invalid comparison player selection")', source)

    def test_query_source_ranks_and_filters_by_identity(self):
        source = MAIN_PATH.read_text(encoding="utf-8")
        self.assertIn("PARTITION BY f.player_identity", source)
        self.assertIn("f.player_identity = @players_identity", source)
        self.assertIn("f.player_identity IN UNNEST(@players_identities)", source)
        self.assertIn("@last_x_games = 0 OR player_rank <= @last_x_games", source)


if __name__ == "__main__":
    unittest.main()
