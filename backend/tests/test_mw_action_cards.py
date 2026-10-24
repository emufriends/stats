import ast
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MAIN_PATH = ROOT / "main.py"
SOURCE = MAIN_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def function_source(name):
    node = next(
        item for item in TREE.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == name
    )
    return ast.get_source_segment(SOURCE, node)


def literal_assignment(name):
    assignment = next(
        node for node in TREE.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
    )
    return ast.literal_eval(assignment.value)


class MwActionCardsTests(unittest.TestCase):
    def test_catalog_has_all_twenty_special_cards(self):
        catalog = literal_assignment("MW_ACTION_CARD_CATALOG")
        self.assertEqual(len(catalog), 20)
        self.assertEqual([row[0] for row in catalog], list(range(1, 21)))
        self.assertEqual({row[1] for row in catalog}, {
            "Animals", "Association", "Build", "Cards", "Sponsors",
        })
        for card_type in {row[1] for row in catalog}:
            self.assertEqual(
                sorted(row[2] for row in catalog if row[1] == card_type),
                [1, 2, 3, 4],
            )

    def test_telemetry_validation_covers_all_eight_fields(self):
        source = function_source("_mw_action_card_telemetry_condition")
        for field in (
            "Animals_Action_Card_Number",
            "Association_Action_Card_Number",
            "Build_Action_Card_Number",
            "Cards_Action_Card_Number",
            "Sponsors_Action_Card_Number",
            "First_drafted_action_card",
            "Second_drafted_action_card",
            "Third_drafted_action_card",
        ):
            self.assertIn(field, source)
        self.assertIn("BETWEEN 0 AND 4", source)
        self.assertIn("REGEXP_CONTAINS", source)

    def test_prepared_population_requires_exactly_two_valid_players(self):
        source = function_source("_refresh_prepared_mw_action_card_tables")
        self.assertIn("CAST(f.is_mw AS INT64) = 1", source)
        self.assertIn("HAVING COUNT(*) = 2", source)
        self.assertIn("COUNT(DISTINCT player) = 2", source)
        self.assertIn("COUNTIF(NOT", source)
        self.assertIn("PREPARED_MW_ACTION_CARD_PLAYERS_TABLE", source)
        self.assertIn("PREPARED_MW_ACTION_CARD_DRAFTS_TABLE", source)
        self.assertIn("PREPARED_MW_ACTION_CARD_MAP_AGGREGATES_TABLE", source)
        self.assertIn("PREPARED_MW_ACTION_CARD_SYNERGY_AGGREGATES_TABLE", source)
        self.assertIn("PREPARED_CARD_ACTION_CARD_TABLE", source)
        self.assertIn("PREPARED_CARD_ACTION_CARD_AGGREGATES_TABLE", source)

    def test_catalog_documents_backend_to_frontend_names(self):
        catalog = literal_assignment("MW_ACTION_CARD_CATALOG")
        self.assertIn((17, "Sponsors", 1, "Trade"), catalog)
        source = SOURCE
        self.assertIn("Sponsors 1 -> Trade", source)

    def test_draft_is_an_accepted_view(self):
        parser = function_source("_parse_mw_action_cards_view")
        self.assertIn("VALID_MW_ACTION_CARDS_VIEWS", parser)
        self.assertIn('MW_ACTION_CARDS_VIEW_DRAFT = "draft"', SOURCE)

    def test_general_query_uses_player_scope_and_unordered_table_pairing(self):
        source = function_source("_build_mw_action_cards_query")
        self.assertIn('(\"pre_match_elo\", \"player_elo_min\"', source)
        self.assertIn('(\"opponent_pre_match_elo\", \"opponent_elo_min\"', source)
        self.assertIn('role_bounds("d.p1_pre_match_elo", "player")', source)
        self.assertIn('role_bounds("d.p2_pre_match_elo", "opponent")', source)
        self.assertIn('role_bounds("d.p2_pre_match_elo", "player")', source)
        self.assertIn('role_bounds("d.p1_pre_match_elo", "opponent")', source)
        self.assertIn('") OR ("', source)
        self.assertIn("COUNTIF(d.picked)", source)
        self.assertIn("COUNTIF(d.drafted_first)", source)
        self.assertIn("COUNTIF(d.drafted_second)", source)
        self.assertIn("COUNTIF(d.undrafted)", source)
        self.assertIn("SAFE_DIVIDE", source)

    def test_general_query_splits_upgraded_and_basic_delta(self):
        prepared = function_source("_refresh_prepared_mw_action_card_tables")
        query = function_source("_build_mw_action_cards_query")
        for field in (
            "Upgraded_Animals_action_card",
            "Upgraded_Association_action_card",
            "Upgraded_Build_action_card",
            "Upgraded_Cards_action_card",
            "Upgraded_Sponsors_action_card",
        ):
            self.assertIn(field, prepared)
        self.assertIn("AS upgraded", prepared)
        self.assertIn("COALESCE", prepared)
        self.assertIn("delta_picked_upgraded", query)
        self.assertIn("delta_picked_basic", query)
        self.assertIn("IF(p.upgraded, p.elo_delta, NULL)", query)
        self.assertIn("IF(NOT p.upgraded, p.elo_delta, NULL)", query)

    def test_general_and_draft_share_the_filter_cache_identity(self):
        handler = function_source("get_card_stats")
        self.assertIn(
            "if mw_action_cards_view == MW_ACTION_CARDS_VIEW_DRAFT",
            handler,
        )
        self.assertGreaterEqual(
            handler.count('cached_payload["mw_action_cards_view"] = mw_action_cards_view'),
            2,
        )

    def test_only_four_current_views_are_accepted(self):
        for name, value in (
            ("MW_ACTION_CARDS_VIEW_GENERAL", "general"),
            ("MW_ACTION_CARDS_VIEW_DRAFT", "draft"),
            ("MW_ACTION_CARDS_VIEW_BY_MAP", "by_map"),
            ("MW_ACTION_CARDS_VIEW_SYNERGIES", "synergies"),
        ):
            self.assertIn(f'{name} = "{value}"', SOURCE)
        parser = function_source("_parse_mw_action_cards_view")
        self.assertIn("general, draft, by_map, or synergies", parser)

    def test_mw_only_snapshot_is_in_the_default_pack(self):
        source = function_source("_default_snapshot_pack_blob_names")
        for view in ("general", "by-map", "synergies"):
            self.assertIn(f"mw-action-cards/{view}/default-mw.json", source)
            self.assertNotIn(f"mw-action-cards/{view}/default-base.json", source)

    def test_targeted_refresh_rebuilds_only_current_views(self):
        handler = function_source("get_card_stats")
        self.assertIn('params.get("refresh_mw_action_cards") is True', handler)
        self.assertIn('"general": _refresh_default_snapshot_from_prepared', handler)
        self.assertIn('"by_map": _refresh_default_snapshot_from_prepared', handler)
        self.assertIn('"synergies": _refresh_default_snapshot_from_prepared', handler)
        self.assertIn("_write_default_snapshot_pack(data_version)", handler)

    def test_by_map_is_same_map_only_and_keeps_moments(self):
        prepared = function_source("_refresh_prepared_mw_action_card_tables")
        query = function_source("_build_mw_action_cards_query")
        self.assertIn("WHERE Map = opponent_map", prepared)
        self.assertIn("delta_sum_squares", prepared)
        self.assertIn("PREPARED_MW_ACTION_CARD_MAP_AGGREGATES_TABLE", query)
        self.assertIn("delta_overall_ci_sd", query)

    def test_synergies_are_unordered_two_type_pairs(self):
        prepared = function_source("_refresh_prepared_mw_action_card_tables")
        query = function_source("_build_mw_action_cards_query")
        self.assertIn("ORDER BY card_order", prepared)
        self.assertIn("HAVING COUNT(*) = 2 AND COUNT(DISTINCT card_type) = 2", prepared)
        self.assertIn("s1.individual_delta + s2.individual_delta", query)
        self.assertIn(
            "p.delta_actual - (s1.individual_delta + s2.individual_delta)",
            query,
        )

if __name__ == "__main__":
    unittest.main()
