import contextlib
import json
import shutil
import tempfile
import uuid
import unittest
from pathlib import Path
from unittest import mock

from phase3_duckdb_service import PHASE4_NATIVE_ROUTES
from phase5_snapshot_builder import (
    ROUTE_PATHS, SPECIAL_BUNDLE, STANDARD_MAPS, _attach_component_cis,
    expected_snapshot_object_keys,
    _datasets, _is_pack_member, _player_filter_seasons, _request,
    _release_versions, APP_ROOT,
    _reusable_snapshot_paths,
    build_one,
    _qualified_log_snapshot,
)


class Phase5SnapshotBuilderTests(unittest.TestCase):
    def test_snapshot_reuse_requires_identical_producer_versions(self):
        # Installed deployment bundles are immutable/read-only. Test scratch
        # belongs in the host temporary directory, never inside APP_ROOT.
        root = Path(tempfile.mkdtemp(prefix='snapshot-reuse-'))
        generation = type('Generation', (), {'generation_id': 'candidate', 'data_version': 'v1'})()
        try:
            manifest = {'status': 'ok', 'generation': 'candidate', 'data_version': 'v1',
                        'versions': {'code_sha256': 'old'}, 'artifacts': []}
            (root / 'release-manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            with mock.patch('phase5_snapshot_builder._release_versions',
                            return_value={'code_sha256': 'new'}):
                self.assertEqual(_reusable_snapshot_paths(root, generation), set())
        finally:
            shutil.rmtree(root)

    def test_release_hashes_use_installed_code_not_the_data_root(self):
        generation = type('Generation', (), {'manifest': {}})()
        with mock.patch('phase5_snapshot_builder._sha256_file', side_effect=lambda path: path.name) as digest:
            versions = _release_versions(Path('/not-the-executable-root'), generation)
        self.assertTrue(versions['code_files'])
        self.assertIn('phase5_component_ci.py', versions['code_files'])
        self.assertTrue(all(call.args[0].is_relative_to(APP_ROOT) for call in digest.call_args_list))

    def test_records_bounded_batch_includes_overflow_and_exact_final_batch(self):
        import tempfile
        for total in (10000, 10500):
            class Adapter:
                def __init__(self):
                    self.requests = []
                def execute(self, request):
                    self.requests.append(request)
                    start = request['offset']
                    return {'status':'ok', 'data_version':'v1', 'data':[
                        {'index':index} for index in range(start, min(total,start+request['limit']))]}
            adapter = Adapter()
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory)/'snapshot.json'
                result = build_one(adapter, 'records', 'most_icons', 1, output, 1000)
                self.assertEqual(result['row_count'], total)
                self.assertEqual(len(adapter.requests), 2)
                self.assertTrue(all(request['limit'] == 10000 for request in adapter.requests))
                self.assertEqual([row['index'] for row in json.loads(output.read_text())['data']], list(range(total)))

    def test_cross_generation_snapshot_reuse_requires_exact_population_and_code(self):
        import tempfile
        import hashlib
        from phase5_refresh_dependencies import LOG_RELATIONS
        from phase3_duckdb_service import PUBLIC_CONTRACT_SCHEMA_VERSION
        signature = {'schema_version':2,'engine_version':'v1.4.4','population_sha256':'population','producer_sha256':'producer'}
        versions = {'code_files':{'producer.py':'same'},'contract_sha256':'contract',
                    'public_contract_schema_version':PUBLIC_CONTRACT_SCHEMA_VERSION}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshots = root/'phase2_private_data/snapshots/parent'
            generations = root/'phase2_private_data/generations'
            generations.mkdir(parents=True)
            (snapshots/'card-stats').mkdir(parents=True)
            payload = {'status':'ok','generation':'parent','data_version':'old',
                'contract_schema_version':PUBLIC_CONTRACT_SCHEMA_VERSION,
                'data':[{'delta_played':0.5,'played_ci95_low':0.1}],'row_count':1}
            path = snapshots/'card-stats/default-mw.json'
            path.write_text(json.dumps(payload),encoding='utf-8')
            (generations/'parent.manifest.json').write_text(json.dumps({'builder':{'log_dependency':signature}}))
            release = {'status':'ok','generation':'parent','data_version':'old','versions':versions,
                'artifacts':[{'object_key':'card-stats/default-mw.json','bytes':path.stat().st_size,
                              'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}]}
            (snapshots/'release-manifest.json').write_text(json.dumps(release))
            candidate = type('Generation',(),{'generation_id':'current','data_version':'new',
                'manifest':{'parent_generation':'parent','builder':{'reused_relations':list(LOG_RELATIONS),
                    'log_dependency':dict(signature)}}})()
            with mock.patch('phase5_snapshot_builder._release_versions',return_value=versions):
                result = _qualified_log_snapshot(root,candidate,'card-stats/default-mw.json')
                self.assertEqual(result['generation'],'current')
                self.assertEqual(result['data_version'],'new')
                self.assertEqual(result['data'],payload['data'])
                self.assertIsNone(_qualified_log_snapshot(root,candidate,'card-stats/maps/metrics/default-mw.json'))
                candidate.manifest['builder']['log_dependency']['population_sha256'] = 'changed'
                self.assertIsNone(_qualified_log_snapshot(root,candidate,'card-stats/default-mw.json'))
                candidate.manifest['builder']['log_dependency'] = dict(signature)
            with mock.patch('phase5_snapshot_builder._release_versions',return_value={**versions,'code_files':{'producer.py':'changed'}}):
                self.assertIsNone(_qualified_log_snapshot(root,candidate,'card-stats/default-mw.json'))

    def test_player_filter_seasons_fetches_timezone_values_as_text(self):
        class Result:
            @staticmethod
            def fetchall():
                return [("S14", "2026-07-15 14:00:00+00", "2026-10-13 12:00:00+00", "mw")]

        class Connection:
            def __init__(self):
                self.sql = ""

            def execute(self, sql):
                self.sql = sql
                return Result()

        class Store:
            def __init__(self):
                self.database = Connection()

            @contextlib.contextmanager
            def connection(self):
                yield "generation", self.database

        class Adapter:
            def __init__(self):
                self.store = Store()

        adapter = Adapter()
        seasons = _player_filter_seasons(adapter, [])
        self.assertEqual(seasons[0]["season"], "S14")
        self.assertEqual(seasons[0]["start_utc"], "2026-07-15 14:00:00+00")
        self.assertIn("CAST(start_utc AS VARCHAR)", adapter.store.database.sql)
        self.assertIn("CAST(end_utc AS VARCHAR)", adapter.store.database.sql)

    def test_expected_snapshot_inventory_is_complete_and_dataset_aware(self):
        keys = expected_snapshot_object_keys()
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(keys), 98)
        self.assertIn(
            "card-stats/combinations/card-action-card/default-mw.json", keys
        )
        self.assertNotIn(
            "card-stats/combinations/card-action-card/default-base.json", keys
        )
        self.assertIn("card-stats/players/arena/latest.json", keys)
        self.assertIn("card-stats/players/arena/manifest.json", keys)

    def test_component_ci_snapshot_reuses_repeated_standalone_means(self):
        class Adapter:
            def __init__(self):
                self.requests = []

            def execute(self, request):
                self.requests.append(request)
                data = []
                for descriptor in request["component_ci_rows"]:
                    data.append({
                        "row_key": '["%s","%s"]' % (
                            descriptor["card_name"], descriptor["action_card_key"]
                        ),
                        **{
                            f"component_{index}_{suffix}": index
                            for index in (1, 2)
                            for suffix in (
                                "mean", "ci95_low", "ci95_high", "ci95_se",
                                "ci95_n", "ci95_cluster_n",
                            )
                        },
                    })
                return {"data": data}

        rows = [
            {"card_name": f"Card {card}", "action_card_key": f"Action {action}"}
            for card in range(50) for action in range(20)
        ]
        adapter = Adapter()
        _attach_component_cis(adapter, "combinations", "card_action_card", 1, rows)
        self.assertEqual(len(adapter.requests), 1)
        self.assertEqual(len(adapter.requests[0]["component_ci_rows"]), 69)
        self.assertTrue(all(row["component_1_ci95_n"] == 1 for row in rows))
        self.assertTrue(all(row["component_2_ci95_n"] == 2 for row in rows))

    def test_map_snapshot_does_not_recalculate_context_ci_as_component(self):
        class Adapter:
            def __init__(self):
                self.requests = []

            def execute(self, request):
                self.requests.append(request)
                return {"data": [{
                    "row_key": '["%s","%s"]' % (
                        item["card_name"], item["map_name"]
                    ),
                    "component_1_mean": 0.1,
                    "component_1_ci95_low": 0.0,
                    "component_1_ci95_high": 0.2,
                    "component_1_ci95_se": 0.05,
                    "component_1_ci95_n": 10,
                    "component_1_ci95_cluster_n": 10,
                } for item in request["component_ci_rows"]]}

        rows = [
            {"card_name": f"Card {card}", "map_name": f"Map {map_number}"}
            for card in range(50) for map_number in range(20)
        ]
        adapter = Adapter()
        _attach_component_cis(adapter, "combinations", "card_map", 1, rows)
        self.assertEqual(len(adapter.requests), 1)
        self.assertEqual(len(adapter.requests[0]["component_ci_rows"]), 50)
        self.assertTrue(all(row["component_1_ci95_n"] == 10 for row in rows))
        self.assertTrue(all(row["component_2_ci95_n"] == 0 for row in rows))

    def test_analytical_default_matches_frontend_scope(self):
        request = _request("cards", "default", 1, 1000, 0)
        self.assertEqual(request["maps"], STANDARD_MAPS)
        self.assertEqual(request["player_elo_min"], 300)
        self.assertEqual(request["opponent_elo_min"], 300)
        self.assertEqual(request["date_from"], "2025-01-01")

    def test_players_default_keeps_its_distinct_scope(self):
        request = _request("players", "general", 0, 1000, 0)
        self.assertEqual(request["maps"], STANDARD_MAPS)
        self.assertEqual(request["opponent_elo_min"], 0)
        self.assertIsNone(request["date_from"])
        self.assertNotIn("player_elo_min", request)

    def test_home_and_h2h_remain_unrestricted(self):
        home = _request("home", "default", 1, 1000, 0)
        h2h = _request("maps", "tournament_h2h", 1, 1000, 0)
        self.assertNotIn("maps", home)
        self.assertNotIn("maps", h2h)
        self.assertNotIn("date_from", home)
        self.assertNotIn("date_from", h2h)

    def test_build_uses_its_public_view_field(self):
        request = _request("build", "hexes", 1, 1000, 0)
        self.assertEqual(request["build_view"], "hexes")
        self.assertNotIn("build", request)

    def test_snapshot_route_inventory_is_authoritative(self):
        expected = PHASE4_NATIVE_ROUTES | {("cards", "default"), ("combinations", "card_card")}
        self.assertEqual(
            set(ROUTE_PATHS),
            expected - {SPECIAL_BUNDLE, ("players", "arena_top_100")},
        )

    def test_current_full_release_has_explicit_snapshot_and_pack_membership(self):
        specs = PHASE4_NATIVE_ROUTES | {("cards", "default"), ("combinations", "card_card")}
        entries = [
            {"page": "arena", "view": "top_100", "object_key": key}
            for key in (
                "card-stats/players/arena-top-100/all-seasons.json",
                "card-stats/players/arena/latest.json",
                "card-stats/players/arena/manifest.json",
            )
        ]
        for page, view in sorted(specs - {SPECIAL_BUNDLE, ("players", "arena_top_100")}):
            bases = ROUTE_PATHS[(page, view)]
            bases = bases if isinstance(bases, list) else [bases]
            datasets = [1] if (page, view) == ("combinations", "card_action_card") else _datasets(page)
            for dataset in datasets:
                suffix = "mw" if dataset in (None, 1) else "base"
                entries.extend({
                    "page": page, "view": view,
                    "object_key": f"{base}/default-{suffix}.json",
                } for base in bases)
        self.assertEqual(len(entries), 98)
        self.assertEqual(sum(_is_pack_member(item) for item in entries), 89)


if __name__ == "__main__":
    unittest.main()
