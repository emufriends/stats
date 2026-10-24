"""VM-side worker for the private DuckDB refresh boundary.

The public Cloud Function only queues a sanitized request and starts the fixed
VM. This worker owns the long-running work: refresh the small moving inputs,
run the bounded source sync, build an inactive immutable candidate, coordinate
public artifact/local-pointer publication, publish status, and release the
lock. Small control reads use authenticated HTTPS with the VM identity and a
cached metadata-server token. Bulk source transfers use ``gcloud storage``;
artifact publication uses a persistent authenticated Storage SDK session;
idle polling never launches a CLI process or needs another runtime service.
"""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase5_operational_controls import prune_local_releases, prune_source_exports, refresh_inputs
from phase5_source_sync import file_record, validate_files
from phase5_refresh_metrics import RefreshTimings
from phase5_query_pause import RefreshQueryGate


APP_ROOT = Path(__file__).resolve().parent
# Persistent data deliberately lives outside the immutable deployment bundle.
# ARK_ROOT therefore names the data root only; executable modules must always
# be resolved relative to this worker's installed release.
ROOT = Path(os.environ.get("ARK_ROOT", "/home/ascri"))
PRIVATE = ROOT / "phase2_private_data"
SOURCE_DIR = PRIVATE / "source"
MOVING_DIR = PRIVATE / "moving_sources"
WORK_DIR = PRIVATE / "worker"
REQUEST_BUCKET = os.environ.get("REFRESH_BUCKET", "ark-nova-stats-dashboard-cache")
REQUEST_PREFIX = os.environ.get("REFRESH_PREFIX", "card-stats")
REQUEST_BLOB = os.environ.get("REFRESH_REQUEST_BLOB", f"{REQUEST_PREFIX}/refresh/private-request.json")
STATUS_BLOB = os.environ.get("REFRESH_STATUS_BLOB", f"{REQUEST_PREFIX}/refresh/status.json")
LOCK_BLOB = os.environ.get("REFRESH_LOCK_BLOB", f"{REQUEST_PREFIX}/refresh/lock.json")
SOURCE_BUCKET = os.environ.get("SOURCE_BUCKET", "ark-nova-stats-phase2-import-413312054512")
SOURCE_PREFIX = os.environ.get("SOURCE_PREFIX", "phase5/source-sync")
DIAGNOSTIC_PREFIX = os.environ.get("DIAGNOSTIC_PREFIX", "phase5/refresh-diagnostics")
# This worker downloads committed exports; it never submits BigQuery queries.
# Query byte limits belong to the controlled source-export service, not to a
# VM environment setting that cannot affect already completed export jobs.
THREADS = int(os.environ.get("REFRESH_THREADS", "2"))
MEMORY_LIMIT = os.environ.get("REFRESH_MEMORY_LIMIT", "2000MB")
SOURCE_MEMORY_LIMIT = os.environ.get('REFRESH_SOURCE_MEMORY_LIMIT', MEMORY_LIMIT)
KEEP_ALIVE = os.environ.get("DUCKDB_WORKER_KEEP_ALIVE", "false").lower() in {"1", "true", "yes", "on"}
# Smaller shared-core VMs retain the same statistical work but need more CPU
# time. The maintenance lock includes a separate one-hour recovery margin.
REFRESH_WINDOW_SECONDS = 6 * 60 * 60
VM_ZONE = os.environ.get("VM_ZONE", "europe-west1-c")
VM_NAME = os.environ.get("VM_NAME", "ark-nova-duckdb-test")


class ControlReadError(RuntimeError):
    """A control object could not be read; this is never evidence of absence."""


