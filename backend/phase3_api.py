"""Private production HTTP process for the dashboard DuckDB service.

The development default binds to loopback. The production systemd unit binds
to all interfaces on port 8787; network access is controlled by the VM's
deployment/firewall configuration. The public Cloud Run gateway is the
dashboard's external query boundary. It exposes only health, readiness, capabilities, status, and the
allow-listed query adapter. Arbitrary SQL and generation-management operations
are not HTTP endpoints.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import threading
import time
from importlib import import_module
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from phase3_duckdb_service import (
    DuckDBServingStore,
    GenerationManager,
    Phase3AuditLog,
    Phase3RequestAdapter,
    QueryDeadlineExceeded,
    ServingStateError,
    UnsupportedRouteError,
    create_private_adapter,
    warm_interactive_generation,
)
from phase5_query_pause import RefreshQueryGate, AnalyticalRequestsPaused


MAX_REQUEST_BYTES = 1024 * 1024
# Shared helper is also copied into the gateway container. import_module accepts
# the existing directory's hyphenated namespace without changing deployed paths.
BoundedHTTPServer = import_module('cloudrun-duckdb-gateway.http_limits').BoundedHTTPServer


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"cannot serialize {type(value).__name__}")


class Phase3Application:
    """Pure request dispatcher used by both tests and the HTTP handler."""

    def __init__(
        self,
        manager: GenerationManager,
        adapter: Phase3RequestAdapter,
        max_concurrent_queries: int = 2,
        query_slot_wait_seconds: float | None = None,
        query_gate: RefreshQueryGate | None = None,
    ) -> None:
        if max_concurrent_queries < 1:
            raise ValueError("max_concurrent_queries must be positive")
        self.manager = manager
        self.adapter = adapter
        self.query_gate = query_gate
        self.maintenance_only = bool(query_gate and query_gate.fully_paused())
        self.store = DuckDBServingStore(manager)
        self.query_slots = threading.BoundedSemaphore(max_concurrent_queries)
        if query_slot_wait_seconds is None:
            query_slot_wait_seconds = float(
                os.environ.get("PHASE3_QUERY_SLOT_WAIT_SECONDS", "10")
            )
        if query_slot_wait_seconds < 0:
            raise ValueError("query_slot_wait_seconds cannot be negative")
        self.query_slot_wait_seconds = query_slot_wait_seconds
        self._inflight_lock = threading.Lock()
        self._inflight: dict[str, dict[str, Any]] = {}
        self.shared_wait_seconds = max(
            1.0, float(os.environ.get("PHASE3_SHARED_REQUEST_WAIT_SECONDS", "95"))
        )

    @staticmethod
    def _request_key(request: Mapping[str, Any]) -> str:
        canonical = json.dumps(request, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _error(code: str, message: str) -> dict[str, Any]:
        return {"status": "error", "error": code, "message": message}

    @staticmethod
    def _serving_state(payload: Mapping[str, Any]) -> dict[str, Any]:
        """Expose generation state without local filesystem information."""

        allowed = {
            "state", "generation", "data_version", "activated_at",
            "previous_generation", "ready", "rollback_ready",
        }
        return {key: value for key, value in payload.items() if key in allowed}

    def dispatch(
        self, method: str, path: str, body: bytes = b"",
    ) -> tuple[int, dict[str, Any]]:
        # Covers queued and shared requests as well as actual SQL. The worker
        # cannot start memory-heavy stages until every admitted request ends.
        if method.upper() == 'POST' and urlsplit(path).path == '/v1/query' and self.query_gate:
            if self.maintenance_only:
                return 503, self._error('refresh_in_progress',
                    'The dashboard is refreshing. Filters and selected-player statistics '
                    'are temporarily paused. Default tables remain available. '
                    'Please try again after the refresh.')
            try:
                with self.query_gate.query():
                    return self._dispatch(method, path, body)
            except AnalyticalRequestsPaused:
                return 503, self._error('refresh_in_progress',
                    'The dashboard is refreshing. Filters and selected-player statistics '
                    'are temporarily paused. Default tables remain available. '
                    'Please try again after the refresh.')
        return self._dispatch(method, path, body)

    def _dispatch(
        self,
        method: str,
        path: str,
        body: bytes = b"",
    ) -> tuple[int, dict[str, Any]]:
        route = urlsplit(path).path
        method = method.upper()
        if method == "GET" and route == "/healthz":
            try:
                payload = self._serving_state(self.store.health())
                return (200 if payload.get("ready") else 503), payload
            except ServingStateError:
                return 503, self._error(
                    "serving_unavailable", "private serving generation is unavailable"
                )
        if method == "GET" and route == "/readyz":
            try:
                payload = self._serving_state(self.manager.readiness())
                return (200 if payload.get("ready") else 503), payload
            except ServingStateError:
                return 503, self._error(
                    "serving_unavailable", "private serving generation is unavailable"
                )
        if method == "GET" and route == "/v1/status":
            try:
                return 200, {**self._serving_state(self.manager.status()),
                    'analytical_requests_paused': bool(self.query_gate and self.query_gate.blocked()),
                    'maintenance_only': self.maintenance_only}
            except ServingStateError:
                return 503, self._error(
                    "serving_unavailable", "private serving generation is unavailable"
                )
        if method == "GET" and route == "/v1/capabilities":
            return 200, self.adapter.capabilities()
        if method == "POST" and route == "/v1/query":
            try:
                request = json.loads(body.decode("utf-8"))
                if not isinstance(request, Mapping):
                    raise ValueError("request body must be a JSON object")
                request_key = self._request_key(request)
                with self._inflight_lock:
                    flight = self._inflight.get(request_key)
                    owner = flight is None
                    if owner:
                        flight = {"event": threading.Event(), "response": None}
                        self._inflight[request_key] = flight
                if not owner:
                    if not flight["event"].wait(self.shared_wait_seconds):
                        return 504, self._error(
                            "query_deadline", "shared analytical request exceeded its deadline"
                        )
                    response = flight.get("response")
                    if response is None:
                        return 503, self._error(
                            "shared_request_failed", "shared analytical request did not complete"
                        )
                    return copy.deepcopy(response)
                # Short bursts are normal when a user switches views or
                # applies filters. Queue them briefly instead of rejecting the
                # third request immediately while two analytical slots are in
                # use. The bounded wait still protects the serving VM from an
                # unbounded request backlog.
                if not self.query_slots.acquire(timeout=self.query_slot_wait_seconds):
                    response = (503, self._error(
                        "serving_busy",
                        "private analytical query capacity is currently full",
                    ))
                    flight["response"] = response
                    flight["event"].set()
                    with self._inflight_lock:
                        self._inflight.pop(request_key, None)
                    return response
                try:
                    try:
                        response = (200, self.adapter.execute(request))
                    except Exception as error:
                        response = self._query_failure(error)
                    flight["response"] = copy.deepcopy(response)
                    return response
                finally:
                    self.query_slots.release()
                    flight["event"].set()
                    with self._inflight_lock:
                        self._inflight.pop(request_key, None)
            except UnicodeDecodeError:
                return 400, self._error("invalid_json", "request body must be UTF-8")
            except json.JSONDecodeError:
                return 400, self._error("invalid_json", "request body must be valid JSON")
            except ValueError as exc:
                return 400, self._error("invalid_request", str(exc))
            except UnsupportedRouteError as exc:
                return 501, self._error("phase4_pending", str(exc))
            except QueryDeadlineExceeded as exc:
                return 504, self._error("query_deadline", str(exc))
            except ServingStateError:
                return 503, self._error(
                    "serving_unavailable", "private serving generation is unavailable"
                )
            except Exception as exc:  # pragma: no cover - last-resort boundary
                return 500, self._error("internal_error", type(exc).__name__)
        if route in {"/healthz", "/readyz", "/v1/status", "/v1/capabilities", "/v1/query"}:
            return 405, self._error("method_not_allowed", "method is not allowed for this endpoint")
        return 404, self._error("not_found", "endpoint does not exist")

    def _query_failure(self, error):
        if isinstance(error, ValueError):
            return 400, self._error('invalid_request', str(error))
        if isinstance(error, UnsupportedRouteError):
            return 501, self._error('phase4_pending', str(error))
        if isinstance(error, QueryDeadlineExceeded):
            return 504, self._error('query_deadline', str(error))
        if isinstance(error, ServingStateError):
            return 503, self._error('serving_unavailable', 'private serving generation is unavailable')
        return 500, self._error('internal_error', type(error).__name__)


class Phase3HTTPHandler(BaseHTTPRequestHandler):
    server_version = "ArkNovaPhase3/1"

    @property
    def app(self) -> Phase3Application:
        return self.server.phase3_app  # type: ignore[attr-defined]

    def _send(self, status: int, payload: Mapping[str, Any]) -> None:
        encoded = json.dumps(
            payload,
            separators=(",", ":"),
            default=_json_default,
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("X-Content-Type-Options", "nosniff")
        if payload.get('error') == 'refresh_in_progress':
            self.send_header('Retry-After', '30')
        self.end_headers()
        self.wfile.write(encoded)

    def _dispatch(self, include_body: bool) -> None:
        body = b""
        if include_body:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._send(400, {"status": "error", "error": "invalid_length"})
                return
            if length < 0 or length > MAX_REQUEST_BYTES:
                self._send(413, {"status": "error", "error": "request_too_large"})
                return
            try:
                body = self.rfile.read(length)
            except TimeoutError:
                self._send(408, {'status': 'error', 'error': 'request_timeout'})
                return
            if len(body) != length:
                self._send(400, {'status': 'error', 'error': 'incomplete_body'})
                return
        status, payload = self.app.dispatch(self.command, self.path, body)
        self._send(status, payload)

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch(False)

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch(True)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Allow", "GET, POST, OPTIONS")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.end_headers()

    def log_message(self, _format: str, *args: Any) -> None:
        # Avoid BaseHTTPRequestHandler logging request bodies or query strings.
        return


def create_application(
    generations_dir: str | Path,
    pointer_path: str | Path,
    cache_path: str | Path,
    audit_path: str | Path,
    max_concurrent_queries: int = 2,
    query_slot_wait_seconds: float | None = None,
    query_gate: RefreshQueryGate | None = None,
) -> Phase3Application:
    audit = Phase3AuditLog(audit_path)
    manager = GenerationManager(
        generations_dir,
        pointer_path=pointer_path,
        audit_log=audit,
    )
    adapter = create_private_adapter(
        manager,
        persistent_cache_path=cache_path,
        audit_log=audit,
    )
    return Phase3Application(
        manager, adapter, max_concurrent_queries, query_slot_wait_seconds, query_gate
    )


def main(argv: Sequence[str] | None = None) -> int:
    root = Path(__file__).resolve().parent
    private = root / "phase3_private_serving"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--generations-dir",
        type=Path,
        default=Path(os.environ.get(
            "PHASE3_GENERATIONS_DIR",
            root / "phase2_private_data" / "generations",
        )),
    )
    parser.add_argument("--pointer", type=Path, default=private / "current.json")
    parser.add_argument("--cache", type=Path, default=private / "response-cache.sqlite3")
    parser.add_argument("--audit", type=Path, default=private / "audit.jsonl")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument(
        "--max-concurrent-queries",
        type=int,
        default=int(os.environ.get("PHASE3_MAX_CONCURRENT_QUERIES", "2")),
    )
    args = parser.parse_args(argv)
    gate_path = os.environ.get('PHASE5_QUERY_PAUSE_LOCK')
    gate = RefreshQueryGate(gate_path) if gate_path else None
    app = create_application(
        args.generations_dir,
        args.pointer,
        args.cache,
        args.audit,
        args.max_concurrent_queries,
        query_gate=gate,
    )
    if os.environ.get("PHASE3_WARM_INTERACTIVE", "1") != "0":
        try:
            if gate:
                with gate.query():
                    warm_interactive_generation(app.manager)
            else:
                warm_interactive_generation(app.manager)
        except AnalyticalRequestsPaused:
            pass
    server = BoundedHTTPServer((args.host, args.port), Phase3HTTPHandler,
        max_connections=int(os.environ.get('PHASE3_MAX_HTTP_CONNECTIONS', '16')),
        read_timeout=float(os.environ.get('PHASE3_HTTP_READ_TIMEOUT', '15')))
    server.phase3_app = app  # type: ignore[attr-defined]
    if gate:
        def refresh_mode_watch():
            while True:
                time.sleep(0.5)
                if gate.fully_paused() != app.maintenance_only:
                    # A fully exclusive barrier proves there is no admitted
                    # query to interrupt. Restart releases DuckDB/Python arenas;
                    # a boolean guard or connection.close alone cannot do so.
                    # Restart=always starts a lightweight paused process, and
                    # restarts/warmups normally after the owner releases locks.
                    os._exit(0)
        threading.Thread(target=refresh_mode_watch, daemon=True).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
