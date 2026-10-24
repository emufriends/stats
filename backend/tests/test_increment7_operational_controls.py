from __future__ import annotations

import json
import os
import shutil
import threading
import time
import unittest
from datetime import datetime, timezone
import uuid
from contextlib import contextmanager
from pathlib import Path

from phase3_api import Phase3Application
from phase5_operational_controls import (
    BUILD_INPUT_NAMES,
    prune_local_releases,
    prune_source_exports,
    refresh_inputs,
    validate_reusable_candidate,
)
from phase5_refresh_worker import APP_ROOT, _arena_roster_required
from phase5_snapshot_builder import _player_filter_seasons
from phase5_verify_budget_policy import verify
from budget_shutdown_service.policy import evaluate_budget_notification


class _Manager:
    pass


class _SlowAdapter:
    def __init__(self):
        self.calls = 0
        self.lock = threading.Lock()

    def execute(self, request):
        with self.lock:
            self.calls += 1
        time.sleep(0.1)
        return {"status": "ok", "data": [request["stats_page"]]}

    def capabilities(self):
        return {}


class Increment7Tests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[1] / ".test-temp"
        base.mkdir(exist_ok=True)
        self.root = base / f"increment7-{uuid.uuid4().hex}"
        self.root.mkdir()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_ongoing_arena_season_does_not_require_a_roster(self):
        now = datetime(2026, 9, 24, tzinfo=timezone.utc)
        self.assertFalse(_arena_roster_required("2026-10-13 12:00:00", current_time=now))
        self.assertTrue(_arena_roster_required("2026-07-15 12:00:00", current_time=now))
        self.assertTrue(_arena_roster_required("", current_time=now))

    def test_refresh_worker_resolves_code_from_installed_bundle(self):
        self.assertEqual(APP_ROOT, Path(__file__).resolve().parents[1])
        self.assertTrue((APP_ROOT / "phase5_refresh_workflow.py").is_file())
        source = (APP_ROOT / "phase5_refresh_worker.py").read_text(encoding="utf-8")
        self.assertIn('str(APP_ROOT / "phase5_refresh_workflow.py")', source)
        self.assertIn('str(APP_ROOT / "phase5_publish_release.py")', source)
        self.assertIn('workflow, cwd=APP_ROOT', source)
        self.assertIn('refresh_inputs(APP_ROOT, source_root, MOVING_DIR)', source)
        workflow_source = (APP_ROOT / "phase5_refresh_workflow.py").read_text(encoding="utf-8")
        self.assertIn('app_root = builder_path.resolve().parent', workflow_source)
        self.assertIn('refresh_inputs(app_root, source_root, moving_source_dir)', workflow_source)
        self.assertIn('app_root / "phase5_snapshot_builder.py"', workflow_source)

    def test_players_manifest_includes_metadata_only_arena_season(self):
        class Cursor:
            def fetchall(self):
                return [
                    ("S14", datetime(2026, 7, 15, tzinfo=timezone.utc),
                     datetime(2026, 10, 13, tzinfo=timezone.utc), "mw"),
                    ("S13", datetime(2026, 4, 1, tzinfo=timezone.utc),
                     datetime(2026, 7, 1, tzinfo=timezone.utc), "mw"),
                ]

        class Connection:
            def execute(self, _sql):
                return Cursor()

        class Store:
            @contextmanager
            def connection(self):
                yield object(), Connection()

        adapter = type("Adapter", (), {"store": Store()})()
        seasons = _player_filter_seasons(adapter, [{"season": "S13", "number": 13}])
        self.assertEqual([item["season"] for item in seasons], ["S14", "S13"])
        self.assertTrue(seasons[0]["is_mw"])

    def test_identical_inflight_requests_execute_once(self):
        adapter = _SlowAdapter()
        app = Phase3Application(_Manager(), adapter, max_concurrent_queries=2)
        body = json.dumps({"stats_page": "cards"}).encode()
        barrier = threading.Barrier(3)
        results = []

        def call():
            barrier.wait()
            results.append(app.dispatch("POST", "/v1/query", body))

        threads = [threading.Thread(target=call) for _ in range(2)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()
        self.assertEqual(adapter.calls, 1)
        self.assertEqual([status for status, _ in results], [200, 200])

    def test_different_request_waits_for_a_query_slot(self):
        adapter = _SlowAdapter()
        app = Phase3Application(
            _Manager(), adapter, max_concurrent_queries=1,
            query_slot_wait_seconds=0.5,
        )
        first = json.dumps({"stats_page": "cards"}).encode()
        second = json.dumps({"stats_page": "maps"}).encode()
        results = []
        thread = threading.Thread(
            target=lambda: results.append(app.dispatch("POST", "/v1/query", first))
        )
        thread.start()
        time.sleep(0.02)
        results.append(app.dispatch("POST", "/v1/query", second))
        thread.join()
        self.assertEqual(sorted(status for status, _ in results), [200, 200])
        self.assertEqual(adapter.calls, 2)

    def test_refresh_fingerprint_ignores_status_timestamp_and_tracks_inputs(self):
        source = self.root / "source"
        moving = self.root / "moving"
        source.mkdir(); moving.mkdir()
        (source / "manifest.json").write_text(json.dumps({
            "generation": "s1", "source_fingerprints": {"full": "x"}, "files": [],
        }), encoding="utf-8")
        (moving / "arena_settings.csv").write_text("season,date\nS1,2023-01-01\n", encoding="utf-8")
        (moving / "source-status.json").write_text('{"refreshed_at":"one"}', encoding="utf-8")
        (moving / "tournament-metadata.json").write_text(json.dumps({
            "rows": [{"table_id": 1}],
            "source": {"sha256": "x", "row_count": 1, "fetched_at": "one"},
        }), encoding="utf-8")
        (self.root / "merge_players.csv").write_text("a,b\n", encoding="utf-8")
        first = refresh_inputs(self.root, source, moving)["fingerprint"]
        (moving / "source-status.json").write_text('{"refreshed_at":"two"}', encoding="utf-8")
        (moving / "tournament-metadata.json").write_text(json.dumps({
            "rows": [{"table_id": 1}],
            "source": {"sha256": "x", "row_count": 1, "fetched_at": "two"},
        }), encoding="utf-8")
        self.assertEqual(first, refresh_inputs(self.root, source, moving)["fingerprint"])
        (moving / "arena_settings.csv").write_text("season,date\nS2,2024-01-01\n", encoding="utf-8")
        self.assertNotEqual(first, refresh_inputs(self.root, source, moving)["fingerprint"])

    def test_card_metadata_is_a_versioned_build_and_deployment_input(self):
        self.assertIn("cards_attributes.csv", BUILD_INPUT_NAMES)
        package_source = (
            Path(__file__).resolve().parents[1] / "phase5_package_deployment.py"
        ).read_text(encoding="utf-8")
        self.assertIn('root / "cards_attributes.csv"', package_source)
        self.assertIn('root.glob("contracts/**/*")', package_source)

    def test_build_identity_tracks_runtime_imports_but_not_audit_scripts(self):
        source = self.root / 'source'; source.mkdir()
        moving = self.root / 'moving'; moving.mkdir()
        (source / 'manifest.json').write_text('{"generation":"s1"}', encoding='utf-8')
        (self.root / 'phase4_local_routes.py').write_text('import extra_runtime_helper\n', encoding='utf-8')
        (self.root / 'extra_runtime_helper.py').write_text('VALUE=1\n', encoding='utf-8')
        audit = self.root / 'phase4_independent_reconciliation.py'
        audit.write_text('AUDIT=1\n', encoding='utf-8')
        first = refresh_inputs(self.root, source, moving)['fingerprint']
        audit.write_text('AUDIT=2\n', encoding='utf-8')
        self.assertEqual(first, refresh_inputs(self.root, source, moving)['fingerprint'])
        (self.root / 'extra_runtime_helper.py').write_text('VALUE=2\n', encoding='utf-8')
        self.assertNotEqual(first, refresh_inputs(self.root, source, moving)['fingerprint'])

    def test_validated_candidate_requires_complete_checksummed_inventory(self):
        generation = "g1"; fingerprint = "abc"
        generations = self.root / "phase2_private_data" / "generations"
        snapshot = self.root / "phase2_private_data" / "snapshots" / generation
        generations.mkdir(parents=True); snapshot.mkdir(parents=True)
        (generations / f"{generation}.duckdb").write_bytes(b"db")
        (generations / f"{generation}.manifest.json").write_text(json.dumps({
            "refresh_fingerprint": fingerprint, "release": {"status": "validated"},
        }), encoding="utf-8")
        artifact = snapshot / "a.json"; artifact.write_bytes(b"{}")
        import hashlib
        (snapshot / "release-manifest.json").write_text(json.dumps({
            "status": "ok", "generation": generation, "data_version": "v1",
            "snapshot_count": 1, "release_version": "r1", "required_object_keys": ["x/a.json"],
            "artifacts": [{"object_key": "x/a.json", "path": str(artifact), "bytes": 2,
                           "sha256": hashlib.sha256(b"{}").hexdigest()}],
        }), encoding="utf-8")
        self.assertIsNotNone(validate_reusable_candidate(self.root, generation, fingerprint))
        artifact.write_bytes(b"tampered")
        self.assertIsNone(validate_reusable_candidate(self.root, generation, fingerprint))

    def test_retention_preserves_active_pointer_rollback_parent_and_three_newest(self):
        generations = self.root / "phase2_private_data" / "generations"
        generations.mkdir(parents=True)
        for index, name in enumerate(["ancient", "parent", "active", "old1", "new1", "new2"]):
            (generations / f"{name}.duckdb").write_bytes(name.encode())
            (generations / f"{name}.manifest.json").write_text(json.dumps({
                "generation": name, "database": str(generations / f"{name}.duckdb"),
                "parent_generation": "parent" if name == "active" else None,
            }), encoding="utf-8")
            stamp = time.time() + index
            os.utime(generations / f"{name}.manifest.json", (stamp, stamp))
        pointer = self.root / "phase3_private_serving" / "current.json"
        pointer.parent.mkdir(); pointer.write_text(json.dumps({
            "generation": "active", "previous_generation": "old1",
        }), encoding="utf-8")
        report = prune_local_releases(self.root, keep_completed=3)
        self.assertTrue((generations / "active.duckdb").exists())
        self.assertTrue((generations / "parent.duckdb").exists())
        self.assertTrue((generations / "old1.duckdb").exists())
        self.assertIn("ancient", report["removed_generations"])

    def test_checked_in_budget_policy_is_eur_20_40(self):
        result = verify(Path(__file__).resolve().parents[1])
        self.assertEqual(result["status"], "ok")

    def test_source_retention_protects_release_and_inflight_references(self):
        private=self.root / 'phase2_private_data'
        generations=private / 'generations'; generations.mkdir(parents=True)
        source=private / 'source'; source.mkdir()
        for index,name in enumerate(('active','rollback','inflight','orphan','newest')):
            directory=source / ('.source-'+name); directory.mkdir()
            (directory / 'manifest.json').write_text(json.dumps({'generation':name}),encoding='utf-8')
            stamp=time.time()-172800+index
            os.utime(directory,(stamp,stamp))
        for name in ('active','rollback'):
            (generations / (name+'.manifest.json')).write_text(json.dumps({'source_generation':name}),encoding='utf-8')
        report=prune_source_exports(self.root,extra_protected=[source / '.source-inflight'])
        self.assertEqual(report['removed_sources'],['.source-orphan'])
        for name in ('active','rollback','inflight','newest'):
            self.assertTrue((source / ('.source-'+name)).is_dir())

    def test_source_cleanup_fails_closed_on_malformed_release_metadata(self):
        private=self.root / 'phase2_private_data'
        generations=private / 'generations'; generations.mkdir(parents=True)
        source=private / 'source'; source.mkdir()
        directory=source / '.source-orphan'; directory.mkdir()
        stamp=time.time()-172800; os.utime(directory,(stamp,stamp))
        (generations / 'broken.manifest.json').write_text('not JSON',encoding='utf-8')
        with self.assertRaises(json.JSONDecodeError):
            prune_source_exports(self.root,keep_newest=0)
        self.assertTrue(directory.is_dir())

    def test_budget_shutdown_requires_the_eur_40_policy(self):
        self.assertEqual(evaluate_budget_notification({
            "currencyCode": "EUR", "costAmount": 39.99,
        })["action"], "ignored")
        self.assertEqual(evaluate_budget_notification({
            "currencyCode": "EUR", "costAmount": 40,
        })["action"], "stop")
        self.assertEqual(evaluate_budget_notification({
            "currencyCode": "EUR", "budgetAmount": 40,
            "alertThresholdExceeded": 1.0,
        })["action"], "stop")
        self.assertEqual(evaluate_budget_notification({
            "currencyCode": "USD", "costAmount": 100,
        })["action"], "ignored_currency_mismatch")


if __name__ == "__main__":
    unittest.main()
