"""Public HTTPS gateway for the private DuckDB API.

The gateway exposes only the existing read-only API paths and forwards them to
the VM's internal address. It never accepts SQL, filesystem paths, activation
commands, or arbitrary upstream URLs.

Dashboard readers are anonymous. The upstream HTTP hop has no bearer-token
protocol: private networking/firewall configuration must protect port 8787.
ALLOWED_ORIGINS controls browser CORS, not non-browser access. Source defaults
for auto-start and IAM are not evidence of installed production policy.
"""

from __future__ import annotations

import json
import os
import time
from http.server import BaseHTTPRequestHandler
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
try:
    from .http_limits import BoundedHTTPServer
except ImportError:  # Container/direct script entry point.
    from http_limits import BoundedHTTPServer


UPSTREAM = os.environ.get("DUCKDB_UPSTREAM", "http://10.132.0.2:8787").rstrip("/")
MAX_REQUEST_BODY = int(os.environ.get("MAX_REQUEST_BODY_BYTES", str(1024 * 1024)))
# Large analytical responses (notably Players history and unpaged Combos) are
# legitimate dashboard payloads.  Keep request validation strict, but give
# responses their own explicit bound instead of reusing the 1 MiB upload cap.
# Production explicitly sets MAX_RESPONSE_BODY_BYTES=16777216, including the
# complete Arena season bundle; do not inherit an older image's smaller default.
MAX_RESPONSE_BODY = int(os.environ.get("MAX_RESPONSE_BODY_BYTES", str(16 * 1024 * 1024)))
# Allow the API's 10-second admission wait and 90-second query deadline to
# return their own mapped response before the proxy's connection deadline.
TIMEOUT = float(os.environ.get("DUCKDB_UPSTREAM_TIMEOUT", "110"))
ALLOWED_PATHS = {"/healthz", "/gateway-healthz", "/readyz", "/v1/status", "/v1/capabilities", "/v1/query"}
UPSTREAM_PATHS = {"/gateway-healthz": "/healthz"}
AUTO_START_VM = os.environ.get("AUTO_START_VM", "false").lower() in {"1", "true", "yes", "on"}
COMPUTE_PROJECT = os.environ.get("COMPUTE_PROJECT", "ark-nova-stats-dashboard")
COMPUTE_ZONE = os.environ.get("COMPUTE_ZONE", "europe-west1-c")
COMPUTE_INSTANCE = os.environ.get("COMPUTE_INSTANCE", "ark-nova-duckdb-test")
START_TIMEOUT = float(os.environ.get("START_TIMEOUT", "75"))
ALLOWED_ORIGINS = {
    origin.strip()
    for origin in os.environ.get(
        "ALLOWED_ORIGINS",
        "https://emufriends.github.io,http://127.0.0.1:8767,http://localhost:8767",
    ).split(",")
    if origin.strip()
}


