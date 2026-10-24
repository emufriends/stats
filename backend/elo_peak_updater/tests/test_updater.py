import unittest
from datetime import datetime, timezone
from decimal import Decimal

from updater import (
    MemoryStateStore,
    PeakRecord,
    SheetRow,
    _scheduled_run_id,
    build_discord_messages,
    build_peak_query,
    comparison_rating,
    execute_update,
    plan_row_update,
    quantize_rating,
)


class FakeSheets:
    def __init__(self, payload=None):
        self.requests = []
        self.operation = None
        self.payload = payload

    def spreadsheets(self):
        return self

    def get(self, **kwargs):
        self.operation = "get"
        return self

    def batchUpdate(self, **kwargs):
        self.operation = "batchUpdate"
        self.requests.append(kwargs)
        return self

    def execute(self):
        if self.operation == "get":
            return self.payload or {
                "sheets": [
                    {"properties": {"sheetId": index, "title": title}, "data": []}
                    for index, title in enumerate(("Masters", "Experts", "Candidates", "Ineligible"), start=1)
                ]
            }
        return {}


class FakeQueryResult:
    def __init__(self, rows):
        self.rows = rows

    def result(self):
        return self.rows


class FakeBigQuery:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def query(self, query, job_config=None):
        self.queries.append((query, job_config))
        return FakeQueryResult(self.rows)


def row(**kwargs):
    defaults = dict(
        sheet_title="Masters",
        sheet_id=1,
        row_number=2,
        name="Player One",
        player_id="p1",
        elo_rating=Decimal("500.00"),
        elo_date="2026-01-01",
        elo_table_id="100",
        elo_url="https://example/100",
        arena_rating=Decimal("1200.00"),
        arena_table_id="200",
        arena_url="https://example/200",
    )
    defaults.update(kwargs)
    return SheetRow(**defaults)


