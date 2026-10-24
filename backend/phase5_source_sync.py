"""Bounded, metadata-gated source sync for the private DuckDB builder.

The physical sources have neither partitions nor an ingestion/change timestamp.
Consequently a date or maximum table_id cursor is NOT a complete change feed.
Changed Full Sample generations use one canonical-view export; unchanged Logs
are reused. Exact table-level additions, corrections and deletions are reconciled
locally. This avoids all BigQuery derivative/snapshot queries, but does not claim
that exporting fewer result rows would reduce an unpartitioned source scan.

Default execution is a metadata/dry-run plan. --execute writes a new private
source directory and manifest; it never activates serving or enables a schedule.
The manifest is the commit marker. Failed attempts have no usable manifest.
Deterministic job IDs let retries attach to previously submitted export jobs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from phase5_process_lock import acquire as acquire_process_lock
from datetime import datetime, timezone
from pathlib import Path

SOURCE_PROJECT = "freestyle-190711"
BILLING_PROJECT = "ark-nova-stats-dashboard"
FULL = f"{SOURCE_PROJECT}.ark_nova.all_games_stat"
RAW = f"{SOURCE_PROJECT}.ark_nova.all_games_stat_raw"
LOGS = f"{SOURCE_PROJECT}.ark_nova.game_log_stat_v2"
ROUTINE = f"{SOURCE_PROJECT}.ark_nova.calculatePreMatchElo"
FULL_SQL = f"SELECT * EXCEPT(last_x_games) FROM `{FULL}`"
DEFAULT_CAP = 8 * 1024**3


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def gcloud(*args):
    executable = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if not executable:
        candidate = Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Cloud SDK/google-cloud-sdk/bin/gcloud.cmd"
        executable = str(candidate) if candidate.is_file() else None
    if not executable:
        raise RuntimeError("Google Cloud CLI is required for private object transfers")
    return subprocess.run([executable, *args], check=True, capture_output=True, text=True).stdout


def cloud_client(cli_auth=False):
    from google.cloud import bigquery
    credentials = None
    if cli_auth:
        # Capture the token in memory only. Never print it or put it in arguments.
        from google.oauth2.credentials import Credentials
        credentials = Credentials(gcloud("auth", "print-access-token").strip())
    return bigquery.Client(project=BILLING_PROJECT, credentials=credentials)


def table_metadata(table):
    info = table.to_api_repr()
    if info.get("streamingBuffer"):
        raise RuntimeError("Source has uncommitted streaming rows; retry after ingestion settles")
    return {key: info.get(key) for key in (
        "id", "etag", "lastModifiedTime", "numRows", "numBytes", "schema", "view",
        "timePartitioning", "rangePartitioning", "clustering",
    )}


def read_metadata(client):
    full = table_metadata(client.get_table(FULL))
    raw = table_metadata(client.get_table(RAW))
    logs = table_metadata(client.get_table(LOGS))
    routine = client.get_routine(ROUTINE).to_api_repr()
    # Include raw data AND canonical view/UDF definitions. View modification
    # time alone does not change when new physical source rows arrive.
    return {"full_sample": {"view": full, "raw": raw, "routine": routine}, "logs": logs}


def fingerprints(metadata):
    return {name: digest(value) for name, value in metadata.items()}


def changed_families(metadata, previous):
    prior = (previous or {}).get("source_fingerprints", {})
    return [name for name, value in fingerprints(metadata).items() if prior.get(name) != value]


def validate_budget(estimated, cap):
    if cap <= 0 or cap > DEFAULT_CAP:
        raise ValueError("Source sync ceiling must be positive and no more than 8 GiB")
    if estimated > cap:
        raise RuntimeError(f"Source export dry run needs {estimated} bytes; ceiling is {cap}")


def make_plan(client, metadata, previous, cap):
    from google.cloud import bigquery
    validate_budget(0, cap)
    changed = changed_families(metadata, previous)
    estimated = 0
    if "full_sample" in changed:
        job = client.query(FULL_SQL, location="US", job_config=bigquery.QueryJobConfig(
            dry_run=True, use_query_cache=False, maximum_bytes_billed=cap,
            labels={"ark_workload": "source_sync", "ark_component": "plan"},
        ))
        estimated = int(job.total_bytes_processed or 0)
        validate_budget(estimated, cap)
    return {"status": "unchanged" if not changed else "planned", "changed_families": changed,
            "estimated_query_bytes": estimated, "maximum_bytes_billed": cap,
            "source_fingerprints": fingerprints(metadata), "metadata": metadata}


def file_record(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(part)
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": h.hexdigest()}


def validate_files(root, manifest):
    records = manifest.get("files", [])
    if not records:
        raise RuntimeError("Sync manifest has no file checksums")
    names = [item["name"] for item in records]
    actual = {p.name for p in root.glob("*.parquet")}
    if len(set(names)) != len(names) or set(names) != actual:
        raise RuntimeError("Source file inventory differs from the committed manifest")
    for item in records:
        if Path(item["name"]).name != item["name"] or file_record(root / item["name"]) != item:
            raise RuntimeError("Source file checksum or size mismatch")
    if any(not any(name.startswith(family + "-") for name in names) for family in ("full_sample", "logs")):
        raise RuntimeError("Source manifest must contain both source families")


def existing_or_submit(client, job_id, submit):
    from google.api_core.exceptions import NotFound, Conflict
    try:
        job = client.get_job(job_id, location="US")
    except NotFound:
        try:
            job = submit()
        except Conflict:
            job = client.get_job(job_id, location="US")
    job.result()
    return job


def export_source(client, plan, previous_root, output_root, bucket, prefix):
    from google.cloud import bigquery
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]+", bucket):
        raise ValueError("Invalid private bucket name")
    if not re.fullmatch(r"[A-Za-z0-9_/-]+", prefix) or ".." in prefix:
        raise ValueError("Invalid private export prefix")
    if previous_root and output_root.resolve() == previous_root.resolve():
        raise ValueError("Source generations must be immutable: choose a new directory")
    if plan["status"] == "unchanged":
        return {k: v for k, v in plan.items() if k != "metadata"}
    if (output_root / "manifest.json").exists():
        manifest = json.loads((output_root / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("source_fingerprints") != plan["source_fingerprints"]:
            raise RuntimeError("Output already contains a different source generation")
        validate_files(output_root, manifest)
        return {"status": "reused", "generation": manifest["generation"], "source_root": str(output_root)}
    output_root.mkdir(parents=True, exist_ok=True)
    lock_path = output_root / ".sync.lock"
    lock = acquire_process_lock(lock_path)
    try:
        request_path = output_root / "sync-request.json"
        if request_path.exists():
            if json.loads(request_path.read_text(encoding="utf-8")) != plan["source_fingerprints"]:
                raise RuntimeError("Incomplete output belongs to another source version; choose a new directory")
        else:
            request_path.write_text(json.dumps(plan["source_fingerprints"], sort_keys=True), encoding="utf-8")
        generation = "sync-" + digest(plan["source_fingerprints"])[:24]
        uri = f"gs://{bucket}/{prefix.strip('/')}/{generation}"
        operation = digest({"uri": uri, "fingerprints": plan["source_fingerprints"]})[:32]
        jobs = {}
        for family in ("full_sample", "logs"):
            if family not in plan["changed_families"]:
                old = sorted(previous_root.glob(f"{family}-*.parquet")) if previous_root else []
                if not old:
                    raise RuntimeError(f"Reusable {family} source files are missing")
                for path in old:
                    target = output_root / path.name
                    if not target.exists():
                        try:
                            os.link(path, target)
                        except OSError:
                            shutil.copy2(path, target)
                continue
            job_id = f"ark_source_sync_{operation}_{family}"
            if family == "full_sample":
                sql = f"EXPORT DATA OPTIONS(uri='{uri}/full_sample-*.parquet', format='PARQUET', overwrite=false) AS {FULL_SQL}"
                job = existing_or_submit(client, job_id, lambda: client.query(
                    sql, job_id=job_id, job_retry=None, location="US", job_config=bigquery.QueryJobConfig(
                        maximum_bytes_billed=plan["maximum_bytes_billed"], use_query_cache=False,
                        labels={"ark_workload": "source_sync", "ark_component": "full_sample"},
                    )))
            else:
                job = existing_or_submit(client, job_id, lambda: client.extract_table(
                    LOGS, f"{uri}/logs-*.parquet", job_id=job_id, location="US",
                    job_config=bigquery.ExtractJobConfig(destination_format="PARQUET",
                        labels={"ark_workload": "source_sync", "ark_component": "logs"}),
                ))
            jobs[family] = {"job_id": job.job_id, "bytes_processed": getattr(job, "total_bytes_processed", 0),
                            "bytes_billed": getattr(job, "total_bytes_billed", 0)}
            job.reload()
            # Job.to_api_repr() serializes submission fields only. Output shard
            # counts live in the reloaded server response; keep this access here.
            statistics = job._properties["statistics"]
            if family == "full_sample":
                exported = statistics["query"]["exportDataStatistics"]
                expected_files = int(exported["fileCount"])
                jobs[family]["row_count"] = int(exported["rowCount"])
            else:
                expected_files = sum(map(int, statistics["extract"]["destinationUriFileCounts"]))
                jobs[family]["row_count"] = int(plan["metadata"]["logs"]["numRows"])
            jobs[family]["file_count"] = expected_files
            gcloud("storage", "cp", f"{uri}/{family}-*.parquet", str(output_root))
            if len(list(output_root.glob(f"{family}-*.parquet"))) != expected_files:
                raise RuntimeError(f"{family} downloaded shard count does not match the completed export job")
        if fingerprints(read_metadata(client)) != plan["source_fingerprints"]:
            raise RuntimeError("Source changed during export; candidate not committed. Re-plan with fresh metadata.")
        files = [file_record(p) for p in sorted(output_root.glob("*.parquet"))]
        manifest = {"status": "ok", "mode": "source_sync", "schema_version": 1,
                    "generation": generation, "created_at": utc_now(),
                    "source_fingerprints": plan["source_fingerprints"], "source_metadata": plan["metadata"],
                    "changed_families": plan["changed_families"], "jobs": jobs, "files": files,
                    "parent_source_root": str(previous_root) if previous_root else None}
        validate_files(output_root, manifest)
        temporary = output_root / "manifest.json.tmp"
        temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, output_root / "manifest.json")
        return {"status": "ok", "generation": generation, "source_root": str(output_root),
                "changed_families": plan["changed_families"], "jobs": jobs, "file_count": len(files)}
    finally:
        os.close(lock)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--bucket", default="ark-nova-stats-phase2-import-413312054512")
    parser.add_argument("--prefix", default="phase5/source-sync")
    parser.add_argument("--maximum-bytes-billed", type=int, default=DEFAULT_CAP)
    parser.add_argument("--cli-auth", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    prior = None
    if args.previous:
        prior = json.loads((args.previous / "manifest.json").read_text(encoding="utf-8"))
        if prior.get("status") != "ok":
            raise RuntimeError("Previous source manifest is not committed")
        if prior.get("mode") == "source_sync":
            validate_files(args.previous, prior)
    if args.execute and args.output is None:
        parser.error("--execute requires --output")
    client = cloud_client(args.cli_auth)
    plan = make_plan(client, read_metadata(client), prior, args.maximum_bytes_billed)
    result = export_source(client, plan, args.previous, args.output, args.bucket, args.prefix) if args.execute else plan
    print(json.dumps({k: v for k, v in result.items() if k != "metadata"}, indent=2, sort_keys=True, default=str))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
