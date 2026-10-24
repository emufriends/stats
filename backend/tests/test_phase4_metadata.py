import pathlib
import tempfile
import unittest

from phase4_metadata import (
    MetadataValidationError,
    materialize_metadata_tables,
    parse_arena_settings_csv,
    parse_tournament_csv,
)


class Phase4MetadataTests(unittest.TestCase):
    def test_tournament_sheet_is_normalized_and_duplicate_rows_are_idempotent(self):
        raw = (
            b"table_id,tournament_name,season\n"
            b"123,Snark,7\n123,Snark,7\n"
        )
        rows, info = parse_tournament_csv(raw)
        self.assertEqual(rows, [{"table_id": 123, "tournament_name": "Snark", "season": "7"}])
        self.assertEqual(info["row_count"], 1)
        self.assertEqual(len(info["sha256"]), 64)

    def test_tournament_conflicts_and_missing_values_fail_closed(self):
        with self.assertRaises(MetadataValidationError):
            parse_tournament_csv(b"table_id,tournament_name,season\n123,Snark,7\n123,Emu,7\n")
        with self.assertRaises(MetadataValidationError):
            parse_tournament_csv(b"table_id,tournament_name,season\n123,,7\n")

    def test_arena_settings_normalize_naive_utc_timestamps(self):
        rows, _ = parse_arena_settings_csv(
            b"Season,Start (UTC),End (UTC),Mode\n"
            b"S14,2026-07-15 14:00:00,2026-10-13 12:00:00,MW\n"
        )
        self.assertEqual(rows[0]["season"], "S14")
        self.assertEqual(rows[0]["mode"], "mw")
        self.assertTrue(rows[0]["start_utc"].endswith("+00:00"))

    def test_materialized_tables_have_the_private_metadata_contract(self):
        try:
            import duckdb
        except ImportError:  # pragma: no cover - environment-specific
            self.skipTest("duckdb unavailable")
        with tempfile.TemporaryDirectory() as directory:
            connection = duckdb.connect(str(pathlib.Path(directory) / "metadata.duckdb"))
            materialize_metadata_tables(
                connection,
                [{"table_id": 123, "tournament_name": "Snark", "season": "7"}],
                [{"season": "S14", "start_utc": "2026-07-15T14:00:00+00:00", "end_utc": "2026-10-13T12:00:00+00:00", "mode": "mw"}],
            )
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM tournament_tables_metadata").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM arena_seasons_metadata").fetchone()[0], 1)
            connection.close()


if __name__ == "__main__":
    unittest.main()