class UpdaterTests(unittest.TestCase):
    def test_future_scheduler_time_gets_a_manual_run_id(self):
        run_id = _scheduled_run_id(
            {"X-CloudScheduler-ScheduleTime": "2026-09-02T17:00:00-07:00"},
            datetime(2026, 9, 2, 10, 36, tzinfo=timezone.utc),
        )
        self.assertTrue(run_id.startswith("manual-"))

    def test_current_scheduler_time_remains_idempotent(self):
        run_id = _scheduled_run_id(
            {"X-CloudScheduler-ScheduleTime": "2026-09-02T10:36:00Z"},
            datetime(2026, 9, 2, 10, 36, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(run_id, "scheduled-2026-09-02T10_36_00Z")

    def test_query_uses_raw_full_sample_fields_and_latest_tie_order(self):
        query = build_peak_query()
        self.assertIn("post_match_elo", query)
        self.assertIn("post_match_arena_rating", query)
        self.assertIn("game_ended_at DESC, table_id DESC, url DESC", query)
        self.assertIn("@player_ids", query)
        self.assertIn("FORMAT_DATE('%Y-%m-%d'", query)

    def test_higher_elo_updates_value_date_table_link_and_notifies_masters(self):
        update = plan_row_update(
            row(),
            {
                "elo": PeakRecord(Decimal("501.25"), "101", "https://example/101", "2026-02-03"),
                "arena": None,
            },
        )
        self.assertEqual(update.elo_peak_updates, 1)
        self.assertEqual(len(update.elo_increases), 1)
        self.assertEqual(update.elo_increases[0]["old"], "500.00")
        self.assertEqual(update.elo_increases[0]["new"], "501.25")
        self.assertEqual({r["updateCells"]["start"]["columnIndex"] for r in update.requests}, {5, 6, 12})
        date_request = next(r for r in update.requests if r["updateCells"]["start"]["columnIndex"] == 6)
        date_cell = date_request["updateCells"]["rows"][0]["values"][0]
        self.assertEqual(date_cell["userEnteredValue"]["numberValue"], 46056)
        self.assertEqual(date_cell["userEnteredFormat"]["numberFormat"]["pattern"], "yyyy-mm-dd")

    def test_lower_elo_does_not_overwrite_manual_higher_value(self):
        update = plan_row_update(
            row(elo_rating=Decimal("600.00")),
            {"elo": PeakRecord(Decimal("599.99"), "101", "https://example/101", "2026-02-03"), "arena": None},
        )
        self.assertEqual(update.requests, [])
        self.assertEqual(update.elo_increases, [])

    def test_equal_elo_repairs_metadata_without_writing_rating(self):
        update = plan_row_update(
            row(elo_date="26-01-01", elo_table_id="old", elo_url="https://old"),
            {"elo": PeakRecord(Decimal("500.00"), "101", "https://example/101", "2026-02-03"), "arena": None},
        )
        self.assertEqual(update.elo_peak_updates, 0)
        self.assertEqual(update.elo_increases, [])
        self.assertEqual({r["updateCells"]["start"]["columnIndex"] for r in update.requests}, {5, 6, 12})
        self.assertTrue(all("userEnteredValue" not in r["updateCells"]["rows"][0]["values"][0] for r in update.requests if r["updateCells"]["start"]["columnIndex"] == 5))

    def test_equal_elo_repairs_matching_text_date_as_a_real_date(self):
        update = plan_row_update(
            row(elo_date="2026-01-01", elo_date_is_date=False),
            {"elo": PeakRecord(Decimal("500.00"), "100", "https://example/100", "2026-01-01"), "arena": None},
        )
        date_request = next(r for r in update.requests if r["updateCells"]["start"]["columnIndex"] == 6)
        date_cell = date_request["updateCells"]["rows"][0]["values"][0]
        self.assertEqual(date_cell["userEnteredValue"]["numberValue"], 46023)
        self.assertEqual(date_cell["userEnteredFormat"]["numberFormat"]["pattern"], "yyyy-mm-dd")

    def test_lower_arena_does_not_overwrite_existing_rating(self):
        update = plan_row_update(
            row(arena_rating=Decimal("1400.00")),
            {"elo": None, "arena": PeakRecord(Decimal("1399.99"), "201", "https://example/201")},
        )
        self.assertEqual(update.requests, [])

    def test_equal_arena_repairs_table_and_link_only(self):
        update = plan_row_update(
            row(arena_table_id="old", arena_url="https://old"),
            {"elo": None, "arena": PeakRecord(Decimal("1200.00"), "201", "https://example/201")},
        )
        self.assertEqual({r["updateCells"]["start"]["columnIndex"] for r in update.requests}, {7, 13})
        self.assertEqual(update.arena_peak_updates, 0)

    def test_candidates_do_not_appear_in_discord_updates(self):
        update = plan_row_update(
            row(sheet_title="Candidates"),
            {"elo": PeakRecord(Decimal("501.00"), "101", "https://example/101", "2026-02-03"), "arena": None},
        )
        self.assertEqual(update.elo_peak_updates, 1)
        self.assertEqual(update.elo_increases, [])

    def test_blank_rating_is_updated(self):
        update = plan_row_update(
            row(elo_rating=None, arena_rating=None),
            {
                "elo": PeakRecord(Decimal("501.00"), "101", "https://example/101", "2026-02-03"),
                "arena": PeakRecord(Decimal("1201.00"), "201", "https://example/201"),
            },
        )
        self.assertEqual(update.elo_peak_updates, 1)
        self.assertEqual(update.arena_peak_updates, 1)

    def test_discord_none_message(self):
        self.assertEqual(build_discord_messages([], datetime(2026, 9, 2, tzinfo=timezone.utc).date()), ["__**New elo peaks: 2026-09-02**__\n- None"])

    def test_discord_line_format(self):
        self.assertEqual(
            build_discord_messages(
                [{"name": "Test Player", "old": "900.00", "new": "901.00"}],
                datetime(2026, 9, 2, tzinfo=timezone.utc).date(),
            ),
            ["__**New elo peaks: 2026-09-02**__\n- __Test Player:__ 900.00 → **901.00**"],
        )

    def test_discord_lines_are_sorted_by_new_elo_descending(self):
        messages = build_discord_messages(
            [
                {"name": "Player A", "old": "900.00", "new": "905.00"},
                {"name": "Player B", "old": "800.00", "new": "910.00"},
                {"name": "Player C", "old": "899.00", "new": "905.00"},
            ],
            datetime(2026, 9, 2, tzinfo=timezone.utc).date(),
        )
        self.assertEqual(
            messages,
            [
                "__**New elo peaks: 2026-09-02**__\n"
                "- __Player B:__ 800.00 → **910.00**\n"
                "- __Player A:__ 900.00 → **905.00**\n"
                "- __Player C:__ 899.00 → **905.00**"
            ],
        )

    def test_na_arena_rating_is_compared_as_zero(self):
        self.assertEqual(comparison_rating(None), Decimal("0.00"))
        update = plan_row_update(
            row(arena_rating=None),
            {"elo": None, "arena": PeakRecord(Decimal("1.00"), "201", "https://example/201")},
        )
        self.assertEqual(update.arena_peak_updates, 1)

    def test_execute_update_is_resume_safe(self):
        cells = [{} for _ in range(9)]
        cells[0] = {"effectiveValue": {"stringValue": "Player One"}}
        cells[8] = {"effectiveValue": {"stringValue": "p1"}}
        sheets = FakeSheets({
            "sheets": [
                {
                    "properties": {"sheetId": index, "title": title},
                    "data": ([{"startRow": 0, "rowData": [{"values": cells}]}] if title == "Masters" else []),
                }
                for index, title in enumerate(("Masters", "Experts", "Candidates", "Ineligible"), start=1)
            ]
        })
        bq = FakeBigQuery([{
            "player_id": "p1",
            "elo_rating": 501.0,
            "elo_table_id": "101",
            "elo_url": "https://example/101",
            "elo_date": "2026-09-01",
            "arena_rating": None,
            "arena_table_id": None,
            "arena_url": None,
        }])
        state = MemoryStateStore()
        sent = []
        result = execute_update(
            sheets_service=sheets,
            bigquery_client=bq,
            state_store=state,
            webhook_sender=lambda url, content: sent.append(content),
            webhook_url="https://discord.invalid/webhook",
            run_id="scheduled-test",
            now=datetime(2026, 9, 2, tzinfo=timezone.utc),
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(sent), 1)
        self.assertEqual(len(bq.queries), 1)
        result2 = execute_update(
            sheets_service=sheets,
            bigquery_client=bq,
            state_store=state,
            webhook_sender=lambda url, content: sent.append(content),
            webhook_url="https://discord.invalid/webhook",
            run_id="scheduled-test",
            now=datetime(2026, 9, 2, tzinfo=timezone.utc),
        )
        self.assertEqual(result2["status"], "ok")
        self.assertEqual(len(sent), 1)
        self.assertEqual(len(bq.queries), 1)

    def test_rating_quantization(self):
        self.assertEqual(quantize_rating("501.245"), Decimal("501.25"))


if __name__ == "__main__":
    unittest.main()
