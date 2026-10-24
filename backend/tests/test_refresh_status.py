import ast
import datetime
import hmac
import pathlib
import threading
import types
import unittest
import uuid
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
MAIN_PATH = ROOT / "main.py"


def load_refresh_code():
    names = {
        "_utc_now_iso",
        "_has_refresh_page_auth",
        "_RefreshProgress",
        "_run_tracked_daily_refresh",
    }
    tree = ast.parse(MAIN_PATH.read_text(encoding="utf-8"))
    selected = [
        node for node in tree.body
        if (isinstance(node, ast.FunctionDef) or isinstance(node, ast.ClassDef))
        and node.name in names
    ]
    namespace = {
        "datetime": datetime.datetime,
        "timezone": datetime.timezone,
        "hmac": hmac,
        "threading": threading,
        "uuid": uuid,
        "REFRESH_PAGE_PASSWORD": None,
        "_REFRESH_PROGRESS_STATE_LOCK": threading.Lock(),
        "_ACTIVE_REFRESH_PROGRESS": None,
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(MAIN_PATH), "exec"), namespace)
    return namespace


class RefreshStatusTests(unittest.TestCase):
    def setUp(self):
        self.main = load_refresh_code()

    def test_refresh_password_uses_dedicated_header(self):
        request = types.SimpleNamespace(
            headers={"X-Ark-Nova-Refresh-Password": "correct"}
        )
        self.main["REFRESH_PAGE_PASSWORD"] = "correct"
        try:
            self.assertTrue(self.main["_has_refresh_page_auth"](request))
            request.headers["X-Ark-Nova-Refresh-Password"] = "wrong"
            self.assertFalse(self.main["_has_refresh_page_auth"](request))
        finally:
            self.main["REFRESH_PAGE_PASSWORD"] = None

    def test_progress_is_monotonic_and_failure_preserves_completion(self):
        writes = []
        previous = {
            "state": "succeeded",
            "last_completed_at": "2026-08-18T01:30:00+00:00",
            "completed_data_version": "version-1",
        }
        self.main["_read_refresh_status"] = mock.Mock(return_value=previous)
        self.main["_write_refresh_status"] = mock.Mock(
            side_effect=lambda payload: writes.append(dict(payload)) or True
        )
        try:
            progress = self.main["_RefreshProgress"]("run-1")
            progress.report(60, "Later stage")
            progress.report(20, "Stale stage")
            progress.fail()
        finally:
            self.main.pop("_read_refresh_status", None)
            self.main.pop("_write_refresh_status", None)

        self.assertEqual(writes[-1]["state"], "failed")
        self.assertEqual(writes[-1]["progress_percent"], 60)
        self.assertEqual(writes[-1]["last_completed_at"], previous["last_completed_at"])
        self.assertEqual(writes[-1]["completed_data_version"], "version-1")

    def test_concurrent_refresh_attaches_without_running_work(self):
        current = {"state": "running", "run_id": "existing", "progress_percent": 42}
        run_refresh = mock.Mock()
        self.main.update({
            "_acquire_refresh_lock": mock.Mock(return_value=False),
            "_read_refresh_status": mock.Mock(return_value=current),
            "_run_daily_refresh": run_refresh,
        })
        payload = self.main["_run_tracked_daily_refresh"]()

        self.assertEqual(payload["status"], "running")
        self.assertEqual(payload["refresh_status"], current)
        run_refresh.assert_not_called()

    def test_success_records_completion_after_main_refresh(self):
        events = []

        class FakeProgress:
            def __init__(self, run_id):
                self.run_id = run_id

            def complete(self, data_version):
                events.append(("complete", data_version))

            def fail(self):
                events.append(("failed", None))

        self.main.update({
            "_acquire_refresh_lock": mock.Mock(return_value=True),
            "_release_refresh_lock": mock.Mock(),
            "_RefreshProgress": FakeProgress,
            "_run_daily_refresh": mock.Mock(
                return_value={"status": "ok", "data_version": "version-2"}
            ),
        })
        payload = self.main["_run_tracked_daily_refresh"]()

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(events, [("complete", "version-2")])


if __name__ == "__main__":
    unittest.main()
