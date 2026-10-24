import ast
import pathlib
import unittest


MAIN_PATH = pathlib.Path(__file__).resolve().parents[1] / "main.py"
MAIN_SOURCE = MAIN_PATH.read_text(encoding="utf-8")
MAIN_TREE = ast.parse(MAIN_SOURCE)


def _literal_assignment(name):
    assignment = next(
        node
        for node in MAIN_TREE.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
    )
    return ast.literal_eval(assignment.value)


def _home_branch_calls_without_invalid_map_filter():
    for node in ast.walk(MAIN_TREE):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
            continue
        if not (
            isinstance(node.test.left, ast.Name)
            and node.test.left.id == "stats_page"
            and len(node.test.ops) == 1
            and isinstance(node.test.ops[0], ast.Eq)
            and len(node.test.comparators) == 1
            and isinstance(node.test.comparators[0], ast.Name)
            and node.test.comparators[0].id == "STATS_PAGE_HOME"
        ):
            continue
        for call in ast.walk(node):
            if not (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == "_build_full_sample_where_sql"
            ):
                continue
            if any(
                keyword.arg == "exclude_invalid_maps"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is False
                for keyword in call.keywords
            ):
                return True
    return False


def _players_branch_calls_without_invalid_map_filter():
    for node in ast.walk(MAIN_TREE):
        if not isinstance(node, ast.If):
            continue
        source = ast.get_source_segment(MAIN_SOURCE, node) or ""
        if (
            "stats_page == STATS_PAGE_PLAYERS" in source
            and "_build_full_sample_where_sql" in source
            and "exclude_invalid_maps=False" in source
        ):
            return True
    return False


class HomeMapPopulationTests(unittest.TestCase):
    def test_home_catalog_contains_legacy_and_beginner_maps(self):
        expected_codes = {
            "1a", "2a", "3a", "4a", "5a", "6a", "7a", "8a",
            "9", "10", "11", "12", "13", "14", "T1",
            "1", "2", "3", "4", "5", "6", "7", "8", "A", "0",
        }
        maps = _literal_assignment("ALL_MAPS_FOR_METRICS")
        actual_codes = {item["code"] for item in maps}
        self.assertEqual(actual_codes, expected_codes)
        self.assertEqual(len(maps), 25)

    def test_home_where_clause_does_not_add_invalid_map_filter(self):
        self.assertTrue(_home_branch_calls_without_invalid_map_filter())

    def test_restricted_default_still_adds_invalid_map_filter(self):
        function = next(
            node
            for node in MAIN_TREE.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_build_full_sample_where_sql"
        )
        defaults = dict(zip(
            [argument.arg for argument in function.args.args[-len(function.args.defaults):]],
            function.args.defaults,
        ))
        self.assertIs(ast.literal_eval(defaults["exclude_invalid_maps"]), True)

    def test_players_where_clause_accepts_all_configured_maps(self):
        self.assertTrue(_players_branch_calls_without_invalid_map_filter())
        self.assertIn(
            "if stats_page in (STATS_PAGE_HOME, STATS_PAGE_PLAYERS, STATS_PAGE_RECORDS)",
            MAIN_SOURCE,
        )


if __name__ == "__main__":
    unittest.main()
