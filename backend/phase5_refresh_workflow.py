"""Build and validate one rollback-safe DuckDB release candidate.

The workflow owns source import, narrow derivatives, moving-source
materialization, snapshots, and the authoritative artifact manifest. Production
uses ``--defer-activation`` so the coordinated publisher can advance public
objects and local pointers together. Direct private runs may activate only after
the same complete validation boundary. BigQuery source tables are never
modified.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase3_duckdb_service import DuckDBServingStore, GenerationManager, _load_duckdb, _utc_now
from phase4_metadata import fetch_tournament_metadata, load_arena_settings, materialize_metadata_tables
from phase4_materialize_route_derivatives import _create_relations as create_arena_relations
from phase4_records_source import _sha, read_biggest, read_elo, read_fastest
from phase5_source_materialize import materialize as materialize_source
from phase5_source_reconcile import reconcile as reconcile_source
from phase5_refresh_metrics import RefreshTimings
from phase5_offline_stage import invoke as invoke_offline_stage
from phase5_operational_controls import (
    ensure_refresh_headroom,
    prune_local_releases,
    prune_source_exports,
    refresh_inputs,
    validate_reusable_candidate,
)


EXPECTED_RELATIONS = {
    "game_player_narrow", "prepared_full_sample_narrow", "card_play_narrow", "corrupted_tables_narrow",
    "completed_tables_narrow",
    "players_metrics_narrow",
    "players_by_identity_narrow", "players_default_cohorts_narrow",
    "card_log_narrow", "card_in_hand_narrow", "card_seen_narrow",
    "card_filter_fact_mw_narrow", "card_filter_fact_base_narrow",
    "card_filter_table_fact_mw_narrow", "card_filter_table_fact_base_narrow",
    "card_play_event_narrow", "opening_hand_narrow",
    "endgame_score_event_narrow",
    "conservation_cp_player_narrow", "conservation_cp_opportunity_narrow",
    "mw_action_card_eligible_tables_narrow",
    "mw_action_card_selection_narrow",
    "mw_action_card_catalog_narrow", "mw_action_card_draft_narrow",
    "mw_action_card_pair_narrow",
}


def _write_progress(path: Path | None, percent: int, phase: str) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps({"progress_percent": percent, "phase": phase}) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False
    return True


def _lock(path: Path, stale_after_seconds: int = 4 * 60 * 60) -> int:
    """Acquire the refresh lock, recovering one left by a killed workflow."""
    path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(2):
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, json.dumps({
                "pid": os.getpid(), "created_at": _utc_now(), "created_unix": time.time(),
            }).encode("utf-8"))
            os.fsync(descriptor)
            return descriptor
        except FileExistsError as exc:
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                pid = int(existing.get("pid") or 0)
                age = time.time() - float(existing.get("created_unix") or path.stat().st_mtime)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pid, age = 0, stale_after_seconds + 1
            if attempt == 0 and (age > stale_after_seconds or not _process_exists(pid)):
                path.unlink(missing_ok=True)
                continue
            raise RuntimeError(f"private refresh already running: {path}") from exc
    raise RuntimeError(f"could not acquire private refresh lock: {path}")


def _materialize_records(
    connection, source_dir: Path, fallback_database: Path | None = None
) -> dict[str, int]:
    fastest = read_fastest(source_dir / "records-fastest.csv")
    biggest = read_biggest(source_dir / "records-biggest.csv")
    try:
        elo = read_elo(source_dir / "records-elo.csv")
    except ValueError:
        if fallback_database is None:
            raise
        fallback = _load_duckdb()
        fallback_connection = fallback.connect(str(fallback_database), read_only=True)
        try:
            elo = fallback_connection.execute(
                "SELECT source_row, country, player, peak_elo, peak_arena, rank "
                "FROM records_elo_leaderboard_narrow ORDER BY rank"
            ).fetchall()
        finally:
            fallback_connection.close()
        if len(elo) < 100:
            raise ValueError("active generation has no valid Elo leaderboard fallback")
    connection.execute("DROP TABLE IF EXISTS records_manual_narrow")
    connection.execute("""CREATE TABLE records_manual_narrow(
      record_view VARCHAR NOT NULL, source_row BIGINT NOT NULL,
      table_id BIGINT NOT NULL, player VARCHAR NOT NULL, mode VARCHAR,
      turns DOUBLE, score DOUBLE, ept BIGINT, flat BIGINT, "end" BIGINT,
      total BIGINT, move BIGINT, actions BIGINT, map_code VARCHAR,
      result_code VARCHAR, game_date VARCHAR
    )""")
    connection.executemany(
        "INSERT INTO records_manual_narrow VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        fastest + biggest,
    )
    connection.execute("DROP TABLE IF EXISTS records_elo_leaderboard_narrow")
    connection.execute("""CREATE TABLE records_elo_leaderboard_narrow(
      source_row BIGINT NOT NULL, country VARCHAR NOT NULL, player VARCHAR NOT NULL,
      peak_elo DOUBLE NOT NULL, peak_arena DOUBLE, rank BIGINT NOT NULL
    )""")
    connection.executemany(
        "INSERT INTO records_elo_leaderboard_narrow VALUES (?, ?, ?, ?, ?, ?)", elo
    )
    return {
        "records_manual_narrow": len(fastest) + len(biggest),
        "records_elo_leaderboard_narrow": len(elo),
    }


def _tournament_metadata_with_fallback(
    source_dir: Path, fallback_database: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Consume the worker-validated tournament cache, with direct-run fallback."""
    cache_path = source_dir / "tournament-metadata.json"
    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        rows = list(cached["rows"])
        if rows:
            state = str((cached.get("source") or {}).get("state") or "fresh")
            status_path = source_dir / "source-status.json"
            if status_path.is_file():
                status = json.loads(status_path.read_text(encoding="utf-8"))
                state = str(
                    (status.get("sources") or {}).get("tournament-metadata.json", {}).get("state")
                    or state
                )
            return rows, {**dict(cached.get("source") or {}), "state": state}
    except (FileNotFoundError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        pass
    try:
        rows, info = fetch_tournament_metadata()
        payload = {"rows": rows, "source": {**info, "state": "fresh"}}
        temporary = cache_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, cache_path)
        return rows, payload["source"]
    except Exception as fetch_error:
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            rows = list(cached["rows"])
            if rows:
                return rows, {
                    **dict(cached.get("source") or {}),
                    "state": "last_known_good",
                    "fallback_reason": type(fetch_error).__name__,
                }
        except (FileNotFoundError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            pass
        duckdb = _load_duckdb()
        connection = duckdb.connect(str(fallback_database), read_only=True)
        try:
            rows = [
                {"table_id": row[0], "tournament_name": row[1], "season": row[2]}
                for row in connection.execute(
                    "SELECT table_id, tournament_name, season FROM tournament_tables_metadata ORDER BY table_id"
                ).fetchall()
            ]
        finally:
            connection.close()
        if not rows:
            raise RuntimeError("tournament metadata is unavailable and no last-known-good rows exist") from fetch_error
        return rows, {
            "state": "last_known_good", "source": "active_generation",
            "row_count": len(rows), "fallback_reason": type(fetch_error).__name__,
        }


def refresh(
    *,
    root: Path,
    source_root: Path,
    generation_id: str,
    builder_path: Path,
    arena_settings: Path,
    moving_source_dir: Path,
    threads: int = 2,
    memory_limit: str = "2800MB",
    source_memory_limit: str | None = None,
    snapshot_chunk: int = 100000,
    report_path: Path | None = None,
    incremental_source: bool = False,
    progress_file: Path | None = None,
    activate_release: bool = True,
    isolate_stages: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    # Import and analytical preparation have different working sets. Keep their
    # budgets independent; fresh stage processes release import allocations
    # before the builder starts. This does not alter source-family sync/export.
    source_budget = source_memory_limit or memory_limit
    timing = RefreshTimings()
    app_root = builder_path.resolve().parent
    private = root / "phase2_private_data"
    generations = private / "generations"
    staging = private / "staging"
    pointer = root / "phase3_private_serving" / "current.json"
    manager = GenerationManager(generations, pointer)
    previous = manager.current()
    if previous is None:
        raise RuntimeError("no active generation")
    source_manifest = json.loads((source_root / "manifest.json").read_text(encoding="utf-8"))
    source_generation = str(source_manifest.get("generation") or generation_id)
    input_contract = refresh_inputs(app_root, source_root, moving_source_dir)
    refresh_fingerprint = str(input_contract["fingerprint"])
    if previous.manifest.get("refresh_fingerprint") == refresh_fingerprint:
        if validate_reusable_candidate(
            root, previous.generation_id, refresh_fingerprint
        ) is None:
            raise RuntimeError("unchanged active release failed artifact revalidation")
        if not DuckDBServingStore(
            manager, generation_id=previous.generation_id
        ).health().get("ready"):
            raise RuntimeError("unchanged active release failed its read-only health query")
        output = {
            "status": "unchanged",
            "generation": previous.generation_id,
            "data_version": previous.data_version,
            "previous_generation": previous.generation_id,
            "activated": True,
            "refresh_fingerprint": refresh_fingerprint,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }
        if report_path:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _write_progress(progress_file, 96, "No source or build-contract changes")
        return output
    if generation_id == previous.generation_id:
        raise ValueError("generation must differ from the active generation")
    staging.mkdir(parents=True, exist_ok=True)
    staging_db = staging / f"{generation_id}.duckdb"
    report_file = staging / f"{generation_id}.builder.json"
    snapshot_root = private / "snapshots" / generation_id
    lock_fd = _lock(private / "refresh.lock")
    activated = False
    candidate_adopted = False
    previous_snapshot_pointer = None
    snapshot_pointer = private / "snapshots" / "current.json"
    if snapshot_pointer.is_file():
        previous_snapshot_pointer = snapshot_pointer.read_bytes()
    try:
        reusable = validate_reusable_candidate(
            root, generation_id, refresh_fingerprint
        )
        if reusable is not None:
            if not DuckDBServingStore(manager, generation_id=generation_id).health().get("ready"):
                raise RuntimeError("reusable candidate database failed its read-only health query")
            output = {
                "status": "candidate_ready",
                **reusable,
                "previous_generation": previous.generation_id,
                "activated": False,
                "reused_candidate": True,
                "refresh_fingerprint": refresh_fingerprint,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
            }
            if report_path:
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(
                    json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )
            _write_progress(progress_file, 96, "Reusing validated release candidate")
            return output
        retention = prune_local_releases(root, allow_staging_cleanup=True)
        retention['sources'] = prune_source_exports(root, extra_protected=[source_root])
        disk_headroom = ensure_refresh_headroom(root, previous.database_path)
        if staging_db.exists():
            raise FileExistsError(staging_db)
        _write_progress(progress_file, 38, "Importing changed source data")
        # Source reconciliation updates a staging copy. Full Sample facts are
        # rebuilt; unchanged log-scoped derivatives may be reused only after
        # producer, complete canonical population and numeric-key checks.
        with timing.stage('source_import'):
            if isolate_stages:
                source_report = invoke_offline_stage('source', {
                    'source_root': source_root, 'database': staging_db,
                    'previous_database': previous.database_path,
                    'incremental_source': incremental_source,
                    'threads': threads, 'memory_limit': source_budget,
                    'temp_directory': staging / f'{generation_id}.source-spill',
                }, staging / f'{generation_id}.source-stage.json')
            elif incremental_source:
                source_report = reconcile_source(
                    source_root, previous.database_path, staging_db,
                    threads=threads, memory_limit=source_budget,
                    temp_directory=staging / f"{generation_id}.source-spill",
                )
            else:
                source_report = materialize_source(
                    source_root, staging_db, threads=threads, memory_limit=source_budget,
                    temp_directory=staging / f"{generation_id}.source-spill",
                )
        if isolate_stages:
            timing.stages[-1]['child_process_rss_highwater_bytes'] = source_report['stage_process_rss_highwater_bytes']
        _write_progress(progress_file, 43, "Importing Arena and tournament metadata")
        ancillary_settings = {
            'database': staging_db, 'previous_database': previous.database_path,
            'moving_source_dir': moving_source_dir, 'arena_settings': arena_settings,
            'threads': threads, 'memory_limit': memory_limit,
            'temp_directory': staging / f'{generation_id}.metadata-spill',
        }
        if isolate_stages:
            metadata_result = invoke_offline_stage('metadata', ancillary_settings,
                staging / f'{generation_id}.metadata-stage.json')
            tournament_info, arena_info = metadata_result['tournament_info'], metadata_result['arena_info']
        else:
            tournament_rows, tournament_info = _tournament_metadata_with_fallback(
                moving_source_dir, previous.database_path
            )
            arena_rows, arena_info = load_arena_settings(arena_settings)
            duckdb = _load_duckdb()
            connection = duckdb.connect(str(staging_db))
            try:
                connection.execute('SET threads=?', [max(1, int(threads))])
                connection.execute('SET memory_limit=?', [memory_limit])
                connection.execute('SET preserve_insertion_order=false')
                materialize_metadata_tables(connection, tournament_rows, arena_rows)
                connection.execute("CHECKPOINT")
            finally:
                connection.close()
        source_status_path = moving_source_dir / "source-status.json"
        moving_source_status = (
            json.loads(source_status_path.read_text(encoding="utf-8"))
            if source_status_path.is_file() else {"sources": {}}
        )
        arena_info["state"] = (
            moving_source_status.get("sources", {})
            .get("arena_settings.csv", {}).get("state", "unknown")
        )
        _write_progress(progress_file, 48, "Building canonical prepared relations")
        with timing.stage('analytical_derivatives'):
            if isolate_stages:
                builder_stage = invoke_offline_stage('builder', {
                    'builder': builder_path, 'database': staging_db,
                    'builder_report': report_file,
                    'threads': threads, 'memory_limit': memory_limit,
                    'temp_directory': staging / f'{generation_id}.builder-spill',
                    'merge_players': app_root / 'merge_players.csv',
                    'source_manifest': source_root / 'manifest.json',
                    'previous_database': previous.database_path,
                    'reuse_report': previous.manifest.get('builder') or {},
                }, staging / f'{generation_id}.builder-stage.json')
                status = 0
            else:
                builder = _load_module(builder_path, "phase5_refresh_builder")
                status = builder.run(
                    staging_db, report_file, threads=threads, memory_limit=memory_limit,
                    temp_directory=staging / f"{generation_id}.builder-spill",
                    merge_players_path=app_root / "merge_players.csv",
                    source_manifest=source_root / 'manifest.json',
                    reuse_database=previous.database_path,
                    reuse_report=previous.manifest.get('builder') or {},
                )
        if isolate_stages:
            timing.stages[-1]['child_process_rss_highwater_bytes'] = builder_stage['stage_process_rss_highwater_bytes']
        if status != 0:
            raise RuntimeError(f"narrow builder returned {status}")
        builder_report = json.loads(report_file.read_text(encoding="utf-8"))
        if builder_report.get("status") != "ok":
            raise RuntimeError("narrow builder report is not successful")
        missing = sorted(EXPECTED_RELATIONS - set(builder_report.get("relations", {})))
        if missing:
            raise RuntimeError(f"builder report is missing relations: {missing}")
        _write_progress(progress_file, 65, "Importing Arena rosters and Records metadata")
        if isolate_stages:
            ancillary_settings['temp_directory'] = staging / f'{generation_id}.roster-spill'
            roster_result = invoke_offline_stage('rosters_records', ancillary_settings,
                staging / f'{generation_id}.roster-stage.json')
            arena_counts, record_counts = roster_result['arena_counts'], roster_result['record_counts']
        else:
            connection = duckdb.connect(str(staging_db))
            try:
                connection.execute('SET threads=?', [max(1, int(threads))])
                connection.execute('SET memory_limit=?', [memory_limit])
                connection.execute('SET preserve_insertion_order=false')
                arena_counts = create_arena_relations(connection, moving_source_dir)
                record_counts = _materialize_records(
                    connection, moving_source_dir, previous.database_path
                )
                connection.execute("CHECKPOINT")
            finally:
                connection.close()
        _write_progress(progress_file, 75, "Generating default snapshots")

        manifest = dict(previous.manifest)
        manifest.update({
            "generation": generation_id,
            "data_version": f"phase5-source-{source_generation}",
            "source_generation": source_generation,
            "refresh_fingerprint": refresh_fingerprint,
            "refresh_inputs": input_contract,
            "database": str(generations / f"{generation_id}.duckdb"),
            "parent_generation": previous.generation_id,
            "staged_at": _utc_now(),
            "status": "ok",
            "source_materialization": source_report,
            "builder": builder_report,
            "metadata_sources": {"tournament_sheet": tournament_info, "arena_settings": arena_info},
            "route_derivatives": {**arena_counts, **record_counts},
            "moving_sources": {
                "status": moving_source_status,
                "arena_settings_sha256": _sha(moving_source_dir / "arena_settings.csv"),
                "arena_rosters": {
                    path.name: _sha(path)
                    for path in sorted(moving_source_dir.glob("s*.csv"))
                },
                "records_fastest_sha256": _sha(moving_source_dir / "records-fastest.csv"),
                "records_biggest_sha256": _sha(moving_source_dir / "records-biggest.csv"),
                "records_elo_sha256": _sha(moving_source_dir / "records-elo.csv"),
            },
            "operational_controls": {
                "disk_headroom": disk_headroom,
                "retention": retention,
            },
        })
        manifest_path = staging / f"{generation_id}.manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        candidate = manager.adopt_existing(generation_id, staging_db, manifest_path)
        candidate_adopted = True

        snapshot_builder = _load_module(
            app_root / "phase5_snapshot_builder.py",
            "phase5_refresh_snapshot_builder",
        )
        with timing.stage('snapshots_indexes_pack'):
            if isolate_stages:
                snapshot_result = invoke_offline_stage('snapshots', {
                    'root': root, 'output': snapshot_root, 'generation': generation_id,
                    'chunk': snapshot_chunk,
                    'threads': int(os.environ.get('DUCKDB_SNAPSHOT_THREADS', str(threads))),
                    'memory_limit': os.environ.get('DUCKDB_SNAPSHOT_MEMORY_LIMIT', memory_limit),
                }, staging / f'{generation_id}.snapshot-stage.json')
            else:
                snapshot_result = snapshot_builder.build(root, snapshot_root, generation_id, snapshot_chunk)
        if isolate_stages:
            timing.stages[-1]['child_process_rss_highwater_bytes'] = snapshot_result['stage_process_rss_highwater_bytes']
        if snapshot_result.get("status") != "ok":
            raise RuntimeError("snapshot artifact manifest is not publishable")
        if snapshot_result.get("generation") != generation_id:
            raise RuntimeError("snapshot artifact manifest belongs to another generation")
        if snapshot_result.get("data_version") != manifest["data_version"]:
            raise RuntimeError("snapshot artifact manifest has the wrong data version")
        required_keys = snapshot_result.get("required_object_keys") or []
        artifacts = snapshot_result.get("artifacts") or []
        if len(required_keys) != len(artifacts) or set(required_keys) != {
            item.get("object_key") for item in artifacts
        }:
            raise RuntimeError("snapshot artifact manifest is incomplete")
        for artifact in artifacts:
            artifact_path = Path(artifact["path"])
            if not artifact_path.is_file() or artifact_path.stat().st_size != artifact.get("bytes"):
                raise RuntimeError(f"release artifact is missing or incomplete: {artifact_path}")
        (snapshot_root / "manifest.json").write_text(
            json.dumps(snapshot_result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        # Candidate validation has completed while the old generation remained
        # active. Record all release identities in the generation manifest
        # before the only activation point.
        published_manifest = dict(candidate.manifest)
        published_manifest["release"] = {
            "status": "validated",
            "release_version": snapshot_result.get("release_version"),
            "artifact_manifest": str(snapshot_root / "release-manifest.json"),
            "artifact_count": snapshot_result.get("artifact_count"),
            "versions": snapshot_result.get("versions"),
            "validated_at": _utc_now(),
        }
        generation_manifest = generations / f"{generation_id}.manifest.json"
        generation_manifest_tmp = generation_manifest.with_suffix(".manifest.json.tmp")
        generation_manifest_tmp.write_text(
            json.dumps(published_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(generation_manifest_tmp, generation_manifest)

        if activate_release:
            _write_progress(progress_file, 96, "Activating the validated release")
            manager.activate(candidate.generation_id)
            activated = True
            snapshot_pointer.parent.mkdir(parents=True, exist_ok=True)
            snapshot_pointer_tmp = snapshot_pointer.with_suffix(".json.tmp")
            snapshot_pointer_tmp.write_text(
                json.dumps({
                    "status": "ok",
                    "generation": generation_id,
                    "data_version": manifest["data_version"],
                    "manifest": str(snapshot_root / "manifest.json"),
                    "release_manifest": str(snapshot_root / "release-manifest.json"),
                    "release_version": snapshot_result.get("release_version"),
                    "published_at": _utc_now(),
                }, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(snapshot_pointer_tmp, snapshot_pointer)
            _write_progress(progress_file, 98, "Publishing the private generation")
        else:
            _write_progress(progress_file, 96, "Candidate validated; awaiting coordinated publication")
        output = {
            "status": "ok" if activate_release else "candidate_ready",
            "generation": generation_id,
            "data_version": manifest["data_version"],
            "previous_generation": previous.generation_id,
            "snapshot_count": snapshot_result["snapshot_count"],
            "artifact_count": snapshot_result["artifact_count"],
            "release_version": snapshot_result["release_version"],
            "activated": activate_release,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "timings": timing.stages,
            "isolated_preparation_rss": ({
                'metadata': metadata_result['stage_process_rss_highwater_bytes'],
                'arena_records': roster_result['stage_process_rss_highwater_bytes'],
            } if isolate_stages else None),
        }
        if report_path:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return output
    except Exception as exc:
        if activated:
            manager.activate(previous.generation_id)
            if previous_snapshot_pointer is None:
                snapshot_pointer.unlink(missing_ok=True)
            else:
                snapshot_pointer_tmp = snapshot_pointer.with_suffix(".json.rollback.tmp")
                snapshot_pointer_tmp.write_bytes(previous_snapshot_pointer)
                os.replace(snapshot_pointer_tmp, snapshot_pointer)
        shutil.rmtree(snapshot_root, ignore_errors=True)
        staging_db.unlink(missing_ok=True)
        (staging / f"{generation_id}.manifest.json").unlink(missing_ok=True)
        # A failed inactive candidate is not a serving generation and should
        # not block an idempotent retry using the same generation identifier.
        if candidate_adopted and not activated:
            (generations / f"{generation_id}.duckdb").unlink(missing_ok=True)
            (generations / f"{generation_id}.manifest.json").unlink(missing_ok=True)
        raise RuntimeError(f"private refresh failed: {type(exc).__name__}") from exc
    finally:
        os.close(lock_fd)
        (private / "refresh.lock").unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_root", type=Path)
    parser.add_argument("generation")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--builder", type=Path, default=Path("/home/ascri/phase2_local_vertical_slice.py"))
    parser.add_argument("--arena-settings", type=Path, default=Path("arena/arena_settings.csv"))
    parser.add_argument("--moving-source-dir", type=Path, default=Path("phase2_private_data/moving_sources"))
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--memory-limit", default="2800MB")
    parser.add_argument('--source-memory-limit',
                        help='Separate local source-import engine budget; defaults to builder budget')
    parser.add_argument("--snapshot-chunk", type=int, default=100000)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--progress-file", type=Path)
    parser.add_argument("--incremental-source", action="store_true",
                        help="Reconcile changed game tables into a copy of the current source database")
    parser.add_argument("--defer-activation", action="store_true",
                        help="Leave the validated candidate inactive for coordinated public publication")
    parser.add_argument('--isolate-stages', action='store_true',
                        help='Release process memory between serial import, builder and snapshot stages')
    args = parser.parse_args()
    root = args.root.resolve()
    resolve = lambda value: value if value.is_absolute() else root / value
    try:
        result = refresh(
            root=root,
            source_root=args.source_root.resolve(),
            generation_id=args.generation,
            builder_path=resolve(args.builder),
            arena_settings=resolve(args.arena_settings),
            moving_source_dir=resolve(args.moving_source_dir),
            threads=args.threads,
            memory_limit=args.memory_limit,
            source_memory_limit=args.source_memory_limit,
            snapshot_chunk=args.snapshot_chunk,
            report_path=resolve(args.report) if args.report else None,
            progress_file=resolve(args.progress_file) if args.progress_file else None,
            incremental_source=args.incremental_source,
            activate_release=not args.defer_activation,
            isolate_stages=args.isolate_stages,
        )
    except Exception as exc:
        if args.report:
            error_path = resolve(args.report)
            error_path.parent.mkdir(parents=True, exist_ok=True)
            error_path.write_text(
                json.dumps({
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(),
                }, indent=2
                ) + "\n",
                encoding="utf-8",
            )
        raise
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
