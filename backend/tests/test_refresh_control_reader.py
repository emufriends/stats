"""Refresh polling must be cheap, bounded and fail closed on uncertain reads."""
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import phase5_refresh_worker as worker


def response(value):
    return io.BytesIO(json.dumps(value).encode())


def http_error(code):
    return HTTPError("https://storage.googleapis.com/", code, "error", {}, None)


class ControlReaderTests(unittest.TestCase):
    def test_cached_vm_token_and_encoded_object_path(self):
        reader = worker.ControlReader()
        with patch.object(worker.urllib.request, "urlopen", side_effect=[
            response({"access_token": "private-test-token", "expires_in": 3600}),
            response({"run_id": "one"}), response({"run_id": "two"}),
        ]) as opening, patch.object(worker, "gcloud") as cli:
            self.assertEqual(reader.read("bucket", "a/b space.json"), {"run_id": "one"})
            self.assertEqual(reader.read("bucket", "a/b space.json"), {"run_id": "two"})
            self.assertEqual(opening.call_count, 3)
            self.assertIn("a%2Fb%20space.json?alt=media", opening.call_args.args[0].full_url)
            self.assertEqual(opening.call_args.kwargs["timeout"], 15)
            cli.assert_not_called()

    def test_only_explicit_not_found_means_missing(self):
        for code in [404, 403, 429, 500, 503]:
            with self.subTest(code=code):
                reader = worker.ControlReader()
                reader.token, reader.expires_at = "test", float("inf")
                with patch.object(worker.urllib.request, "urlopen", side_effect=http_error(code)):
                    if code == 404:
                        self.assertIsNone(reader.read("bucket", "key"))
                    else:
                        with self.assertRaises(worker.ControlReadError):
                            reader.read("bucket", "key")

    def test_authentication_refreshes_token_once(self):
        reader = worker.ControlReader()
        reader.token, reader.expires_at = "expired", float("inf")
        with patch.object(worker.urllib.request, "urlopen", side_effect=[
            http_error(401), response({"access_token": "replacement", "expires_in": 3600}),
            response({"state": "idle"}),
        ]) as opening:
            self.assertEqual(reader.read("bucket", "key"), {"state": "idle"})
            self.assertEqual(opening.call_count, 3)

    def test_invalid_json_timeout_and_transport_do_not_mean_missing(self):
        for outcome in [io.BytesIO(b"not json"), response([]), TimeoutError("secret"), URLError("secret")]:
            with self.subTest(outcome=type(outcome).__name__):
                reader = worker.ControlReader()
                reader.token, reader.expires_at = "test", float("inf")
                kwargs = {"side_effect": outcome} if isinstance(outcome, Exception) else {"return_value": outcome}
                with patch.object(worker.urllib.request, "urlopen", **kwargs):
                    with self.assertRaises(worker.ControlReadError) as raised:
                        reader.read("bucket", "key")
                    self.assertNotIn("secret", str(raised.exception))

    def test_idle_poll_failure_preserves_request_and_retries(self):
        with patch.object(worker, "WORK_DIR"), \
             patch.object(worker, "PRIVATE", Path(__file__).parent), \
             patch.object(worker, "KEEP_ALIVE", True), \
             patch.object(worker, "read_json", side_effect=[worker.ControlReadError("timeout"), None]), \
             patch.object(worker.time, "sleep", side_effect=[None, KeyboardInterrupt]), \
             patch.object(worker, "run_refresh") as refresh, \
             patch.object(worker, "release_lock") as release, \
             patch.object(worker, "gcloud") as cli:
            with self.assertRaises(KeyboardInterrupt):
                worker.main()
            refresh.assert_not_called()
            release.assert_not_called()
            cli.assert_not_called()


if __name__ == "__main__":
    unittest.main()