class ControlReader:
    """Bounded VM-only storage reads, with credentials kept solely in memory."""

    def __init__(self) -> None:
        self.token = ""
        self.expires_at = 0.0

    def access_token(self) -> str:
        if self.token and time.monotonic() < self.expires_at:
            return self.token
        request = urllib.request.Request(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"},
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                value = json.loads(response.read(65537))
            token = value["access_token"]
            lifetime = float(value["expires_in"])
            if not isinstance(token, str) or not token or lifetime <= 0:
                raise ValueError("invalid token response")
        except Exception:
            # Neither tokens nor HTTP bodies belong in logs/status exceptions.
            raise ControlReadError("VM identity token is unavailable") from None
        self.token = token
        self.expires_at = time.monotonic() + max(0, lifetime - 60)
        return token

    def read(self, bucket: str, blob: str) -> dict[str, Any] | None:
        url = ("https://storage.googleapis.com/storage/v1/b/"
               + urllib.parse.quote(bucket, safe="") + "/o/"
               + urllib.parse.quote(blob.lstrip("/"), safe="") + "?alt=media")
        for attempt in range(2):
            request = urllib.request.Request(url, headers={
                "Authorization": "Bearer " + self.access_token(),
                "Cache-Control": "no-cache",
            })
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    body = response.read(4 * 1024 * 1024 + 1)
                if len(body) > 4 * 1024 * 1024:
                    raise ControlReadError("Storage control object exceeds its size limit")
                value = json.loads(body)
                if not isinstance(value, dict):
                    raise ControlReadError("Storage control object is not a JSON object")
                return value
            except urllib.error.HTTPError as error:
                error.close()
                if error.code == 404:
                    return None
                if error.code == 401 and attempt == 0:
                    self.token = ""
                    self.expires_at = 0.0
                    continue
                raise ControlReadError(f"Storage control read failed (HTTP {error.code})") from None
            except ControlReadError:
                raise
            except Exception:
                raise ControlReadError("Storage control read failed or returned invalid JSON") from None
        raise ControlReadError("Storage control authentication failed")


CONTROL_READER = ControlReader()

ARENA_URL = os.environ.get("ARENA_URL", "https://raw.githubusercontent.com/emufriends/stats/main/docs/arena").rstrip("/")
RECORD_URLS = {
    "records-fastest.csv": os.environ.get(
        "RECORDS_FASTEST_URL",
        "https://docs.google.com/spreadsheets/d/1RSOjQdZcGmOY7PBsDY7erGz--dtPJLc3ydNArr9bV48/export?format=csv&gid=1836311698",
    ),
    "records-biggest.csv": os.environ.get(
        "RECORDS_BIGGEST_URL",
        "https://docs.google.com/spreadsheets/d/1SfWmRUo3c2jHbezJDVwXxi3zqEm5RdiZxp4hbHfEl0Q/export?format=csv",
    ),
    "records-elo.csv": os.environ.get(
        "RECORDS_ELO_URL",
        "https://docs.google.com/spreadsheets/d/1NG3FPP70riMzhHPJ6Suz30bhJxUocFd_rKDKxn0kZbM/export?format=csv&sheet=Masters",
    ),
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def gcloud(*args: str, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess[str]:
    command = ["gcloud", *args]
    return subprocess.run(command, check=check, text=True, capture_output=capture, timeout=120)


def gs_uri(blob: str) -> str:
    return f"gs://{REQUEST_BUCKET}/{blob.lstrip('/')}"


def read_json(blob: str) -> dict[str, Any] | None:
    return CONTROL_READER.read(REQUEST_BUCKET, blob)


def read_json_from(bucket: str, blob: str) -> dict[str, Any] | None:
    return CONTROL_READER.read(bucket, blob)


def read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def write_json(blob: str, payload: dict[str, Any]) -> None:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", dir=WORK_DIR, delete=False) as handle:
        json.dump(payload, handle, separators=(",", ":"))
        path = handle.name
    try:
        gcloud("storage", "cp", "--quiet", path, gs_uri(blob))
    finally:
        Path(path).unlink(missing_ok=True)


def write_diagnostic(run_id: str, error: BaseException, *, stdout: str = "", stderr: str = "") -> None:
    """Keep detailed failures on the operator-only VM; publish sanitized status only.

    The snapshot bucket permits anonymous reads, including diagnostic prefixes.
    The source bucket is read-only for this identity. Neither is an appropriate
    fallback destination for SQL, stack traces or private workflow output.
    """
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    path = WORK_DIR / f"{run_id}.failure.txt"
    details = [
        f"run_id={run_id}",
        f"exception={type(error).__name__}: {error}",
        "traceback:",
        traceback.format_exc(),
    ]
    if stdout:
        details.extend(["stdout:", stdout[-20000:]])
    if stderr:
        details.extend(["stderr:", stderr[-20000:]])
    path.write_text("\n".join(details) + "\n", encoding="utf-8")
    marker = WORK_DIR / f"{run_id}.diagnostic-written"
    marker.write_text("1\n", encoding="utf-8")


def status_payload(run_id: str, state: str, percent: int, phase: str, previous: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    previous = previous or {}
    payload = {
        "state": state,
        "run_id": run_id,
        "progress_percent": max(0, min(100, int(percent))),
        "phase": phase,
        "started_at": extra.pop("started_at", previous.get("started_at")),
        "updated_at": now(),
        "last_completed_at": extra.pop("last_completed_at", previous.get("last_completed_at")),
        "completed_data_version": extra.pop("completed_data_version", previous.get("completed_data_version")),
    }
    return payload


def publish(run_id: str, state: str, percent: int, phase: str, previous: dict[str, Any], **extra: Any) -> dict[str, Any]:
    payload = status_payload(run_id, state, percent, phase, previous, **extra)
    write_json(STATUS_BLOB, payload)
    return payload


def find_previous_source() -> Path:
    latest = SOURCE_DIR / "latest"
    if latest.is_dir() and (latest / "manifest.json").is_file():
        return latest.resolve()
    candidates = sorted(
        (path for path in SOURCE_DIR.iterdir() if path.is_dir() and (path / "manifest.json").is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise RuntimeError("no committed source generation exists")
    return candidates[0]


def download(url: str, path: Path) -> bool:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "ark-nova-private-refresh"})
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
        path.write_bytes(data)
        return bool(data)
    except Exception:
        return False


def _arena_roster_required(end_value: Any, *, current_time: datetime | None = None) -> bool:
    """Require a roster only after its Arena season has ended.

    Arena settings may publish an ongoing season before its Elite League sheet
    exists.  That season is still needed by Players filters, but it must not
    block the daily refresh or displace the newest completed Arena roster.
    Missing/invalid end timestamps fail closed and continue to require a roster.
    """
    text = str(end_value or "").strip()
    if not text:
        return True
    try:
        end = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return True
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    reference = current_time or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return end <= reference


def refresh_moving_sources() -> dict[str, Any]:
    """Refresh public CSV inputs, retaining each last-known-good file on outage."""
    MOVING_DIR.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"refreshed_at": now(), "sources": {}}
    with tempfile.TemporaryDirectory(dir=PRIVATE) as temporary:
        candidate = Path(temporary) / "moving_sources"
        candidate.mkdir()
        for path in MOVING_DIR.glob("*.csv"):
            shutil.copy2(path, candidate / path.name)

        settings = candidate / "arena_settings.csv"
        settings_fresh = download(f"{ARENA_URL}/arena_settings.csv", settings)
        report["sources"]["arena_settings.csv"] = {
            "state": "fresh" if settings_fresh else "last_known_good"
        }
        season_roster_required: dict[str, bool] = {}
        if settings.is_file():
            with settings.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    season = str(row.get("Season") or "").strip().lower()
                    if season:
                        season_roster_required[season] = _arena_roster_required(
                            row.get("End (UTC)")
                        )
        for season, roster_required in season_roster_required.items():
            name = f"{season}.csv"
            had_last_known_good = (candidate / name).is_file()
            fresh = download(f"{ARENA_URL}/{name}", candidate / name)
            if fresh:
                state = "fresh"
            elif had_last_known_good and (candidate / name).is_file():
                state = "last_known_good"
            elif roster_required:
                state = "missing"
            else:
                state = "unavailable"
            report["sources"][name] = {
                "state": state
            }

        for name, url in RECORD_URLS.items():
            fresh = download(url, candidate / name)
            report["sources"][name] = {
                "state": "fresh" if fresh else "last_known_good"
            }

        # Tournament metadata participates in the deterministic refresh
        # identity, so fetch and validate it before deciding that a generation
        # is unchanged. Fetching it later inside the builder would let a sheet
        # change hide behind an otherwise identical fingerprint.
        tournament_cache = candidate / "tournament-metadata.json"
        try:
            sys.path.insert(0, str(APP_ROOT))
            from phase4_metadata import fetch_tournament_metadata
            tournament_rows, tournament_info = fetch_tournament_metadata()
            tournament_cache.write_text(json.dumps({
                "rows": tournament_rows,
                "source": {**tournament_info, "state": "fresh"},
            }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            report["sources"]["tournament-metadata.json"] = {"state": "fresh"}
        except Exception:
            previous = MOVING_DIR / "tournament-metadata.json"
            if previous.is_file():
                shutil.copy2(previous, tournament_cache)
                report["sources"]["tournament-metadata.json"] = {
                    "state": "last_known_good", "reason": "live tournament fetch failed"
                }
            else:
                report["sources"]["tournament-metadata.json"] = {
                    "state": "active_generation_fallback",
                    "reason": "live tournament fetch failed and no moving-source cache exists",
                }

        # Validate downloaded Records inputs before replacing the committed
        # moving-source set.  A transient or malformed spreadsheet (for
        # example a blank country cell in the Elo sheet) falls back to the
        # previous valid file and must not block the analytical refresh.
        try:
            sys.path.insert(0, str(APP_ROOT))
            from phase4_records_source import read_biggest, read_elo, read_fastest
            readers = {
                "records-fastest.csv": read_fastest,
                "records-biggest.csv": read_biggest,
                "records-elo.csv": read_elo,
            }
            for name, reader in readers.items():
                try:
                    reader(candidate / name)
                except Exception:
                    previous = MOVING_DIR / name
                    if not previous.is_file():
                        raise
                    shutil.copy2(previous, candidate / name)
                    report["sources"][name] = {
                        "state": "last_known_good", "reason": "downloaded CSV failed validation"
                    }
        except ImportError:
            # The workflow performs the authoritative validation as a second
            # line of defence on installations without the helper module.
            pass

        required = {"arena_settings.csv", *RECORD_URLS}
        if not required.issubset({path.name for path in candidate.glob("*.csv")}):
            raise RuntimeError("moving-source refresh has no complete last-known-good set")
        missing_rosters = [
            f"{season}.csv"
            for season, roster_required in season_roster_required.items()
            if roster_required and not (candidate / f"{season}.csv").is_file()
        ]
        if missing_rosters:
            raise RuntimeError("moving-source refresh is missing Arena rosters: " + ", ".join(missing_rosters))
        (candidate / "source-status.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        backup = MOVING_DIR.with_name("moving_sources.previous")
        shutil.rmtree(backup, ignore_errors=True)
        if MOVING_DIR.exists():
            MOVING_DIR.rename(backup)
        candidate.rename(MOVING_DIR)
        shutil.rmtree(backup, ignore_errors=True)
    return report


def update_latest_source(source_root: Path) -> None:
    latest = SOURCE_DIR / "latest"
    temporary = SOURCE_DIR / ".latest.tmp"
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(source_root, target_is_directory=True)
    temporary.replace(latest)


def commit_source_inventory(source_root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Write the checksum inventory last, making a transferred source reusable."""
    parquet = sorted(source_root.glob("*.parquet"))
    local_manifest = {
        **manifest,
        "mode": "source_sync",
        "files": [file_record(path) for path in parquet],
        "validated_at": now(),
    }
    validate_files(source_root, local_manifest)
    temporary_manifest = source_root / "manifest.json.tmp"
    temporary_manifest.write_text(
        json.dumps(local_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary_manifest, source_root / "manifest.json")
    return local_manifest


def materialize_latest_export(previous_source: Path) -> Path:
    """Download a new function-owned export, or retain the last good source."""
    manifest = read_json_from(SOURCE_BUCKET, f"{SOURCE_PREFIX}/latest-manifest.json")
    if not manifest or manifest.get("status") != "ok":
        return previous_source
    previous_manifest = json.loads(
        (previous_source / "manifest.json").read_text(encoding="utf-8")
    )
    if manifest.get("source_fingerprints") == previous_manifest.get("source_fingerprints"):
        if previous_manifest.get("mode") == "source_sync":
            validate_files(previous_source, previous_manifest)
        else:
            commit_source_inventory(previous_source, {**previous_manifest, **manifest})
        return previous_source

    generation = str(manifest.get("generation") or "")
    exports = manifest.get("export") or {}
    full_uri = str(exports.get("full_sample_uri") or "")
    logs_uri = str(exports.get("logs_uri") or "")
    if not generation or not full_uri or not logs_uri:
        raise RuntimeError("source export manifest is incomplete")
    candidate = SOURCE_DIR / f".source-{generation}"
    committed = candidate / "manifest.json"
    if committed.is_file():
        local_manifest = json.loads(committed.read_text(encoding="utf-8"))
        if local_manifest.get("source_fingerprints") == manifest.get("source_fingerprints"):
            validate_files(candidate, local_manifest)
            return candidate
    if candidate.exists():
        shutil.rmtree(candidate)
    candidate.mkdir(parents=True)
    try:
        # Equal families reuse checksum-validated immutable local files. A
        # changed Full Sample must not redownload an unchanged Logs export.
        validate_files(previous_source, previous_manifest)
        for family, uri in (('full_sample',full_uri),('logs',logs_uri)):
            unchanged = (manifest.get('source_fingerprints',{}).get(family) is not None
                         and manifest['source_fingerprints'][family]
                         == previous_manifest.get('source_fingerprints',{}).get(family))
            if unchanged:
                files = sorted(previous_source.glob(f'{family}-*.parquet'))
                if not files:
                    raise RuntimeError('Reusable source family is missing')
                for path in files:
                    try:
                        os.link(path, candidate / path.name)
                    except OSError:
                        shutil.copy2(path, candidate / path.name)
            else:
                gcloud("storage", "cp", "--quiet", uri, str(candidate))
        commit_source_inventory(candidate, manifest)
    except Exception:
        shutil.rmtree(candidate, ignore_errors=True)
        raise
    return candidate


def save_accounting(run_id: str, result: dict[str, Any]) -> None:
    """Private telemetry is diagnostic; it cannot invalidate a published release."""
    try:
        (WORK_DIR / f'{run_id}.accounting.json').write_text(
            json.dumps(result, indent=2) + '\n', encoding='utf-8')
    except OSError:
        print('Refresh accounting could not be persisted', file=sys.stderr)


def kill_workflow(process) -> None:
    """Stop the Linux workflow session, including fresh offline stage children."""
    if os.name != 'nt':
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        # The deployed worker is Linux. Preserve the existing desktop fixture
        # behavior without inventing a platform-specific production scheduler.
        process.kill()


def run_refresh(run_id: str, previous_status: dict[str, Any]) -> dict[str, Any]:
    # Keep measurements private and scoped to this run, including moving-source,
    # import, isolated-stage and publication subprocesses. No idle-run sampling.
    from phase5_refresh_metrics import measure_resources, private_timeline
    with private_timeline(WORK_DIR / f"{run_id}.memory-timeline.jsonl"):
        with measure_resources([], 'refresh_worker'):
            return _run_refresh_with_pause(run_id, previous_status)


def _run_refresh_with_pause(run_id: str, previous_status: dict[str, Any]) -> dict[str, Any]:
    if os.environ.get('REFRESH_PAUSE_ANALYTICS', 'false').lower() not in {'1', 'true', 'yes', 'on'}:
        return _run_refresh(run_id, previous_status)
    gate_path = os.environ.get('PHASE5_QUERY_PAUSE_LOCK')
    if not gate_path:
        raise RuntimeError('refresh pause enabled without the shared query barrier')
    gate = RefreshQueryGate(gate_path)
    with gate.pause():
        wait_for_lightweight_api()
        return _run_refresh(run_id, previous_status)


def wait_for_lightweight_api(timeout=45):
    """Require process-memory release before starting any refresh stage."""
    deadline = time.monotonic() + timeout
    url = os.environ.get('REFRESH_PAUSE_STATUS_URL', 'http://127.0.0.1:8787/v1/status')
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                status = json.load(response)
            if status.get('maintenance_only') is True and status.get('analytical_requests_paused') is True:
                return
        except (OSError, ValueError):
            pass
        time.sleep(0.5)
    raise TimeoutError('API did not enter lightweight refresh mode')


def _run_refresh(run_id: str, previous_status: dict[str, Any]) -> dict[str, Any]:
    deadline = time.time() + REFRESH_WINDOW_SECONDS
    timing = RefreshTimings()
    worker_started_at = now()
    started_at = (
        previous_status.get("started_at")
        if previous_status.get("state") == "running"
        else now()
    )
    publish(run_id, "running", 5, "Refreshing Arena and Records sources", previous_status, started_at=started_at)
    with timing.stage('moving_sources'):
        refresh_moving_sources()

    publish(run_id, "running", 15, "Checking source metadata", previous_status, started_at=started_at)
    previous_source = find_previous_source()
    # Failed builds must not accumulate a fresh full export indefinitely. This
    # cleanup protects all retained release sources and the committed source.
    try:
        prune_source_exports(ROOT, extra_protected=[previous_source])
    except Exception as cleanup_error:
        write_diagnostic(run_id, cleanup_error)
    with timing.stage('source_download'):
        source_root = materialize_latest_export(previous_source)
    publish(run_id, "running", 35, "Building the private DuckDB generation", previous_status, started_at=started_at)
    input_contract = refresh_inputs(APP_ROOT, source_root, MOVING_DIR)
    generation = f"phase5-refresh-{input_contract['fingerprint'][:24]}"
    workflow = [
        sys.executable, str(APP_ROOT / "phase5_refresh_workflow.py"), str(source_root), generation,
        "--root", str(ROOT), "--builder", str(APP_ROOT / "phase2_local_vertical_slice.py"),
        "--arena-settings", str(MOVING_DIR / "arena_settings.csv"),
        "--moving-source-dir", str(MOVING_DIR), "--threads", str(THREADS),
        "--memory-limit", MEMORY_LIMIT, "--report", str(WORK_DIR / f"{run_id}.refresh.json"),
        '--source-memory-limit', SOURCE_MEMORY_LIMIT,
        "--progress-file", str(WORK_DIR / f"{run_id}.progress.json"),
        "--defer-activation",
    ]
    # Incremental reconciliation normally avoids rebuilding unchanged imported
    # relations. Operators may disable it for a measured recovery build when a
    # sparse/fragmented active database is larger than the available staging
    # headroom; the workflow then rematerializes from the already-local export
    # without querying BigQuery.
    if os.environ.get("PHASE5_INCREMENTAL_SOURCE", "true").strip().lower() not in {
        "0", "false", "no", "off",
    }:
        workflow.insert(-1, "--incremental-source")
    if os.environ.get('REFRESH_ISOLATE_STAGES', 'false').strip().lower() in {'1', 'true', 'yes', 'on'}:
        workflow.insert(-1, '--isolate-stages')
    progress_path = WORK_DIR / f"{run_id}.progress.json"
    progress_path.unlink(missing_ok=True)
    stdout_path = WORK_DIR / f"{run_id}.workflow.stdout.log"
    stderr_path = WORK_DIR / f"{run_id}.workflow.stderr.log"
    stdout_handle = stdout_path.open("w", encoding="utf-8")
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    workflow_started, workflow_started_at = time.perf_counter(), now()
    # Measurement only: every stage process appends a memory sample about every
    # 30 s to this private file (see phase5_refresh_metrics.ResourceSampler).
    child_environment = {
        **os.environ,
        'ARK_RESOURCE_TIMELINE_FILE': str(WORK_DIR / f"{run_id}.memory-timeline.jsonl"),
    }
    process = subprocess.Popen(
        workflow, cwd=APP_ROOT, stdout=stdout_handle, stderr=stderr_handle, text=True,
        env=child_environment,
        # Stage subprocesses inherit this session. A deadline must stop the
        # builder too, not leave an orphan writing to a failed private candidate.
        start_new_session=(os.name != 'nt'),
    )
    last_percent = 35
    while process.poll() is None:
        if time.time() >= deadline:
            kill_workflow(process)
            process.wait()
            stdout_handle.close()
            stderr_handle.close()
            raise TimeoutError("private refresh workflow exceeded six hours")
        progress = read_json_file(progress_path)
        if progress:
            percent = int(progress.get("progress_percent") or last_percent)
            phase = str(progress.get("phase") or "Building the private DuckDB generation")
            if percent > last_percent:
                publish(run_id, "running", percent, phase, previous_status, started_at=started_at)
                last_percent = percent
        time.sleep(5)
    stdout_handle.close()
    stderr_handle.close()
    timing.record('local_workflow', workflow_started, workflow_started_at,
                  state='succeeded' if process.returncode == 0 else 'failed')
    stdout = stdout_path.read_text(encoding="utf-8", errors="replace")[-20000:]
    stderr = stderr_path.read_text(encoding="utf-8", errors="replace")[-20000:]
    workflow_report = WORK_DIR / f"{run_id}.refresh.json"
    if workflow_report.exists():
        stderr += "\nworkflow report:\n" + workflow_report.read_text(
            encoding="utf-8", errors="replace"
        )[-20000:]
    stdout_path.unlink(missing_ok=True)
    stderr_path.unlink(missing_ok=True)
    if process.returncode:
        error = subprocess.CalledProcessError(process.returncode, workflow)
        write_diagnostic(run_id, error, stdout=stdout, stderr=stderr)
        raise error
    progress_path.unlink(missing_ok=True)
    workflow_payload = read_json_file(workflow_report) or {}
    if workflow_payload.get("status") == "unchanged":
        update_latest_source(source_root)
        completed = publish(
            run_id, "succeeded", 100, "No source changes; current release retained",
            previous_status, started_at=started_at,
            last_completed_at=previous_status.get("last_completed_at"),
            completed_data_version=workflow_payload.get("data_version"),
        )
        result = {
            "generation": workflow_payload.get("generation"),
            "data_version": workflow_payload.get("data_version"),
            "source_generation": source_root.name,
            "unchanged": True,
            "status_updated_at": completed.get("updated_at"),
            "queued_at": started_at, "worker_started_at": worker_started_at,
            "completed_at": now(), "timings": timing.stages,
            "workflow_timings": workflow_payload.get('timings', []),
        }
        save_accounting(run_id, result)
        return result
    if workflow_payload.get("status") != "candidate_ready" or workflow_payload.get("activated") is not False:
        raise RuntimeError("refresh workflow did not produce an inactive validated candidate")
    generation = str(workflow_payload.get("generation") or generation)
    manifest = json.loads((PRIVATE / "generations" / f"{generation}.manifest.json").read_text(encoding="utf-8"))
    # Keep the source pointer in the same compensation boundary as public
    # publication. If publication fails, restore the prior source before the
    # failed run is reported.
    update_latest_source(source_root)
    publish(run_id, "running", 97, "Publishing the validated release", previous_status, started_at=started_at)
    remaining_seconds = int(deadline - time.time())
    if remaining_seconds <= 0:
        raise TimeoutError("private refresh exceeded six hours before publication")
    try:
        publication_started, publication_started_at = time.perf_counter(), now()
        publication = subprocess.run(
            [
                sys.executable, str(APP_ROOT / "phase5_publish_release.py"), generation,
                "--root", str(ROOT), "--bucket", REQUEST_BUCKET,
                "--prefix", REQUEST_PREFIX, "--run-id", run_id,
                *publication_code_arguments(),
            ],
            cwd=APP_ROOT, text=True, capture_output=True,
            timeout=remaining_seconds,
        )
        timing.record('publication', publication_started, publication_started_at,
                      state='succeeded' if publication.returncode == 0 else 'failed')
    except subprocess.TimeoutExpired:
        subprocess.run(
            [
                sys.executable, str(APP_ROOT / "phase5_publish_release.py"), generation,
                "--root", str(ROOT), "--bucket", REQUEST_BUCKET, "--recover",
            ],
            cwd=APP_ROOT, text=True, capture_output=True, timeout=900,
        )
        update_latest_source(previous_source)
        raise TimeoutError("coordinated publication exceeded the six-hour refresh window")
    except Exception:
        update_latest_source(previous_source)
        raise
    if publication.returncode:
        update_latest_source(previous_source)
        error = subprocess.CalledProcessError(publication.returncode, publication.args)
        write_diagnostic(
            run_id, error, stdout=publication.stdout or "", stderr=publication.stderr or ""
        )
        raise error
    # Cleanup is deliberately after successful transactional publication.  It
    # can never make a valid release fail and always protects active/rollback
    # generations, so a cleanup error is diagnostic rather than destructive.
    try:
        prune_local_releases(ROOT)
    except Exception as cleanup_error:  # pragma: no cover - operational boundary
        write_diagnostic(run_id, cleanup_error)
    # The publisher writes the succeeded/100% status object inside the same
    # rollback journal as the pack and serving pointers. Do not rewrite it here.
    result = {"generation": generation, "data_version": manifest.get("data_version"),
              "source_generation": source_root.name, "queued_at": started_at,
              "worker_started_at": worker_started_at, "completed_at": now(),
              "timings": timing.stages,
              "workflow_timings": workflow_payload.get('timings', [])}
    # Private accounting distinguishes queue delay from actual worker runtime.
    # The public status contains no SQL, request details or resource internals.
    try:
        result['publication_timings'] = json.loads(publication.stdout).get('timings', [])
    except (ValueError, AttributeError):
        result['publication_timings'] = []
    save_accounting(run_id, result)
    return result


def publication_code_arguments():
    """Record the exact code pair after a compatible immutable code update.

The publisher CLI independently validates the candidate producer inventory and
both installed bundles. Never bypass code/data pairing merely because source
rows are unchanged. Desktop fixture paths are not deployment versions.
"""
    current = APP_ROOT.name
    if not re.fullmatch(r'deploy-[0-9a-f]{20}', current):
        return []
    pointer = read_json_file(ROOT / 'phase3_private_serving/current.json') or {}
    manifest = read_json_file(PRIVATE / 'generations' / (str(pointer.get('generation')) + '.manifest.json')) or {}
    previous = (manifest.get('release') or {}).get('deployment_version')
    if not re.fullmatch(r'deploy-[0-9a-f]{20}', str(previous or '')):
        raise RuntimeError('active release has no exact code rollback pair')
    return ['--deployment-version',current,'--previous-deployment-version',previous]


def release_lock(run_id: str) -> None:
    lock = read_json(LOCK_BLOB)
    if lock and lock.get("run_id") == run_id:
        gcloud("storage", "rm", "--quiet", gs_uri(LOCK_BLOB), check=False)


def stop_vm() -> None:
    # The dedicated VM identity intentionally has no Compute Admin role.  A
    # passwordless local shutdown stops the GCE instance without giving the
    # worker authority to control any other VM.
    subprocess.run(["sudo", "-n", "systemctl", "poweroff"], check=False, capture_output=True, text=True)


def main() -> int:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    # A hard VM/process kill can bypass Python finally blocks. Compensate any
    # journaled publication before accepting another refresh request.
    if (PRIVATE / "publication-transaction.json").is_file():
        # Recovery must use the same barrier as refresh: compensating a
        # publication can involve generation validation and warming.
        from contextlib import nullcontext
        recovery_gate = (RefreshQueryGate(os.environ['PHASE5_QUERY_PAUSE_LOCK']).pause()
            if os.environ.get('REFRESH_PAUSE_ANALYTICS', 'false').lower() in {'1','true','yes','on'}
            else nullcontext())
        with recovery_gate:
            if os.environ.get('REFRESH_PAUSE_ANALYTICS', 'false').lower() in {'1','true','yes','on'}:
                wait_for_lightweight_api()
            recovery = subprocess.run(
            [
                sys.executable, str(APP_ROOT / "phase5_publish_release.py"), "recovery",
                "--root", str(ROOT), "--bucket", REQUEST_BUCKET, "--recover",
            ],
            cwd=APP_ROOT, text=True, capture_output=True, timeout=900,
            )
        if recovery.returncode:
            raise RuntimeError("could not recover the interrupted release publication")
    deadline = time.time() + 180
    while KEEP_ALIVE or time.time() < deadline:
        try:
            request = read_json(REQUEST_BLOB)
            previous = {}
            if request and request.get("run_id"):
                previous = read_json(STATUS_BLOB) or {}
        except ControlReadError as error:
            # Transport/authentication errors must not kill idle scheduling,
            # acknowledge a request, release its lock, or overwrite its status.
            print(f"Refresh control polling delayed: {error}", file=sys.stderr, flush=True)
            time.sleep(15)
            continue
        if request and request.get("run_id"):
            run_id = str(request["run_id"])
            try:
                run_refresh(run_id, previous)
            except Exception as exc:
                if not (WORK_DIR / f"{run_id}.diagnostic-written").exists():
                    write_diagnostic(run_id, exc)
                publish(run_id, "failed", int(previous.get("progress_percent") or 0), "Refresh failed", previous)
            finally:
                (WORK_DIR / f"{run_id}.diagnostic-written").unlink(missing_ok=True)
                release_lock(run_id)
                gcloud("storage", "rm", "--quiet", gs_uri(REQUEST_BLOB), check=False)
                if not KEEP_ALIVE:
                    stop_vm()
            if not KEEP_ALIVE:
                return 0
            continue
        time.sleep(5)
    if not KEEP_ALIVE:
        stop_vm()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