class GatewayHandler(BaseHTTPRequestHandler):
    server_version = "ArkNovaDuckDBGateway/1"

    def _origin(self) -> str | None:
        origin = self.headers.get("Origin")
        return origin if origin in ALLOWED_ORIGINS else None

    def _headers(self, content_type: str = "application/json; charset=utf-8") -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        origin = self._origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def _send(self, status: int, body: bytes, content_type: str = "application/json; charset=utf-8", retry_after: str | None = None) -> None:
        self.send_response(status)
        self._headers(content_type)
        self.send_header("Content-Length", str(len(body)))
        if retry_after and retry_after.isdigit():
            self.send_header('Retry-After', retry_after)
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, code: str, message: str) -> None:
        self._send(status, json.dumps({"status": "error", "error": code, "message": message}, separators=(",", ":")).encode())

    @staticmethod
    def _start_vm() -> None:
        from google.auth import default as google_auth_default
        from google.auth.transport.requests import AuthorizedSession

        credentials, _ = google_auth_default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        session = AuthorizedSession(credentials)
        url = (
            "https://compute.googleapis.com/compute/v1/projects/"
            f"{COMPUTE_PROJECT}/zones/{COMPUTE_ZONE}/instances/{COMPUTE_INSTANCE}/start"
        )
        response = session.post(url, timeout=20)
        if response.status_code not in (200, 201, 202, 409):
            raise RuntimeError(f"VM start returned {response.status_code}")

    @staticmethod
    def _upstream_available() -> bool:
        try:
            with urlopen(Request(f"{UPSTREAM}/healthz", method="GET"), timeout=3) as response:
                return 200 <= response.status < 300
        except (HTTPError, URLError, TimeoutError, OSError):
            return False

    def _wake_vm_if_needed(self, path: str, method: str) -> bool:
        # Health and capability probes must not incur VM startup or compute
        # charges.  Only a real filtered read may request an on-demand wake.
        if path != "/v1/query" or method != "POST":
            return False
        if not AUTO_START_VM or self._upstream_available():
            return False
        try:
            self._start_vm()
        except Exception:
            return False
        deadline = time.monotonic() + START_TIMEOUT
        while time.monotonic() < deadline:
            if self._upstream_available():
                return True
            time.sleep(2)
        return False

    def _proxy(self, method: str) -> None:
        path = self.path.split("?", 1)[0]
        if path not in ALLOWED_PATHS:
            self._error(404, "not_found", "endpoint does not exist")
            return
        if method == "POST":
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._error(400, "invalid_length", "invalid request length")
                return
            if length < 0 or length > MAX_REQUEST_BODY:
                self._error(413, "request_too_large", "request body is too large")
                return
            try:
                body = self.rfile.read(length)
            except TimeoutError:
                self._error(408, 'request_timeout', 'request body timed out')
                return
            if len(body) != length:
                self._error(400, 'incomplete_body', 'request body is incomplete')
                return
            if self.headers.get("Content-Type", "").split(";", 1)[0].lower() != "application/json":
                self._error(415, "unsupported_media_type", "JSON is required")
                return
        else:
            body = None
        request = Request(
            f"{UPSTREAM}{UPSTREAM_PATHS.get(path, path)}",
            data=body,
            method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=TIMEOUT) as response:
                payload = response.read(MAX_RESPONSE_BODY + 1)
                if len(payload) > MAX_RESPONSE_BODY:
                    self._error(502, "upstream_response_too_large", "upstream response is too large")
                    return
                self._send(response.status, payload, response.headers.get_content_type() + "; charset=utf-8")
        except HTTPError as exc:
            payload = exc.read(MAX_REQUEST_BODY + 1)
            self._send(exc.code, payload[:MAX_REQUEST_BODY], retry_after=exc.headers.get('Retry-After'))
        except (URLError, TimeoutError, OSError):
            if self._wake_vm_if_needed(path, method):
                try:
                    with urlopen(request, timeout=TIMEOUT) as response:
                        payload = response.read(MAX_RESPONSE_BODY + 1)
                        if len(payload) > MAX_RESPONSE_BODY:
                            self._error(502, "upstream_response_too_large", "upstream response is too large")
                            return
                        self._send(response.status, payload, response.headers.get_content_type() + "; charset=utf-8")
                        return
                except (HTTPError, URLError, TimeoutError, OSError):
                    pass
            self._error(503, "upstream_unavailable", "private DuckDB service is unavailable")

    def do_OPTIONS(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] not in ALLOWED_PATHS:
            self._error(404, "not_found", "endpoint does not exist")
            return
        self.send_response(204)
        self._headers("")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        self._proxy("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._proxy("POST")

    def log_message(self, _format: str, *args: object) -> None:
        return


def main() -> int:
    port = int(os.environ.get("PORT", "8080"))
    server = BoundedHTTPServer(("0.0.0.0", port), GatewayHandler,
        max_connections=int(os.environ.get('MAX_HTTP_CONNECTIONS', '24')),
        read_timeout=float(os.environ.get('HTTP_READ_TIMEOUT', '15')))
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
