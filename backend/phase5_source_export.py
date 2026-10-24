"""Bounded maintenance export retries with strict, privately recorded consistency.

Importing this module performs no cloud operations. Every attempt is a complete
fresh export; mismatched attempts are never committed, relabelled or reused.
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone


class SourceChangedDuringExport(RuntimeError):
    pass


def metadata_differences(before, after, path=""):
    """Preserve exact values and types; array order is part of the contract."""
    if type(before) is not type(after):
        return [{"path": path, "before": before, "after": after}]
    if isinstance(before, dict):
        result = []
        for key in sorted(set(before) | set(after)):
            child = path + "/" + str(key).replace("~", "~0").replace("/", "~1")
            if key not in before or key not in after:
                result.append({"path": child, "before_present": key in before,
                               "after_present": key in after, "before": before.get(key),
                               "after": after.get(key)})
            else:
                result.extend(metadata_differences(before[key], after[key], child))
        return result
    if isinstance(before, list):
        if len(before) != len(after):
            return [{"path": path, "before": before, "after": after}]
        return [item for i, (a, b) in enumerate(zip(before, after))
                for item in metadata_differences(a, b, path + "/" + str(i))]
    return [] if before == after else [{"path": path, "before": before, "after": after}]


def _now():
    return datetime.now(timezone.utc).isoformat()


def prepare_source_export(*, source_sync, bucket, client, query_config, extract_config,
                          prefix, maintenance_budget, per_export_cap,
                          max_attempts=2, window_seconds=900, quiet_seconds=3,
                          retry_seconds=5, clock=time.monotonic, sleep=time.sleep,
                          now=_now, unique=lambda: uuid.uuid4().hex):
    """Commit only an exact stable before/after match, under bounded budgets.

    Diagnostics use the private source bucket, never the public snapshot bucket.
    Retries retain the unchanged production fingerprint format. Per-query limits
    stay <= 8 GiB; the sum of charged/reserved attempts stays within maintenance
    budget. At most two attempts and 900 seconds fit inside the existing function
    timeout. Real cloud calls happen only when this function is explicitly called.
    """
    if not 1 <= max_attempts <= 2 or not 0 < window_seconds <= 900:
        raise ValueError("source export retry/time bounds are invalid")
    if quiet_seconds < 0 or retry_seconds < 0:
        raise ValueError("source export wait bounds are invalid")
    if maintenance_budget <= 0 or not 0 < per_export_cap <= 8 * 1024 ** 3:
        raise ValueError("source export byte limits are invalid")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_/-]*", prefix) or ".." in prefix.split("/"):
        raise ValueError("invalid source export prefix")
    deadline = clock() + window_seconds
    operation = unique()
    charged_bytes = 0

    def remaining():
        seconds = deadline - clock()
        if seconds <= 0:
            raise TimeoutError("private source export deadline reached")
        return seconds

    def wait(seconds):
        if remaining() <= seconds:
            raise TimeoutError("private source export deadline prevents another wait")
        sleep(seconds)

    class BoundedMetadataClient:
        def get_table(self, *args, **kwargs):
            return client.get_table(*args, **kwargs, timeout=min(30, remaining()), retry=None)

        def get_routine(self, *args, **kwargs):
            return client.get_routine(*args, **kwargs, timeout=min(30, remaining()), retry=None)

        def query(self, *args, **kwargs):
            # Used only for the existing dry-run planner.
            return client.query(*args, **kwargs, timeout=min(30, remaining()), retry=None, job_retry=None)

    bounded_client = BoundedMetadataClient()
    previous_blob = bucket.blob(prefix + "/latest-manifest.json")
    previous = None
    previous_generation = 0
    if previous_blob.exists(timeout=min(30, remaining()), retry=None):
        previous_blob.reload(timeout=min(30, remaining()), retry=None)
        previous_generation = previous_blob.generation
        try:
            previous = json.loads(previous_blob.download_as_text(encoding="utf-8",
                timeout=min(30, remaining()), retry=None))
            if not isinstance(previous, dict):
                previous = None
                raise ValueError("manifest must be an object")
        except (ValueError, UnicodeError):
            logging.warning("Invalid private source manifest; full export required")

    for attempt in range(1, max_attempts + 1):
        before = after = None
        generation = None
        jobs = []
        active_job = None
        phase = "metadata_before"
        before_at = after_at = None
        try:
            remaining()
            before = source_sync.read_metadata(bounded_client)
            before_at = now()
            before_fingerprints = source_sync.fingerprints(before)
            # An unchanged source needs no plan/query/export, as before.
            if previous and previous.get("source_fingerprints") == before_fingerprints:
                return {"status": "unchanged", "generation": previous.get("generation")}
            phase = "metadata_preflight"
            wait(quiet_seconds)
            after = source_sync.read_metadata(bounded_client)
            after_at = now()
            if metadata_differences(before, after):
                raise SourceChangedDuringExport("source changed before private export")

            available = maintenance_budget - charged_bytes
            cap = min(per_export_cap, available)
            if cap <= 0:
                raise RuntimeError("private source export maintenance budget exhausted")
            phase = "plan"
            remaining()
            # Both families are actually exported here, even if only Logs changed.
            # Plan the full SELECT rather than treating a Logs-only change as free.
            plan = source_sync.make_plan(bounded_client, before, None, cap)
            remaining()
            generation = ("sync-" + source_sync.digest(before_fingerprints)[:20]
                          + "-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                          + "-" + unique()[:12])
            destination = "gs://" + bucket.name + "/" + prefix + "/" + generation
            full_uri, logs_uri = destination + "/full_sample-*.parquet", destination + "/logs-*.parquet"
            sql = (f"EXPORT DATA OPTIONS(uri='{full_uri}', format='PARQUET', overwrite=false) "
                   f"AS {source_sync.FULL_SQL}")
            phase = "full_export"
            # Reserve the worst case before submitting; failures cannot recover
            # budget by losing the job's billing statistics.
            charged_bytes += cap
            full_job = client.query(sql, location="US",
                job_id=f"ark_private_source_{generation}_full", job_retry=None,
                timeout=min(30, remaining()), retry=None, job_config=query_config(
                    maximum_bytes_billed=cap, use_query_cache=False,
                    labels={"ark_workload": "source_sync", "ark_component": "full_sample"}))
            jobs.append({"job_id": full_job.job_id, "kind": "full_sample", "complete": False})
            active_job = full_job
            full_job.result(timeout=remaining(), retry=None, job_retry=None)
            active_job = None
            jobs[-1]["complete"] = True
            billed = getattr(full_job, "total_bytes_billed", None)
            if isinstance(billed, int) and (billed < 0 or billed > cap):
                raise RuntimeError("source export returned invalid billing statistics")
            if isinstance(billed, int) and 0 <= billed <= cap:
                charged_bytes -= cap - billed
            jobs[-1]["charged_or_reserved_bytes"] = cap if billed is None else billed
            phase = "logs_export"
            logs_job = client.extract_table(source_sync.LOGS, logs_uri, location="US",
                job_id=f"ark_private_source_{generation}_logs", timeout=min(30, remaining()), retry=None,
                job_config=extract_config(destination_format="PARQUET"))
            jobs.append({"job_id": logs_job.job_id, "kind": "logs", "complete": False})
            active_job = logs_job
            logs_job.result(timeout=remaining(), retry=None)
            active_job = None
            jobs[-1]["complete"] = True
            phase = "metadata_after"
            remaining()
            after = source_sync.read_metadata(bounded_client)
            after_at = now()
            if metadata_differences(before, after):
                raise SourceChangedDuringExport("source changed during private export; retrying is required")

            phase = "commit"
            remaining()
            manifest = {"status": "ok", "mode": "controlled_export", "generation": generation,
                "created_at": now(), "source_fingerprints": before_fingerprints,
                "source_metadata": before,
                "export": {"full_sample_uri": full_uri, "logs_uri": logs_uri},
                "estimated_query_bytes": plan.get("estimated_query_bytes", 0),
                "source_consistency": {"contract": "exact_metadata_v1", "operation": operation,
                    "attempt": attempt, "before_at": before_at, "after_at": after_at,
                    "charged_or_reserved_bytes": charged_bytes, "jobs": jobs}}
            body = json.dumps(manifest, separators=(",", ":"), allow_nan=False)
            bucket.blob(prefix + "/" + generation + "/manifest.json").upload_from_string(
                body, content_type="application/json; charset=utf-8", if_generation_match=0,
                timeout=min(30, remaining()), retry=None)
            previous_blob.upload_from_string(body, content_type="application/json; charset=utf-8",
                                            if_generation_match=previous_generation,
                                            timeout=min(30, remaining()), retry=None)
            return {"status": "ok", "generation": generation,
                    "estimated_query_bytes": plan.get("estimated_query_bytes", 0),
                    "source_export_attempts": attempt}
        except Exception as error:
            if active_job is not None:
                try:
                    active_job.cancel(timeout=min(10, max(1, deadline - clock())), retry=None)
                except Exception as cancel_error:
                    logging.error("Source export cancellation unavailable (%s)", type(cancel_error).__name__)
            diagnostic = {"schema_version": 1, "operation": operation, "attempt": attempt,
                "phase": phase, "recorded_at": now(), "generation": generation,
                "before_at": before_at, "after_at": after_at,
                "before": before, "after": after,
                "before_fingerprints": source_sync.fingerprints(before) if before is not None else None,
                "after_fingerprints": source_sync.fingerprints(after) if after is not None else None,
                "differences": metadata_differences(before, after), "jobs": jobs,
                "error_type": type(error).__name__,
                "charged_or_reserved_bytes": charged_bytes, "maintenance_budget": maintenance_budget}
            try:
                bucket.blob(f"{prefix}-diagnostics/{operation}/attempt-{attempt}.json").upload_from_string(
                    json.dumps(diagnostic, separators=(",", ":"), allow_nan=False),
                    content_type="application/json; charset=utf-8", if_generation_match=0,
                    timeout=10, retry=None)
            except Exception as diagnostic_error:
                logging.error("Private source diagnostics unavailable (%s); consistency remains fail-closed",
                              type(diagnostic_error).__name__)
            if not isinstance(error, SourceChangedDuringExport) or attempt == max_attempts:
                raise
            # Do not retry arbitrary query/storage/permission/time failures.
            if charged_bytes >= maintenance_budget:
                raise RuntimeError("private source export maintenance budget prevents retry") from error
            wait(retry_seconds)
    raise AssertionError("unreachable source export retry state")
