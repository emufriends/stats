import ast
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "main.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def function_source(name):
    node = next(
        item for item in TREE.body
        if isinstance(item, (ast.FunctionDef, ast.ClassDef)) and item.name == name
    )
    return ast.get_source_segment(SOURCE, node)


class CostContainmentTests(unittest.TestCase):
    def test_every_bigquery_client_uses_the_cost_controlled_subclass(self):
        self.assertEqual(SOURCE.count("bigquery.Client("), 0)
        self.assertGreater(SOURCE.count("_CostControlledBigQueryClient("), 20)
        client = function_source("_CostControlledBigQueryClient")
        self.assertIn("maximum_bytes_billed", client)
        self.assertIn('labels["ark_workload"]', client)
        self.assertIn('labels["ark_component"]', client)

    def test_public_queries_are_disabled_by_default_and_guard_cache_misses(self):
        self.assertIn(
            '"PUBLIC_BIGQUERY_QUERIES_ENABLED", False', SOURCE
        )
        component = function_source("_load_component_ci")
        history = function_source("_load_players_history")
        handler = function_source("get_card_stats")
        self.assertGreater(component.index("_read_cache_blob"), -1)
        self.assertGreater(
            component.index("_require_public_bigquery_query"),
            component.index("_read_cache_blob"),
        )
        self.assertGreater(
            history.index("_require_public_bigquery_query"),
            history.index("_read_cache_blob"),
        )
        self.assertIn("_PublicBigQueryQueryDisabled", handler)
        self.assertIn("503", handler)

    def test_optional_bigquery_maintenance_is_off_by_default(self):
        self.assertIn('"CARD_CARD_WARMING_ENABLED", False', SOURCE)
        self.assertIn('"PARTIAL_BIGQUERY_REFRESH_ENABLED", False', SOURCE)

    def test_card_moments_precede_the_aggregate_that_reads_them(self):
        refresh = function_source("_refresh_prepared_tables")
        self.assertLess(
            refresh.index('(\"card_moments\"'),
            refresh.index('(\"card_play_aggregates\"'),
        )

    def test_daily_refresh_has_unchanged_and_lightweight_external_paths(self):
        refresh = function_source("_run_daily_refresh")
        self.assertIn("_can_skip_daily_refresh", refresh)
        self.assertIn('"source_unchanged"', refresh)
        self.assertIn('"external_snapshots_only"', refresh)
        self.assertIn("_write_refresh_source_state", refresh)

    def test_default_snapshot_queries_use_the_maintenance_ceiling(self):
        snapshot = function_source("_refresh_default_snapshot_from_prepared")
        query = function_source("_query_card_stats")
        self.assertIn('"query_workload": "maintenance_snapshot"', snapshot)
        self.assertIn("ark_workload=query_workload or", query)


if __name__ == "__main__":
    unittest.main()
