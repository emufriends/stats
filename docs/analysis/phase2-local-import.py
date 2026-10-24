"""Prepare a private Phase 2 source generation for local snapshot building.

This tool is intentionally separate from the deployed Cloud Function.  It is
the first migration step toward serving filters and snapshots from a private
local analytical database instead of submitting one BigQuery query per
snapshot or filter.

The default ``plan`` command only reads BigQuery metadata and is free.  The
``export`` command is explicit because exporting the canonical view performs
one BigQuery analysis query.  Nothing is written to the public website, Git,
or the deployed cache bucket unless the caller supplies a private export
bucket and an explicit command.

Required environment for export/download:

    PHASE2_IMPORT_BUCKET=private bucket name
    PHASE2_IMPORT_PREFIX=phase2/source (optional)

The export layout is versioned so a failed or partial import never replaces a
previous generation.  A later local builder can consume the Parquet files and
publish a single generation pointer after validation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT = "freestyle-190711"
BILLING_PROJECT = "ark-nova-stats-dashboard"
SOURCE_EXPORT_MAX_BYTES = 8 * 1024**3
SOURCE_DATASET = "ark_nova"
SOURCE_FULL_SAMPLE = f"{PROJECT}.{SOURCE_DATASET}.all_games_stat"
SOURCE_LOGS = f"{PROJECT}.{SOURCE_DATASET}.game_log_stat_v2"
CANONICAL_FULL_SQL = (
    f"SELECT * EXCEPT(last_x_games) FROM `{SOURCE_FULL_SAMPLE}`"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_json(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def import_config() -> tuple[str, str]:
    bucket = os.environ.get("PHASE2_IMPORT_BUCKET", "").strip()
    prefix = os.environ.get("PHASE2_IMPORT_PREFIX", "phase2/source").strip("/")
    if not bucket:
        raise SystemExit(
            "Set PHASE2_IMPORT_BUCKET to a private bucket before export or download."
        )
    if not prefix:
        raise SystemExit("PHASE2_IMPORT_PREFIX must not be empty.")
    return bucket, prefix


def _metadata_from_bq_cli(table_name: str) -> dict:
    """Read table metadata without requiring the Python client library.

    The development desktop has the Google Cloud CLI but does not necessarily
    have the Function's deployment dependencies installed.  Keeping ``plan``
    usable there makes the free metadata-only audit convenient; export still
    intentionally requires the Google Cloud Python libraries on the private
    worker.
    """
    candidates = [
        shutil.which("bq"),
        shutil.which("bq.cmd"),
        os.environ.get("BQ_CLI"),
        r"C:\Users\ascri\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\bq.cmd",
    ]
    executable = next((item for item in candidates if item and Path(item).exists()), None)
    if not executable:
        raise SystemExit(
            "Install google-cloud-bigquery or make the bq CLI available for plan mode."
        )
    cli_table = table_name.replace(".", ":", 1)
    result = subprocess.run(
        [executable, "show", "--format=prettyjson", cli_table],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def source_metadata(client=None):
    if client is None:
        full = _metadata_from_bq_cli(SOURCE_FULL_SAMPLE)
        logs = _metadata_from_bq_cli(SOURCE_LOGS)
        full_schema = full.get("schema", {}).get("fields", [])
        logs_schema = logs.get("schema", {}).get("fields", [])
        full_table = {
            "name": SOURCE_FULL_SAMPLE,
            "kind": "view" if full.get("type") == "VIEW" else "table",
            "modified": full.get("lastModifiedTime"),
            "schema": [
                {
                    "name": field.get("name"),
                    "type": field.get("type"),
                    "mode": field.get("mode", "NULLABLE"),
                }
                for field in full_schema
                if field.get("name") != "last_x_games"
            ],
        }
        logs_table = {
            "name": SOURCE_LOGS,
            "kind": "table",
            "modified": logs.get("lastModifiedTime"),
            "num_rows": int(logs.get("numRows") or 0),
            "num_bytes": int(logs.get("numBytes") or 0),
            "schema": [
                {
                    "name": field.get("name"),
                    "type": field.get("type"),
                    "mode": field.get("mode", "NULLABLE"),
                }
                for field in logs_schema
            ],
        }
        contract = {
            "schema_version": 1,
            "full_sample": full_table,
            "logs": logs_table,
            "canonical_full_sample_sql": CANONICAL_FULL_SQL,
        }
        contract["source_fingerprint"] = sha256_json(contract)
        return contract
    full = client.get_table(SOURCE_FULL_SAMPLE)
    logs = client.get_table(SOURCE_LOGS)
    full_table = {
        "name": SOURCE_FULL_SAMPLE,
        "kind": "view" if full.table_type == "VIEW" else "table",
        "modified": full.modified.isoformat() if full.modified else None,
        "schema": [
            {"name": field.name, "type": field.field_type, "mode": field.mode}
            for field in full.schema
            if field.name != "last_x_games"
        ],
    }
    logs_table = {
        "name": SOURCE_LOGS,
        "kind": "table",
        "modified": logs.modified.isoformat() if logs.modified else None,
        "num_rows": int(logs.num_rows or 0),
        "num_bytes": int(logs.num_bytes or 0),
        "schema": [
            {"name": field.name, "type": field.field_type, "mode": field.mode}
            for field in logs.schema
        ],
    }
    contract = {
        "schema_version": 1,
        "full_sample": full_table,
        "logs": logs_table,
        "canonical_full_sample_sql": CANONICAL_FULL_SQL,
    }
    contract["source_fingerprint"] = sha256_json(contract)
    return contract


def plan() -> int:
    contract = source_metadata()
    print(json.dumps({"status": "ok", "mode": "plan", **contract}, indent=2))
    return 0


def export_generation() -> int:
    from google.cloud import bigquery

    bucket, prefix = import_config()
    # The external source project is read-only for this dashboard. Import jobs
    # are billed to our project and use the same bounded source-export budget
    # as the metadata-gated Phase 5 sync (see phase5-source-sync.md).
    client = bigquery.Client(project=BILLING_PROJECT)
    contract = source_metadata(client)
    generation = f"{utc_now().replace(':', '').replace('-', '')}-{contract['source_fingerprint'][:12]}"
    root = f"gs://{bucket}/{prefix}/{generation}"

    # EXPORT DATA over the view is the one intentionally charged source import.
    # It is performed once for the whole generation, rather than once per page
    # or snapshot.  Parquet preserves nested Logs fields and compresses transfer
    # and local storage without changing values.
    full_export_sql = f"""
    EXPORT DATA OPTIONS(
      uri='{root}/full_sample-*.parquet',
      format='PARQUET',
      overwrite=true
    ) AS
    {CANONICAL_FULL_SQL}
    """
    estimate = client.query(CANONICAL_FULL_SQL, location="US", job_config=bigquery.QueryJobConfig(
        dry_run=True, use_query_cache=False, maximum_bytes_billed=SOURCE_EXPORT_MAX_BYTES,
    ))
    if (estimate.total_bytes_processed or 0) > SOURCE_EXPORT_MAX_BYTES:
        raise RuntimeError("Source export exceeds the 8 GiB import ceiling")
    full_job = client.query(full_export_sql, location="US", job_config=bigquery.QueryJobConfig(
        maximum_bytes_billed=SOURCE_EXPORT_MAX_BYTES,
        labels={"ark_workload": "source_sync", "ark_component": "bootstrap"},
    ))
    full_job.result()

    # A native extract of the physical Logs table avoids wrapping it in a
    # second SELECT query.  The export service writes to the private bucket;
    # the caller can download it to the local builder afterward.
    extract_job = client.extract_table(
        SOURCE_LOGS,
        f"{root}/logs-*.parquet",
        location="US",
        job_config=bigquery.ExtractJobConfig(destination_format="PARQUET"),
    )
    extract_job.result()

    manifest = {
        "status": "ok",
        "mode": "export",
        "generation": generation,
        "created_at": utc_now(),
        "bucket": bucket,
        "prefix": f"{prefix}/{generation}",
        "source": contract,
        "export": {
            "full_sample_uri": f"{root}/full_sample-*.parquet",
            "logs_uri": f"{root}/logs-*.parquet",
            "full_sample_job_id": full_job.job_id,
            "full_sample_bytes_processed": full_job.total_bytes_processed,
            "logs_extract_job_id": extract_job.job_id,
        },
    }
    # Keep the manifest beside the generation.  The local builder should only
    # promote it after both object families are present and readable.
    from google.cloud import storage

    blob = storage.Client().bucket(bucket).blob(f"{prefix}/{generation}/manifest.json")
    blob.cache_control = "no-store, max-age=0"
    blob.upload_from_string(
        json.dumps(manifest, indent=2, sort_keys=True),
        content_type="application/json; charset=utf-8",
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "mode": "export",
                "generation": generation,
                "manifest": f"gs://{bucket}/{prefix}/{generation}/manifest.json",
                "full_sample_bytes_processed": full_job.total_bytes_processed,
            },
            indent=2,
        )
    )
    return 0


def download_generation(generation: str, output_dir: Path) -> int:
    bucket, prefix = import_config()
    from google.cloud import storage

    generation_prefix = f"{prefix}/{generation}/"
    client = storage.Client()
    blobs = list(client.list_blobs(bucket, prefix=generation_prefix))
    if not blobs:
        raise SystemExit(f"No objects found for gs://{bucket}/{generation_prefix}")
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded = []
    for blob in blobs:
        relative = blob.name[len(generation_prefix):]
        if not relative or relative.endswith("/"):
            continue
        target = output_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(target))
        downloaded.append(relative)
    if "manifest.json" not in downloaded:
        raise SystemExit("Generation is incomplete: manifest.json is missing.")
    print(json.dumps({"status": "ok", "mode": "download", "files": downloaded}, indent=2))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("plan", help="Read source metadata only; no analysis query.")
    subparsers.add_parser(
        "export", help="Export one private versioned source generation."
    )
    download_parser = subparsers.add_parser(
        "download", help="Download a previously exported generation."
    )
    download_parser.add_argument("generation")
    download_parser.add_argument("output_dir", type=Path)
    args = parser.parse_args(argv)
    if args.command == "plan":
        return plan()
    if args.command == "export":
        return export_generation()
    return download_generation(args.generation, args.output_dir)


if __name__ == "__main__":
    sys.exit(main())
