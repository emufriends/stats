import ast
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "main.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def function_source(name):
    node = next(
        item for item in TREE.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    return ast.get_source_segment(SOURCE, node)


class ComponentConfidenceIntervalTests(unittest.TestCase):
    def test_component_query_returns_only_standalone_intervals(self):
        source = function_source("_build_component_ci_query")
        self.assertIn("_component_ci_projection(component_aliases)", source)
        self.assertIn("component_stats", source)
        self.assertNotIn("interaction_ci95_", source)
        self.assertNotIn("variance.standard_error", source)

    def test_component_request_contract_is_distinct_from_synergy_request(self):
        source = function_source("get_card_stats")
        self.assertIn('params.get("component_ci")', source)
        self.assertIn('params.get("component_ci_rows", [])', source)
        self.assertNotIn('params.get("synergy_ci")', source)
        self.assertNotIn('params.get("synergy_ci_rows")', source)

    def test_snapshot_builder_retains_component_ci_enrichment(self):
        attach_source = function_source("_attach_snapshot_component_cis")
        self.assertIn("_load_component_ci", attach_source)
        self.assertIn("persist_synchronously=True", attach_source)
        refresh_source = function_source("_refresh_default_snapshot_from_prepared")
        self.assertIn("include_component_cis=True", refresh_source)
        self.assertIn("_attach_snapshot_component_cis", refresh_source)

    def test_additive_ci_scheduler_and_payload_metadata_are_gone(self):
        self.assertNotIn('"SYNERGY_CI_REFRESH_ENABLED"', SOURCE)
        self.assertNotIn('params.get("refresh_synergy_cis")', SOURCE)
        self.assertNotIn('payload["synergy_ci_status"]', SOURCE)
        self.assertNotIn('payload["synergy_ci_data_version"]', SOURCE)

    def test_combination_point_estimates_remain(self):
        source = function_source("_build_combinations_query")
        self.assertIn("AS interaction", source)
        self.assertIn("AS delta_actual", source)
        self.assertNotIn("interaction_ci95_", source)


if __name__ == "__main__":
    unittest.main()
