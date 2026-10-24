import ast
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "main.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
NODE = next(
    item for item in TREE.body
    if isinstance(item, ast.FunctionDef)
    and item.name == "_validate_snapshot_pack_member"
)
NAMESPACE = {}
exec(compile(ast.Module(body=[NODE], type_ignores=[]), str(ROOT / "main.py"), "exec"), NAMESPACE)
validate = NAMESPACE["_validate_snapshot_pack_member"]


def function_source(name):
    node = next(
        item for item in TREE.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    return ast.get_source_segment(SOURCE, node)


class SnapshotFreshnessTests(unittest.TestCase):
    def test_current_point_snapshot_can_publish_without_synergy_ci_metadata(self):
        validate(
            "card-stats/combinations/card-card/default-mw.json",
            {"data_version": "v-current", "data": []},
            "v-current",
        )

    def test_old_point_snapshot_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "data-version mismatch"):
            validate(
                "card-stats/combinations/card-card/default-mw.json",
                {"data_version": "v-old"},
                "v-current",
            )

    def test_version_neutral_elo_leaderboard_remains_allowed(self):
        validate(
            "card-stats/records/elo-leaderboard/default-mw.json",
            {"status": "ok", "data": []},
            "v-current",
        )

    def test_pack_reads_are_pinned_to_the_current_storage_generation(self):
        source = function_source("_write_default_snapshot_pack")
        self.assertIn("blob.reload()", source)
        self.assertIn("if_generation_match=blob.generation", source)

    def test_data_version_marker_bypasses_shared_cache(self):
        read_source = function_source("_read_data_version")
        write_source = function_source("_write_data_version")
        self.assertIn("if_generation_match=blob.generation", read_source)
        self.assertIn('blob.cache_control = "no-store, max-age=0"', write_source)

    def test_component_ci_is_part_of_snapshot_build_not_a_second_promotion(self):
        source = function_source("_refresh_default_snapshot_from_prepared")
        self.assertIn("include_component_cis=True", source)
        self.assertNotIn("synergy_ci_status", source)
        self.assertNotIn("synergy_ci_data_version", source)

    def test_no_additive_ci_scheduler_route_remains(self):
        source = function_source("get_card_stats")
        self.assertNotIn('params.get("refresh_synergy_cis")', source)
        self.assertNotIn('params.get("synergy_ci")', source)


if __name__ == "__main__":
    unittest.main()
