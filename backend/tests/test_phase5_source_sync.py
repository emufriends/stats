import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from phase3_duckdb_service import _load_duckdb
from phase5_source_sync import (
    DEFAULT_CAP, changed_families, fingerprints, make_plan,
    file_record, validate_files, validate_budget, export_source,
)
from phase5_source_reconcile import reconcile, reconcile_family


class SyncPlanningTests(unittest.TestCase):
    def setUp(self):
        self.metadata = {"full_sample": {"raw": {"lastModifiedTime": "1"}, "routine": "v1"},
                         "logs": {"lastModifiedTime": "2"}}
        self.prior = {"source_fingerprints": fingerprints(self.metadata)}

    def test_unchanged_never_submits_even_dry_run(self):
        client = Mock()
        result = make_plan(client, self.metadata, self.prior, DEFAULT_CAP)
        self.assertEqual(result["status"], "unchanged")
        client.query.assert_not_called()

    def test_raw_data_and_udf_changes_invalidate_full_only(self):
        for key in ("raw", "routine"):
            metadata = copy.deepcopy(self.metadata)
            metadata["full_sample"][key] = "changed"
            self.assertEqual(changed_families(metadata, self.prior), ["full_sample"])

    def test_logs_only_change_has_no_billed_select(self):
        client = Mock()
        self.metadata["logs"]["lastModifiedTime"] = "3"
        result = make_plan(client, self.metadata, self.prior, DEFAULT_CAP)
        self.assertEqual(result["changed_families"], ["logs"])
        self.assertEqual(result["estimated_query_bytes"], 0)
        client.query.assert_not_called()

    def test_budget_rejected_before_export(self):
        client = Mock()
        client.query.return_value.total_bytes_processed = DEFAULT_CAP + 1
        with self.assertRaisesRegex(RuntimeError, "ceiling"):
            make_plan(client, self.metadata, None, DEFAULT_CAP)
        for cap in (0, -1, DEFAULT_CAP + 1):
            with self.assertRaises(ValueError):
                validate_budget(0, cap)

    def test_retries_cannot_mix_source_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sync-request.json").write_text('{}')
            plan = {"status": "planned", "source_fingerprints": fingerprints(self.metadata)}
            with self.assertRaisesRegex(RuntimeError, "another source version"):
                export_source(Mock(), plan, None, root, "private-bucket", "phase5/source-sync")
            self.assertFalse((root / "manifest.json").exists())
            # Kernel ownership is released; the inode remains to avoid races.
            from phase5_process_lock import exclusive
            with exclusive(root / '.sync.lock'):
                pass

    def test_checksum_and_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("full_sample-0.parquet", "logs-0.parquet"):
                (root / name).write_bytes(b"test data")
            manifest = {"files": [file_record(p) for p in root.glob("*.parquet")]}
            validate_files(root, manifest)
            (root / "logs-0.parquet").write_bytes(b"different")
            with self.assertRaisesRegex(RuntimeError, "checksum"):
                validate_files(root, manifest)

    def test_source_moving_during_export_never_commits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = {"status": "planned", "source_fingerprints": fingerprints(self.metadata),
                    "changed_families": ["full_sample", "logs"], "maximum_bytes_billed": DEFAULT_CAP,
                    "metadata": {"logs": {"numRows": "1"}}}
            moved = copy.deepcopy(self.metadata)
            moved["logs"]["lastModifiedTime"] = "3"
            job = Mock(job_id="test", total_bytes_processed=1, total_bytes_billed=1)
            job._properties = {"statistics": {
                "query": {"exportDataStatistics": {"fileCount": "1", "rowCount": "1"}},
                "extract": {"destinationUriFileCounts": ["1"]}}}
            for family in ("full_sample", "logs"):
                (root / f"{family}-0.parquet").write_bytes(b"data")
            with patch("phase5_source_sync.existing_or_submit", return_value=job), \
                 patch("phase5_source_sync.gcloud"), \
                 patch("phase5_source_sync.read_metadata", return_value=moved):
                with self.assertRaisesRegex(RuntimeError, "Source changed during export"):
                    export_source(Mock(), plan, None, root, "private-bucket", "phase5/source-sync")
            self.assertFalse((root / "manifest.json").exists())

    def test_successful_job_retry_attaches_without_resubmitting(self):
        from phase5_source_sync import existing_or_submit
        client, submit = Mock(), Mock()
        result = existing_or_submit(client, "known-id", submit)
        self.assertIs(result, client.get_job.return_value)
        submit.assert_not_called()
        result.result.assert_called_once()


class ReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.duckdb = _load_duckdb()

    def test_historical_addition_correction_deletion_and_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            con = self.duckdb.connect()
            con.execute("CREATE TABLE source_full_sample(table_id BIGINT, player VARCHAR, ev DOUBLE, cards INTEGER[])")
            con.execute("INSERT INTO source_full_sample VALUES (10,'a',1,[1,2]),(10,'b',-1,[]),(20,'a',2,[]),(20,'a',2,[]),(30,'a',NULL,[]),(40,'a',1,[])")
            con.execute("CREATE TABLE fresh AS SELECT * FROM source_full_sample WHERE table_id != 40")
            con.execute("UPDATE fresh SET ev=3 WHERE table_id=10 AND player='a'")
            con.execute("DELETE FROM fresh WHERE table_id=20")
            con.execute("INSERT INTO fresh VALUES (20,'a',2,[]),(1,'late',0.5,[3])")
            path = (root / "full.parquet").as_posix()
            con.execute("COPY (SELECT * FROM fresh ORDER BY player DESC) TO ? (FORMAT PARQUET)", [path])
            result = reconcile_family(con, "source_full_sample", path)
            self.assertEqual(result, {"added_tables": 1, "deleted_tables": 1, "corrected_tables": 2,
                                      "replaced_rows": 5, "inserted_rows": 4, "rows": 5})
            self.assertEqual(con.execute("SELECT * FROM source_full_sample EXCEPT ALL SELECT * FROM fresh").fetchall(), [])
            self.assertEqual(con.execute("SELECT * FROM fresh EXCEPT ALL SELECT * FROM source_full_sample").fetchall(), [])
            self.assertEqual(reconcile_family(con, "source_full_sample", path)["replaced_rows"], 0)
            con.close()

    def test_failure_preserves_parent_and_removes_partial_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = root / "parent.duckdb"
            target = root / "candidate.duckdb"
            con = self.duckdb.connect(str(parent))
            con.execute("CREATE TABLE source_full_sample AS SELECT 1::BIGINT AS table_id, 2 AS score")
            con.execute("CREATE TABLE source_logs AS SELECT 1::BIGINT AS table_id, 'a' AS player")
            con.execute("COPY (SELECT 1::BIGINT AS table_id, 9 AS score) TO ? (FORMAT PARQUET)", [(root / "full_sample-0.parquet").as_posix()])
            # The second family deliberately has an incompatible schema.
            con.execute("COPY (SELECT 1::BIGINT AS table_id, 1 AS incompatible) TO ? (FORMAT PARQUET)", [(root / "logs-0.parquet").as_posix()])
            con.close()
            (root / "manifest.json").write_text(json.dumps({"status": "ok", "generation": "test"}))
            before = file_record(parent)
            with self.assertRaisesRegex(RuntimeError, "schema changed"):
                reconcile(root, parent, target, memory_limit="256MB")
            self.assertFalse(target.exists())
            self.assertEqual(file_record(parent), before)


if __name__ == "__main__":
    unittest.main()
