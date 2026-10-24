"""DuckDB request serving and immutable generation-activation primitives.

This module is the analytical service behind the VM API. It provides the
testable contract used by the HTTP service and refresh workflow:

* generations are immutable files plus a manifest;
* one tiny pointer identifies the active generation;
* pointer changes are atomic and serialized across processes;
* readers pin a generation for the lifetime of their read-only connection;
* rollback is a pointer operation and never mutates a database.

Serving-code changes do not mutate or activate a generation. A repaired build
must pass the release gates and be explicitly published before it can replace
the current public generation.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import sys
import threading
import time
import uuid
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from phase4_local_routes import (
    SIMPLE_METRIC_FAMILY_ROUTES,
    endgames_general_sql,
    maps_metrics_sql,
    _next_route_sql,
    _remaining_route_sql,
    _final_route_sql,
    _simple_metric_sql,
    scoring_sql,
    MAPS,
    PLAYERS_METRICS,
    PLAYERS_MONEY_FIELDS,
)
from phase4_local_scope import normalize_scope, scope_predicates
from phase3_cards_pair_contracts import cards_pair_sql
from phase4_combo_mw_contracts import (
    EXCLUDED_PROJECTS, _quoted, _round_clause,
    combination_sql, component_ci_sql, component_row_key,
)


GENERATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
POINTER_SCHEMA_VERSION = 1
# Keep population and payload-shape changes in the cache identity so stale
# responses cannot live across a serving-code deployment.
RESPONSE_CACHE_SCHEMA_VERSION = 18
PUBLIC_CONTRACT_SCHEMA_VERSION = 4
EXCLUDED_SUMMARY_PROJECTS = frozenset({
    "reptiles", "europe", "predators", "americas", "australia",
    "birds", "sea animals", "africa", "herbivores", "asia",
    "primates", "habitat diversity", "species diversity",
})


class ServingStateError(RuntimeError):
    """Raised when a generation or activation pointer is not usable."""


class UnsupportedRouteError(ServingStateError):
    """Raised when a recognized dashboard route has no executable adapter."""


class QueryDeadlineExceeded(ServingStateError):
    """Raised when DuckDB is interrupted at the configured serving deadline."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_safe(value: Any) -> Any:
    """Convert DuckDB date/time scalars into public JSON values."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _beta_continued_fraction(a: float, b: float, x: float) -> float:
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) >= 1e-300 else 1e-300)
    result = d
    for iteration in range(1, 201):
        m2 = 2 * iteration
        aa = iteration * (b - iteration) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d; d = 1.0 / (d if abs(d) >= 1e-300 else 1e-300)
        c = 1.0 + aa / c; c = c if abs(c) >= 1e-300 else 1e-300
        result *= d * c
        aa = -(a + iteration) * (qab + iteration) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d; d = 1.0 / (d if abs(d) >= 1e-300 else 1e-300)
        c = 1.0 + aa / c; c = c if abs(c) >= 1e-300 else 1e-300
        delta = d * c; result *= delta
        if abs(delta - 1.0) < 3e-14:
            break
    return result


def _regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    if x <= 0: return 0.0
    if x >= 1: return 1.0
    term = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                    + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return term * _beta_continued_fraction(a, b, x) / a
    return 1.0 - term * _beta_continued_fraction(b, a, 1.0 - x) / b


def _student_t_cdf(value: float, degrees_freedom: int) -> float:
    if value == 0: return 0.5
    x = degrees_freedom / (degrees_freedom + value * value)
    tail = 0.5 * _regularized_incomplete_beta(degrees_freedom / 2.0, 0.5, x)
    return 1.0 - tail if value > 0 else tail


@lru_cache(maxsize=200)
def _t_critical_95(degrees_freedom: int) -> float | None:
    degrees_freedom = int(degrees_freedom)
    if degrees_freedom < 1: return None
    if degrees_freedom > 200: return 1.959963984540054
    low, high = 0.0, 16.0
    for _ in range(70):
        midpoint = (low + high) / 2.0
        if _student_t_cdf(midpoint, degrees_freedom) < 0.975: low = midpoint
        else: high = midpoint
    return (low + high) / 2.0


def _ordinary_ci(mean: Any, sd: Any, count: Any) -> tuple[Any, Any]:
    try:
        mean_value = float(mean)
        sd_value = float(sd)
        n_value = int(count)
    except (TypeError, ValueError):
        return None, None
    if n_value < 2 or not math.isfinite(mean_value) or not math.isfinite(sd_value):
        return None, None
    margin = _t_critical_95(n_value - 1) * sd_value / math.sqrt(n_value)
    return mean_value - margin, mean_value + margin


def _account_summary(
    alias: str, raw_counts: Any, *, player_identity: str = ""
) -> dict[str, Any]:
    counts = []
    for item in raw_counts or []:
        if not isinstance(item, Mapping):
            continue
        counts.append({
            "name": str(item.get("name") or ""),
            "game_count": int(item.get("game_count") or 0),
        })
    selected = next(
        (item["game_count"] for item in counts if item["name"].casefold() == alias.casefold()),
        0,
    )
    total = sum(item["game_count"] for item in counts)
    return {
        "name": alias,
        "game_count": total,
        "selected_game_count": selected,
        "associated_game_count": total - selected,
        # Identity membership is global metadata.  The current filter scope may
        # contain games for only one of several associated aliases, so the
        # scoped account-count list is not a reliable merged-identity flag.
        "is_merged": player_identity.startswith("merge:") or len(counts) > 1,
    }


def _project_players_general(rows: list[dict[str, Any]], request: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    alias = str(request.get("players_player") or "")
    raw_counts = rows[0].get("account_counts") if rows else []
    player_identity = str(rows[0].get("player_identity") or "") if rows else ""
    summary = _account_summary(
        alias, raw_counts, player_identity=player_identity
    )
    projected = []
    for row in rows:
        item = dict(row)
        item.pop("account_counts", None)
        item.pop("player_identity", None)
        projected.append(item)
    return projected, {
        "players_players": [],
        "player_game_count": summary["game_count"],
        "player_selected_game_count": summary["selected_game_count"],
        "player_associated_game_count": summary["associated_game_count"],
        "player_is_merged": summary["is_merged"],
    }


def _project_players_comparison(rows: list[dict[str, Any]], request: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    aliases = list(request.get("players_players") or [])
    by_metric: dict[tuple[Any, ...], dict[str, Any]] = {}
    identities: dict[str, str] = {}
    summaries: dict[str, dict[str, Any]] = {}
    for source in rows:
        alias = str(source.get("player") or "")
        identity = str(source.get("player_identity") or "")
        prior = identities.get(identity)
        if identity and prior and prior != alias:
            raise ValueError("Selected comparison players belong to the same merged player identity")
        if identity:
            identities[identity] = alias
        summaries.setdefault(
            alias,
            _account_summary(
                alias, source.get("account_counts"), player_identity=identity
            ),
        )
        key = (
            source.get("sort_order"), source.get("metric"), source.get("tooltip"),
            source.get("is_default"), source.get("format"), source.get("lower_is_better"),
        )
        target = by_metric.setdefault(key, {
            "sort_order": source.get("sort_order"), "metric": source.get("metric"),
            "tooltip": source.get("tooltip"), "is_default": bool(source.get("is_default")),
            "format": source.get("format"),
            "lower_is_better": bool(source.get("lower_is_better")), "values": [],
        })
        target["values"].append({
            "player": alias, "value": source.get("value"),
            "tooltip_value": source.get("tooltip_value"),
            "game_count": int(source.get("game_count") or 0),
        })
    projected = sorted(by_metric.values(), key=lambda item: int(item.get("sort_order") or 0))
    ordered_summaries = [summaries.get(alias, _account_summary(alias, [])) for alias in aliases]
    return projected, {"players_players": aliases, "players": ordered_summaries}


def _project_players_performance(rows: list[dict[str, Any]], request: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    aliases = list(request.get("players_players") or [])
    by_alias = {
        alias: {"sort_order": index, "player": alias}
        for index, alias in enumerate(aliases)
    }
    map_keys = {full: f"map_{code.lower()}" for code, full in MAPS}
    for source in rows:
        alias = str(source.get("player") or "")
        map_key = map_keys.get(source.get("map_name"))
        if alias not in by_alias or not map_key:
            continue
        target = by_alias[alias]
        mean = source.get("value")
        count = int(source.get("ci_n") or 0)
        low, high = _ordinary_ci(mean, source.get("ci_sd"), count)
        target[map_key] = mean
        target[f"count_{map_key}"] = count
        target[f"{map_key}_ci95_mean"] = source.get("ci_mean")
        target[f"{map_key}_ci95_sd"] = source.get("ci_sd")
        target[f"{map_key}_ci95_n"] = count
        target[f"{map_key}_ci95_low"] = low
        target[f"{map_key}_ci95_high"] = high
    return [by_alias[alias] for alias in aliases], {"players_players": aliases}


def _players_history_catalog(keys: Sequence[str]) -> list[dict[str, Any]]:
    definitions = {item[0]: item for item in PLAYERS_METRICS}
    groups = {
        **{key: "upgrade_percentages" for key in ("animals_pct", "association_pct", "build_pct", "cards_pct", "sponsors_pct")},
        **{key: "action_counts" for key in ("animals_actions", "association_actions", "build_actions", "cards_actions", "sponsors_actions")},
        **{key: "association_bonuses" for key in ("universities", "partner_zoos", "reputation_actions")},
        **{key: "x_tokens" for key in ("x_tokens_gained", "x_tokens_spent")},
        **{key: "small_buildings" for key in ("kiosks", "pavilions")},
        **{key: "icons" for key in (
            "bird_icons", "herbivore_icons", "predator_icons", "primate_icons",
            "reptile_icons", "sea_animal_icons", "bear_icons", "petting_zoo_icons",
            "africa_icons", "america_icons", "asia_icons", "australia_icons",
            "europe_icons", "rock_icons", "water_icons", "science_icons",
        )},
    }
    result = []
    for key in keys:
        if key == "elo":
            result.append({"key": "elo", "sort_order": 0, "label": "Elo", "format": "number", "group": "elo"})
            continue
        item = definitions[key]
        result.append({
            "key": key, "sort_order": int(item[1]), "label": item[2],
            "format": item[5], "group": groups.get(key, f"metric:{key}"),
        })
    return result


def _project_players_history(rows: list[dict[str, Any]], request: Mapping[str, Any]) -> dict[str, Any]:
    aliases = list(request.get("history_aliases") or [])
    metrics = list(request.get("players_history_metrics") or [])
    by_alias: dict[str, list[dict[str, Any]]] = {alias: [] for alias in aliases}
    for row in rows:
        alias = str(row.get("requested_player") or "")
        if alias in by_alias:
            by_alias[alias].append(row)
    players = []
    for alias in aliases:
        points = by_alias[alias]
        game_count = int(points[0].get("game_count") or 0) if points else 0
        if game_count < 250:
            message = (
                "Minimum game count: 250"
                if request.get("players_view") == "general"
                else "Minimum game count for any player: 250"
            )
            raise ValueError(message)
        players.append({
            "name": alias, "game_count": game_count,
            "game_numbers": [int(point.get("game_number") or 0) for point in points],
            "timestamps": [_json_safe(point.get("game_ended_at")) for point in points],
            "series": {key: [point.get(key) for point in points] for key in metrics},
        })
    return {
        "players_history": True, "players_view": request.get("players_view"),
        "window_size": 100, "metrics": _players_history_catalog(metrics),
        "players": players,
    }


class Phase3AuditLog:
    """Small secret-free JSONL audit log for private serving diagnostics."""

    _ALLOWED_FIELDS = {
        "generation", "data_version", "previous_generation", "view",
        "request_fingerprint", "cache_status", "duration_ms", "row_count",
        "error_type", "ready", "rollback_ready",
    }

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def emit(self, event: str, **fields: Any) -> None:
        record: dict[str, Any] = {
            "timestamp": _utc_now(),
            "event": str(event),
        }
        for key in self._ALLOWED_FIELDS:
            if key in fields and fields[key] is not None:
                record[key] = fields[key]
        line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        with self._lock:
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line)
                handle.flush()

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit must be positive")
        if not self.path.exists():
            return []
        records = []
        for line in self.path.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                records.append(item)
        return records


def _load_duckdb():
    """Load DuckDB from the configured native-extension bundle or environment."""

    configured = os.environ.get("DUCKDB_PYTHON_PATH")
    candidates = []
    if configured:
        candidates.append(Path(configured))
    private_root = Path(__file__).resolve().parent / "phase2_private_data"
    candidates.extend((private_root / "python314", private_root / "python"))
    for candidate in candidates:
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
    try:
        import duckdb
    except ImportError as exc:  # pragma: no cover - environment-specific
        raise ServingStateError(
            "DuckDB is not installed; set DUCKDB_PYTHON_PATH for the private bundle"
        ) from exc
    return duckdb


@dataclass(frozen=True)
class Generation:
    generation_id: str
    database_path: Path
    manifest_path: Path
    manifest: Mapping[str, Any]

    @property
    def data_version(self) -> str | None:
        # Metadata-only generations wrap a source-data generation. Their
        # serving/cache identity must remain the source data version, not the
        # wrapper generation ID, otherwise same-data snapshots look stale.
        value = self.manifest.get("data_version") or self.manifest.get("parent_generation")
        if value is None:
            value = self.manifest.get("generation")
        return str(value) if value is not None else None


class GenerationManager:
    """Manage immutable local generations through an atomic active pointer."""

    def __init__(
        self,
        generations_dir: str | Path,
        pointer_path: str | Path | None = None,
        lock_path: str | Path | None = None,
        lock_timeout_seconds: float = 15.0,
        stale_lock_after_seconds: float = 300.0,
        audit_log: Phase3AuditLog | None = None,
    ) -> None:
        self.generations_dir = Path(generations_dir).resolve()
        self.generations_dir.mkdir(parents=True, exist_ok=True)
        self.pointer_path = Path(pointer_path or self.generations_dir.parent / "current.json")
        self.pointer_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = Path(lock_path or self.pointer_path.with_suffix(".lock"))
        self.lock_timeout_seconds = float(lock_timeout_seconds)
        self.stale_lock_after_seconds = float(stale_lock_after_seconds)
        self.audit_log = audit_log
        self._thread_lock = threading.RLock()

    def _audit(self, event: str, **fields: Any) -> None:
        if self.audit_log is None:
            return
        try:
            self.audit_log.emit(event, **fields)
        except OSError:
            # Diagnostics must never make a valid generation unavailable.
            pass

    @staticmethod
    def _validate_id(generation_id: str) -> str:
        if not isinstance(generation_id, str) or not GENERATION_RE.fullmatch(generation_id):
            raise ServingStateError(f"invalid generation id: {generation_id!r}")
        return generation_id

    def _default_paths(self, generation_id: str) -> tuple[Path, Path]:
        return (
            self.generations_dir / f"{generation_id}.duckdb",
            self.generations_dir / f"{generation_id}.manifest.json",
        )

    def inspect(
        self,
        generation_id: str,
        database_path: str | Path | None = None,
        manifest_path: str | Path | None = None,
    ) -> Generation:
        generation_id = self._validate_id(generation_id)
        default_database, default_manifest = self._default_paths(generation_id)
        db_path = Path(database_path or default_database).resolve()
        mf_path = Path(manifest_path or default_manifest).resolve()
        if not db_path.is_file() or db_path.stat().st_size <= 0:
            raise ServingStateError(f"generation database is missing or empty: {db_path}")
        if not mf_path.is_file():
            raise ServingStateError(f"generation manifest is missing: {mf_path}")
        try:
            manifest = json.loads(mf_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ServingStateError(f"cannot read generation manifest: {mf_path}") from exc
        if not isinstance(manifest, dict):
            raise ServingStateError(f"generation manifest must be an object: {mf_path}")
        manifest_generation = manifest.get("generation")
        if manifest_generation is not None and manifest_generation != generation_id:
            raise ServingStateError(
                f"manifest generation mismatch: expected {generation_id}, got {manifest_generation}"
            )
        if manifest.get("status") not in (None, "ok"):
            raise ServingStateError(
                f"generation manifest is not publishable: {manifest.get('status')}"
            )
        return Generation(generation_id, db_path, mf_path, manifest)

    def stage(
        self,
        generation_id: str,
        source_database: str | Path,
        source_manifest: str | Path,
    ) -> Generation:
        """Copy and validate an immutable candidate without activating it."""

        generation_id = self._validate_id(generation_id)
        source_db = Path(source_database).resolve()
        source_mf = Path(source_manifest).resolve()
        if not source_db.is_file() or source_db.stat().st_size <= 0:
            raise ServingStateError(f"source database is missing or empty: {source_db}")
        if not source_mf.is_file():
            raise ServingStateError(f"source manifest is missing: {source_mf}")
        try:
            manifest = json.loads(source_mf.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ServingStateError(f"cannot read source manifest: {source_mf}") from exc
        if not isinstance(manifest, dict) or manifest.get("generation") not in (None, generation_id):
            raise ServingStateError("source manifest generation does not match candidate")
        if manifest.get("status") not in (None, "ok"):
            raise ServingStateError("source manifest is not publishable")
        target_db, target_mf = self._default_paths(generation_id)
        if target_db.exists() or target_mf.exists():
            raise ServingStateError(f"generation already exists: {generation_id}")
        token = uuid.uuid4().hex
        temp_db = self.generations_dir / f".{generation_id}.{token}.staging.duckdb"
        temp_mf = self.generations_dir / f".{generation_id}.{token}.staging.manifest.json"
        database_published = False
        try:
            shutil.copyfile(source_db, temp_db)
            with temp_db.open("r+b") as handle:
                os.fsync(handle.fileno())
            staged_manifest = dict(manifest)
            staged_manifest["generation"] = generation_id
            staged_manifest["database"] = str(target_db)
            staged_manifest["staged_at"] = _utc_now()
            temp_mf.write_text(
                json.dumps(staged_manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with temp_mf.open("r+b") as handle:
                os.fsync(handle.fileno())
            os.replace(temp_db, target_db)
            database_published = True
            os.replace(temp_mf, target_mf)
        except OSError as exc:
            if database_published and not target_mf.exists():
                try:
                    target_db.unlink()
                except OSError:
                    pass
            raise ServingStateError(f"could not stage generation {generation_id}") from exc
        finally:
            for temporary in (temp_db, temp_mf):
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass
        return self.inspect(generation_id)

    def adopt_existing(
        self,
        generation_id: str,
        source_database: str | Path,
        source_manifest: str | Path,
    ) -> Generation:
        """Stage a completed same-filesystem candidate without duplicating it.

        Large private DuckDB generations are built in the staging directory on
        the same filesystem as ``generations``.  Moving that completed file is
        atomic and avoids requiring a second full database-sized copy during
        publication.  The normal ``stage`` method remains the safer default
        for arbitrary source paths.
        """
        generation_id = self._validate_id(generation_id)
        source_db = Path(source_database).resolve()
        source_mf = Path(source_manifest).resolve()
        if not source_db.is_file() or source_db.stat().st_size <= 0:
            raise ServingStateError(f"source database is missing or empty: {source_db}")
        if not source_mf.is_file():
            raise ServingStateError(f"source manifest is missing: {source_mf}")
        try:
            manifest = json.loads(source_mf.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ServingStateError(f"cannot read source manifest: {source_mf}") from exc
        if not isinstance(manifest, dict) or manifest.get("generation") not in (None, generation_id):
            raise ServingStateError("source manifest generation does not match candidate")
        if manifest.get("status") not in (None, "ok"):
            raise ServingStateError("source manifest is not publishable")
        target_db, target_mf = self._default_paths(generation_id)
        if target_db.exists() or target_mf.exists():
            raise ServingStateError(f"generation already exists: {generation_id}")
        staged_manifest = dict(manifest)
        staged_manifest["generation"] = generation_id
        staged_manifest["database"] = str(target_db)
        staged_manifest["staged_at"] = _utc_now()
        database_published = False
        try:
            with source_db.open("r+b") as handle:
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(source_db, target_db)
            database_published = True
            temp_mf = target_mf.with_name(f".{target_mf.name}.{uuid.uuid4().hex}.tmp")
            try:
                temp_mf.write_text(json.dumps(staged_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                with temp_mf.open("r+b") as handle:
                    os.fsync(handle.fileno())
                os.replace(temp_mf, target_mf)
            finally:
                temp_mf.unlink(missing_ok=True)
        except OSError as exc:
            if database_published and not target_mf.exists():
                target_db.unlink(missing_ok=True)
            raise ServingStateError(f"could not adopt generation {generation_id}") from exc
        return self.inspect(generation_id)

    def stage_and_activate(
        self,
        generation_id: str,
        source_database: str | Path,
        source_manifest: str | Path,
    ) -> Generation:
        """Stage a candidate and move the active pointer only after validation."""

        candidate = self.stage(generation_id, source_database, source_manifest)
        return self.activate(candidate.generation_id)

    def _read_pointer(self) -> dict[str, Any] | None:
        if not self.pointer_path.exists():
            return None
        try:
            pointer = json.loads(self.pointer_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ServingStateError(f"cannot read activation pointer: {self.pointer_path}") from exc
        if not isinstance(pointer, dict) or pointer.get("schema_version") != POINTER_SCHEMA_VERSION:
            raise ServingStateError("activation pointer schema is unsupported")
        self._validate_id(pointer.get("generation"))
        return pointer

    def current(self) -> Generation | None:
        pointer = self._read_pointer()
        if pointer is None:
            return None
        return self.inspect(pointer["generation"])

    @contextmanager
    def _activation_lock(self) -> Iterator[None]:
        deadline = time.monotonic() + self.lock_timeout_seconds
        with self._thread_lock:
            fd = None
            while fd is None:
                try:
                    fd = os.open(
                        self.lock_path,
                        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    )
                    os.write(fd, f"pid={os.getpid()}\n".encode("ascii"))
                except FileExistsError:
                    try:
                        age = time.time() - self.lock_path.stat().st_mtime
                        if age > self.stale_lock_after_seconds:
                            self.lock_path.unlink()
                            continue
                    except FileNotFoundError:
                        continue
                    if time.monotonic() >= deadline:
                        raise ServingStateError("timed out waiting for generation activation lock")
                    time.sleep(0.05)
            try:
                yield
            finally:
                os.close(fd)
                try:
                    self.lock_path.unlink()
                except FileNotFoundError:
                    pass

    def _write_pointer(self, pointer: Mapping[str, Any]) -> None:
        temp_path = self.pointer_path.with_name(
            f".{self.pointer_path.name}.{uuid.uuid4().hex}.tmp"
        )
        payload = json.dumps(pointer, indent=2, sort_keys=True) + "\n"
        try:
            with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.pointer_path)
        finally:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass

    def activate(
        self,
        generation_id: str,
        database_path: str | Path | None = None,
        manifest_path: str | Path | None = None,
    ) -> Generation:
        self._audit("generation_activation_started", generation=generation_id)
        try:
            candidate = self.inspect(generation_id, database_path, manifest_path)
        except Exception as exc:
            self._audit(
                "generation_activation_failed",
                generation=generation_id,
                error_type=type(exc).__name__,
            )
            raise
        try:
            with self._activation_lock():
                existing_pointer = self._read_pointer()
                if existing_pointer and existing_pointer["generation"] == generation_id:
                    self._audit(
                        "generation_activation_unchanged",
                        generation=generation_id,
                        data_version=candidate.data_version,
                    )
                    return candidate
                pointer = {
                    "schema_version": POINTER_SCHEMA_VERSION,
                    "generation": generation_id,
                    "activated_at": _utc_now(),
                    "previous_generation": (
                        existing_pointer.get("generation") if existing_pointer else None
                    ),
                }
                self._write_pointer(pointer)
        except Exception as exc:
            self._audit(
                "generation_activation_failed",
                generation=generation_id,
                error_type=type(exc).__name__,
            )
            raise
        self._audit(
            "generation_activated",
            generation=candidate.generation_id,
            data_version=candidate.data_version,
            previous_generation=pointer["previous_generation"],
        )
        return candidate

    def rollback(self, generation_id: str | None = None) -> Generation:
        self._audit("generation_rollback_started", generation=generation_id)
        try:
            with self._activation_lock():
                existing_pointer = self._read_pointer()
                if existing_pointer is None:
                    raise ServingStateError("cannot roll back without an active generation")
                target_id = generation_id or existing_pointer.get("previous_generation")
                if not target_id:
                    raise ServingStateError("no previous generation is available for rollback")
                target = self.inspect(target_id)
                pointer = {
                    "schema_version": POINTER_SCHEMA_VERSION,
                    "generation": target.generation_id,
                    "activated_at": _utc_now(),
                    "previous_generation": existing_pointer.get("generation"),
                }
                self._write_pointer(pointer)
        except Exception as exc:
            self._audit(
                "generation_rollback_failed",
                generation=generation_id,
                error_type=type(exc).__name__,
            )
            raise
        self._audit(
            "generation_rolled_back",
            generation=target.generation_id,
            data_version=target.data_version,
            previous_generation=pointer["previous_generation"],
        )
        return target

    def status(self) -> dict[str, Any]:
        pointer = self._read_pointer()
        if pointer is None:
            return {"state": "empty", "pointer": str(self.pointer_path)}
        generation = self.current()
        assert generation is not None
        return {
            "state": "active",
            "generation": generation.generation_id,
            "data_version": generation.data_version,
            "database": str(generation.database_path),
            "manifest": str(generation.manifest_path),
            "activated_at": pointer.get("activated_at"),
            "previous_generation": pointer.get("previous_generation"),
        }

    def readiness(self) -> dict[str, Any]:
        """Validate the active generation and whether rollback is available."""

        pointer = self._read_pointer()
        if pointer is None:
            result = {
                "ready": False,
                "rollback_ready": False,
                "state": "empty",
            }
            self._audit("readiness_checked", **result)
            return result
        active_valid = False
        rollback_valid = False
        active = None
        try:
            active = self.inspect(pointer["generation"])
            active_valid = True
        except ServingStateError:
            pass
        previous_id = pointer.get("previous_generation")
        if previous_id:
            try:
                self.inspect(previous_id)
                rollback_valid = True
            except ServingStateError:
                pass
        result = {
            "ready": active_valid,
            "rollback_ready": rollback_valid,
            "state": "active" if active_valid else "invalid",
        }
        if active is not None:
            result.update(
                generation=active.generation_id,
                data_version=active.data_version,
            )
        self._audit("readiness_checked", **result)
        return result


class DuckDBServingStore:
    """Read-only query facade that pins each connection to one generation."""

    def __init__(
        self,
        manager: GenerationManager,
        generation_id: str | None = None,
        query_timeout_seconds: float | None = None,
        memory_limit: str | None = None,
    ) -> None:
        self.manager = manager
        # Snapshot and release validation must be able to query an immutable
        # candidate without changing the public serving pointer. Interactive
        # callers leave this unset and continue to follow the active pointer.
        self.generation_id = generation_id
        if query_timeout_seconds is not None and query_timeout_seconds <= 0:
            raise ValueError("query_timeout_seconds must be positive")
        self.query_timeout_seconds = query_timeout_seconds
        self.memory_limit = memory_limit

    def generation(self) -> Generation | None:
        if self.generation_id is not None:
            return self.manager.inspect(self.generation_id)
        return self.manager.current()

    @contextmanager
    def connection(self) -> Iterator[tuple[Generation, Any]]:
        generation = self.generation()
        if generation is None:
            raise ServingStateError("no active DuckDB generation")
        duckdb = _load_duckdb()
        connection = duckdb.connect(str(generation.database_path), read_only=True)
        # The private serving VM has two vCPUs. Use a shared two-thread
        # execution pool for the wide aggregate routes and simultaneous reads;
        # this is not two additional threads per request. The setting remains
        # configurable for smaller test machines.
        try:
            serving_threads = max(1, int(os.environ.get("DUCKDB_SERVING_THREADS", "2")))
        except ValueError:
            serving_threads = 2
        connection.execute(f"SET threads={serving_threads}")
        # DuckDB memory_limit and threads are GLOBAL to the database instance,
        # not per-connection reservations. Concurrent connections to this path
        # share the budget. It bounds the buffer manager, not total process RSS;
        # the real mixed-refresh gate must also measure OS memory headroom.
        memory_limit = (self.memory_limit or os.environ.get("DUCKDB_SERVING_MEMORY_LIMIT", "1300MB")).strip()
        if not re.fullmatch(r"[1-9][0-9]*(?:\.[0-9]+)?\s*(?:KB|MB|GB|KiB|MiB|GiB)", memory_limit, re.I):
            raise ServingStateError("invalid DUCKDB_SERVING_MEMORY_LIMIT")
        connection.execute("SET memory_limit = ?", [memory_limit])
        connection.execute("SET preserve_insertion_order=false")
        try:
            yield generation, connection
        finally:
            connection.close()

    @staticmethod
    def _validate_read_query(sql: str) -> str:
        if not isinstance(sql, str) or not sql.strip():
            raise ValueError("a read query is required")
        normalized = sql.strip()
        if ";" in normalized.rstrip(";"):
            raise ValueError("multiple SQL statements are not allowed")
        if not normalized.lower().startswith(("select", "with", "pragma")):
            raise ValueError("serving store accepts read-only SQL only")
        return normalized

    @contextmanager
    def _read_cursor(
        self,
        sql: str,
        parameters: Sequence[Any] | Mapping[str, Any] | None = None,
    ):
        """Pin the generation and enforce one deadline through cursor consumption."""
        sql = self._validate_read_query(sql)
        with self.connection() as (generation, connection):
            try:
                timeout_seconds = (
                    self.query_timeout_seconds
                    if self.query_timeout_seconds is not None
                    else max(1.0, float(os.environ.get("DUCKDB_QUERY_TIMEOUT_SECONDS", "90")))
                )
            except ValueError as exc:
                raise ServingStateError("invalid DUCKDB_QUERY_TIMEOUT_SECONDS") from exc
            expired = threading.Event()

            def interrupt() -> None:
                expired.set()
                connection.interrupt()

            timer = threading.Timer(timeout_seconds, interrupt)
            timer.daemon = True
            timer.start()
            try:
                cursor = connection.execute(sql, parameters or ())
                yield generation, cursor
            except Exception as exc:
                if expired.is_set():
                    raise QueryDeadlineExceeded(
                        f"analytical query exceeded {timeout_seconds:g} seconds"
                    ) from exc
                raise
            finally:
                timer.cancel()

    def query(
        self, sql: str,
        parameters: Sequence[Any] | Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._read_cursor(sql, parameters) as (generation, cursor):
            columns = [item[0] for item in cursor.description or ()]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return {"generation": generation.generation_id,
                    "data_version": generation.data_version,
                    "columns": columns, "rows": rows}

    @contextmanager
    def query_batches(self, sql: str, parameters=None, *, batch_size: int = 1024):
        """Trusted offline iterator; one query and one bounded tuple batch at a time.

        The context owns the cursor, timer and generation connection. Callers
        must consume the iterator inside it; early exit still closes everything.
        This is not a public request option or an increase to live page limits.
        """
        if not 1 <= batch_size <= 10000:
            raise ValueError("offline batch size must be between 1 and 10000")
        with self._read_cursor(sql, parameters) as (generation, cursor):
            columns = [item[0] for item in cursor.description or ()]

            def batches():
                while batch := cursor.fetchmany(batch_size):
                    yield (dict(zip(columns, row)) for row in batch)

            yield generation, batches()

    def health(self) -> dict[str, Any]:
        if self.generation_id is not None:
            generation = self.manager.inspect(self.generation_id)
            result = self.query("SELECT 1 AS ready")
            return {
                "state": "candidate",
                "generation": generation.generation_id,
                "data_version": generation.data_version,
                "ready": bool(result["rows"] and result["rows"][0]["ready"] == 1),
            }
        status = self.manager.status()
        if status["state"] == "empty":
            return {**status, "ready": False}
        result = self.query("SELECT 1 AS ready")
        return {
            **status,
            "ready": bool(result["rows"] and result["rows"][0]["ready"] == 1),
        }


class Phase3PersistentResponseCache:
    """SQLite-backed response cache shared by local API processes."""

    def __init__(self, database_path: str | Path, max_items: int = 512) -> None:
        if max_items < 1:
            raise ValueError("max_items must be positive")
        self.database_path = Path(database_path).resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_items = int(max_items)
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS phase3_responses (
                  cache_key TEXT PRIMARY KEY,
                  generation TEXT NOT NULL,
                  data_version TEXT,
                  created_at REAL NOT NULL,
                  payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS phase3_responses_created_idx
                  ON phase3_responses(created_at);
                """
            )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(str(self.database_path), timeout=5.0)
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get(self, key: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload FROM phase3_responses WHERE cache_key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row[0])
        except (TypeError, json.JSONDecodeError):
            return None
        return dict(payload) if isinstance(payload, dict) else None

    def put(self, key: str, value: Mapping[str, Any]) -> None:
        payload = json.dumps(dict(value), sort_keys=True, separators=(",", ":"))
        generation = str(value.get("generation") or "")
        data_version = value.get("data_version")
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO phase3_responses
                  (cache_key, generation, data_version, created_at, payload)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                  generation = excluded.generation,
                  data_version = excluded.data_version,
                  created_at = excluded.created_at,
                  payload = excluded.payload
                """,
                (key, generation, data_version, time.time(), payload),
            )
            connection.execute(
                """
                DELETE FROM phase3_responses
                WHERE cache_key IN (
                  SELECT cache_key FROM phase3_responses
                  ORDER BY created_at DESC
                  LIMIT -1 OFFSET ?
                )
                """,
                (self.max_items,),
            )


class Phase3ResponseCache:
    """Byte-bounded immutable JSON cache with generation-scoped SQLite fallback.

    The budget bounds retained serialized payload bytes, not the entire API
    process or transient query/JSON decoding allocations. Each get returns a
    new object, preserving caller mutation isolation without a second deep copy.
    """

    def __init__(
        self,
        max_items: int = 128,
        persistent: Phase3PersistentResponseCache | None = None,
        max_bytes: int | None = None,
        max_entry_bytes: int | None = None,
    ) -> None:
        if max_items < 1:
            raise ValueError("max_items must be positive")
        self.max_items = int(max_items)
        self.max_bytes = int(max_bytes if max_bytes is not None else
                             os.environ.get("PHASE3_RESPONSE_CACHE_MAX_BYTES", 32 * 1024 ** 2))
        self.max_entry_bytes = int(max_entry_bytes if max_entry_bytes is not None else
                                   os.environ.get("PHASE3_RESPONSE_CACHE_MAX_ENTRY_BYTES", 8 * 1024 ** 2))
        if self.max_bytes < 0 or self.max_entry_bytes < 0:
            raise ValueError("cache byte limits must be nonnegative")
        self._items: OrderedDict[str, bytes] = OrderedDict()
        self._bytes = 0
        self._lock = threading.RLock()
        self.persistent = persistent

    @staticmethod
    def key_for(generation: Generation, normalized_request: Mapping[str, Any]) -> str:
        identity = {
            "cache_schema": RESPONSE_CACHE_SCHEMA_VERSION,
            "generation": generation.generation_id,
            "data_version": generation.data_version,
            "request": normalized_request,
        }
        encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        return f"phase3/{generation.data_version or generation.generation_id}/{digest}"

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            value = self._items.get(key)
        if value is not None:
            return json.loads(value)
        if self.persistent is not None:
            value = self.persistent.get(key)
            if value is not None:
                self._remember(key, value)
                # SQLite already decoded a new, caller-owned object.
                return value
        return None

    def _remember(self, key: str, value: Mapping[str, Any]) -> None:
        encoded = json.dumps(dict(value), ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")
        with self._lock:
            previous = self._items.pop(key, None)
            if previous is not None:
                self._bytes -= len(previous)
            if len(encoded) > min(self.max_bytes, self.max_entry_bytes):
                return
            self._items[key] = encoded
            self._bytes += len(encoded)
            while len(self._items) > self.max_items or self._bytes > self.max_bytes:
                _, oldest = self._items.popitem(last=False)
                self._bytes -= len(oldest)

    def put(self, key: str, value: Mapping[str, Any]) -> None:
        self._remember(key, value)
        if self.persistent is not None:
            self.persistent.put(key, value)


PHASE3_PAGE_CATALOG: dict[str, tuple[str, ...]] = {
    "home": ("default",),
    "cards": ("default", "component_ci"),
    "opening_hand": ("default",),
    "endgames": ("general", "cp_distribution", "cp_by_map"),
    "maps": ("metrics", "tournament_h2h"),
    "sponsor_endgames": ("cp", "appeal"),
    "combinations": (
        "card_card", "card_map", "card_round", "card_endgame",
        "card_action_card",
    ),
    "icons": ("default",),
    "build": ("enclosures", "hexes"),
    "predictors": ("general", "icon", "specific"),
    "actions": ("starting_position", "upgrades", "upgrade_order", "upgrades_by_map"),
    "conservation": ("projects", "project_rewards", "cp_rewards"),
    "scoring": ("final_score", "appeal", "conservation_points", "reputation"),
    "workers": ("general", "two_cp_worker"),
    "players": ("general", "comparison", "performance_by_map", "arena_top_100", "history"),
    "arena": ("top_100",),
    "records": ("elo_leaderboard", "fastest_games", "highest_scores", "biggest_turns", "most_icons"),
    "mw_action_cards": ("general", "draft", "by_map", "synergies"),
}


def _combination_range(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, float] | None:
    values = []
    for row in rows:
        try:
            value = float(row.get(field))
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            values.append(value)
    return {"min": min(values), "max": max(values)} if values else None


_CARD_PAIR_TYPE_ORDER = {"animal": 0, "project": 1, "sponsor": 2}
_CARD_PAIR_TYPE_LABELS = {"animal": "Animal", "project": "Project", "sponsor": "Sponsor"}
_ACTION_CARD_TYPE_LABELS = {
    "animals": "Animals", "association": "Association", "build": "Build",
    "cards": "Cards", "sponsors": "Sponsors",
}


def _canonical_combination_pair_type(value: Any, public_view: str) -> str:
    """Normalize the public Type key shared by snapshots, filters, and rows.

    Source card types are intentionally lowercase.  The public contract uses
    title-case labels and Card + Card is unordered by type, so merely comparing
    the raw concatenated SQL value is not sufficient.
    """

    parts = [part.strip().casefold() for part in str(value or "").replace(" vs. ", " + ").split("+")]
    if len(parts) != 2 or not all(parts):
        return str(value or "").strip()
    if public_view == "card_card":
        if any(part not in _CARD_PAIR_TYPE_ORDER for part in parts):
            return str(value or "").strip()
        parts.sort(key=_CARD_PAIR_TYPE_ORDER.__getitem__)
        return " + ".join(_CARD_PAIR_TYPE_LABELS[part] for part in parts)
    if public_view == "card_action_card":
        card_type, action_type = parts
        if card_type not in _CARD_PAIR_TYPE_LABELS or action_type not in _ACTION_CARD_TYPE_LABELS:
            return str(value or "").strip()
        return f"{_CARD_PAIR_TYPE_LABELS[card_type]} + {_ACTION_CARD_TYPE_LABELS[action_type]}"
    return str(value or "").strip()


def _project_combination_rows(
    rows: list[dict[str, Any]], request: Mapping[str, Any], public_view: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Apply search, Type, Minimum, sorting, rank, and paging locally."""
    minimum = int(request.get("combination_min_plays", 1000))
    sort_field = str(request.get("combination_sort") or "interaction")
    reverse = str(request.get("combination_sort_dir") or "desc") != "asc"
    stable_fields = {
        "card_card": ("card_1", "card_2", "pair_type"),
        "card_action_card": ("card_name", "action_card_key", "pair_type"),
        "card_endgame": ("card_name", "endgame_name", "card_type"),
        "card_map": ("card_name", "map_name", "card_type"),
        "card_round": ("card_name", "round_name", "card_type"),
    }[public_view]

    def scalar(row: Mapping[str, Any], field: str) -> tuple[int, Any]:
        value = row.get(field)
        if value is None:
            return (1, "")
        return (0, float(value)) if isinstance(value, (int, float)) else (0, str(value).casefold())

    normalized_rows = [dict(row) for row in rows]
    if public_view in {"card_card", "card_action_card"}:
        for row in normalized_rows:
            row["pair_type"] = _canonical_combination_pair_type(row.get("pair_type"), public_view)
    ranked = [dict(row) for row in normalized_rows if int(row.get("n_played") or 0) >= minimum]
    ranked.sort(key=lambda row: tuple(str(row.get(field) or "").casefold() for field in stable_fields))
    ranked.sort(key=lambda row: scalar(row, sort_field), reverse=reverse)
    for index, row in enumerate(ranked, 1):
        row["global_rank"] = index

    pair_types = {
        _canonical_combination_pair_type(value, public_view)
        for value in request.get("combination_pair_types") or []
    }
    card_types = {str(value).lower() for value in request.get("combination_card_types") or []}
    primary = str(request.get("combination_primary") or "").strip()
    secondary = str(request.get("combination_secondary") or "").strip()
    header_maps = set(request.get("combination_header_maps") or [])
    header_rounds = set(request.get("combination_header_rounds") or [])

    def visible(row: Mapping[str, Any]) -> bool:
        pair_type = _canonical_combination_pair_type(row.get("pair_type"), public_view)
        if public_view in {"card_card", "card_action_card"} and pair_types and pair_type not in pair_types:
            return False
        if public_view == "card_action_card":
            return (not primary or row.get("card_name") == primary) and (not secondary or row.get("action_card_key") == secondary)
        if public_view in {"card_map", "card_round", "card_endgame"}:
            if card_types and str(row.get("card_type") or "").lower() not in card_types:
                return False
            if primary and row.get("card_name") != primary:
                return False
            if public_view == "card_endgame" and secondary and row.get("endgame_name") != secondary:
                return False
            if public_view == "card_map" and header_maps and row.get("map_name") not in header_maps:
                return False
            if public_view == "card_round" and header_rounds and row.get("round_name") not in header_rounds:
                return False
            return True
        if primary and secondary:
            return {row.get("card_1"), row.get("card_2")} == {primary, secondary}
        selected = primary or secondary
        return not selected or selected in {row.get("card_1"), row.get("card_2")}

    candidates_before_minimum = [row for row in normalized_rows if visible(row)]
    visible_rows = [row for row in ranked if visible(row)]
    ranges = {}
    for field in ("delta_1", "delta_2", "delta_card", "delta_action", "delta_general",
                  "delta_map", "delta_round", "delta_endgame", "delta_combined",
                  "delta_actual", "interaction", "avg_elo"):
        item = _combination_range(normalized_rows, field)
        if item is not None:
            ranges[field] = item
    extras: dict[str, Any] = {
        "combination_ranges": ranges,
        "combination_card_options": sorted({str(value) for row in normalized_rows for value in (row.get("card_name"), row.get("card_1"), row.get("card_2")) if value}),
        "combination_endgame_options": sorted({str(row["endgame_name"]) for row in normalized_rows if row.get("endgame_name")}),
        "combination_action_card_options": sorted({str(row["action_card_key"]) for row in normalized_rows if row.get("action_card_key")}),
    }
    if request.get("combination_paged"):
        page = int(request.get("combination_page", 1)); size = int(request.get("combination_page_size", 50))
        start = (page - 1) * size
        extras.update({
            "combination_paged": True, "combination_page": page,
            "combination_page_size": size, "total_rows": len(visible_rows),
            "candidate_count_before_minimum": len(candidates_before_minimum),
            "visible_count": len(visible_rows),
            "highest_matching_play_count": max((int(row.get("n_played") or 0) for row in candidates_before_minimum), default=0),
        })
        visible_rows = visible_rows[start:start + size]
    return visible_rows, extras

PHASE3_NATIVE_ROUTES = {
    ("cards", "default"),
    ("cards", "component_ci"),
    ("players", "history"),
    ("combinations", "card_card"),
}

PHASE4_NATIVE_ROUTES = {
    ("maps", "metrics"),
    ("endgames", "general"),
    ("endgames", "cp_distribution"),
    ("endgames", "cp_by_map"),
    ("maps", "tournament_h2h"),
    ("sponsor_endgames", "cp"),
    ("sponsor_endgames", "appeal"),
    ("predictors", "general"),
    ("predictors", "icon"),
    ("predictors", "specific"),
    ("actions", "starting_position"),
    ("conservation", "cp_rewards"),
    ("home", "default"),
    ("opening_hand", "default"),
    ("combinations", "card_map"),
    ("combinations", "card_round"),
    ("combinations", "card_endgame"),
    ("combinations", "card_action_card"),
    ("players", "general"),
    ("players", "comparison"),
    ("players", "performance_by_map"),
    ("players", "arena_top_100"),
    ("arena", "top_100"),
    ("records", "elo_leaderboard"),
    ("records", "fastest_games"),
    ("records", "highest_scores"),
    ("records", "biggest_turns"),
    ("records", "most_icons"),
    ("mw_action_cards", "general"),
    ("mw_action_cards", "draft"),
    ("mw_action_cards", "by_map"),
    ("mw_action_cards", "synergies"),
    ("scoring", "final_score"),
    ("scoring", "appeal"),
    ("scoring", "conservation_points"),
    ("scoring", "reputation"),
    ("actions", "upgrades"),
    ("actions", "upgrade_order"),
    ("actions", "upgrades_by_map"),
    ("build", "enclosures"),
    ("build", "hexes"),
    ("icons", "default"),
    ("conservation", "projects"),
    ("conservation", "project_rewards"),
    ("workers", "general"),
    ("workers", "two_cp_worker"),
}


def project_ordinary_ci_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    """Add the public 95% interval fields for ordinary EV estimates.

    Local route SQL keeps compact sufficient statistics (mean, sample standard
    deviation, and non-null count).  The public contract exposes interval
    endpoints instead.  Additive combination/Synergy intervals are not
    reconstructed here; only fields explicitly ending in ``_ci_mean`` are
    ordinary single-estimate intervals.
    """

    result = dict(row)
    for key, mean in tuple(row.items()):
        if not key.endswith("_ci_mean"):
            continue
        stem = key.removesuffix("_ci_mean")
        sd = row.get(f"{stem}_ci_sd")
        n = row.get(f"{stem}_ci_n")
        result[f"{stem}_ci95_n"] = n
        low_key = f"{stem}_ci95_low"
        high_key = f"{stem}_ci95_high"
        se_key = f"{stem}_ci95_se"
        result[se_key] = None
        try:
            numeric_n = int(n)
            numeric_mean = float(mean)
            numeric_sd = float(sd)
        except (TypeError, ValueError, OverflowError):
            result[low_key] = None
            result[high_key] = None
            continue
        if numeric_n < 2 or not all(math.isfinite(value) for value in (numeric_mean, numeric_sd)):
            result[low_key] = None
            result[high_key] = None
            continue
        margin = _t_critical_95(numeric_n - 1) * numeric_sd / math.sqrt(numeric_n)
        result[se_key] = numeric_sd / math.sqrt(numeric_n)
        result[low_key] = numeric_mean - margin
        result[high_key] = numeric_mean + margin
    return result


def _project_arena_bundle(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Convert local Arena roster rows to the dashboard's season-bundle shape."""
    fide_dp = (
        -800, -677, -589, -538, -501, -470, -444, -422, -401, -383,
        -366, -351, -336, -322, -309, -296, -284, -273, -262, -251,
        -240, -230, -220, -211, -202, -193, -184, -175, -166, -158,
        -149, -141, -133, -125, -117, -110, -102, -95, -87, -80,
        -72, -65, -57, -50, -43, -36, -29, -21, -14, -7, 0,
        7, 14, 21, 29, 36, 43, 50, 57, 65, 72,
        80, 87, 95, 102, 110, 117, 125, 133, 141, 149,
        158, 166, 175, 184, 193, 202, 211, 220, 230, 240,
        251, 262, 273, 284, 296, 309, 322, 336, 351, 366,
        383, 401, 422, 444, 470, 501, 538, 589, 677, 800,
    )

    def performance_rating(row: Mapping[str, Any]) -> int | None:
        score = row.get("arena_score_rate")
        opponent = row.get("pr_opponent_elo")
        if score is None or opponent is None:
            return None
        percentage = max(0, min(100, int(math.floor(float(score) * 100 + 0.5))))
        return int(round(float(opponent) + fide_dp[percentage]))

    seasons: dict[str, dict[str, Any]] = {}
    for row in rows:
        season = str(row.get("season") or "")
        if not season:
            continue
        bucket = seasons.setdefault(season, {
            "season": season,
            "number": row.get("number"),
            "mode": row.get("mode"),
            "is_mw": row.get("is_mw") if row.get("is_mw") is not None else int(str(row.get("mode") or "").lower() == "mw"),
            "start_utc": row.get("start_utc"),
            "end_utc": row.get("end_utc"),
            "effective_end_utc": row.get("effective_end_utc") or row.get("end_utc"),
            "rows": [],
            "series": [],
        })
        score_rate = row.get("arena_score_rate")
        bucket["rows"].append({
            "rank": row.get("rank"), "player": row.get("player"),
            "player_id": row.get("player_id"), "end": row.get("end"),
            "peak": row.get("peak"), "games": row.get("games"),
            "winrate": float(score_rate) * 100 if score_rate is not None else None,
            "opponent_elo": row.get("opponent_elo"),
            "pr": performance_rating(row),
            "turns": row.get("turns"),
            "ppt": row.get("ppt"),
        })
        bucket["series"].append({
            "rank": row.get("rank"), "player": row.get("player"),
            "player_id": row.get("player_id"),
            "timestamps": list(row.get("timestamps") or []),
            "ratings": list(row.get("ratings") or []),
        })
    return {key: value for key, value in sorted(seasons.items())}

NATIVE_ROUTES = PHASE3_NATIVE_ROUTES | PHASE4_NATIVE_ROUTES


class Phase3RequestAdapter:
    """Allow-listed adapter from public dashboard concepts to local SQL.

    Unsupported page families fail clearly instead of falling back to
    arbitrary SQL or silently changing population semantics.
    """

    # Interactive callers remain page-sized, but private snapshot construction
    # needs one bounded result batch; repeating a full aggregate scan for every
    # 1,000-row page is needlessly expensive.
    MAX_LIMIT = 100000
    _VIEW_FIELDS = {
        "endgames": "endgames_view",
        "maps": "maps_view",
        "sponsor_endgames": "sponsor_endgames_view",
        "combinations": "combinations_view",
        "build": "build_view",
        "predictors": "predictors_view",
        "actions": "actions_view",
        "conservation": "conservation_view",
        "scoring": "scoring_view",
        "workers": "workers_view",
        "players": "players_view",
        "arena": "arena_view",
        "records": "records_view",
        "mw_action_cards": "mw_action_cards_view",
    }
    _DEFAULT_VIEWS = {
        "home": "default", "cards": "default", "opening_hand": "default",
        "icons": "default", "endgames": "general", "maps": "metrics",
        "sponsor_endgames": "cp", "combinations": "card_card",
        "build": "enclosures", "predictors": "general",
        "actions": "starting_position", "conservation": "projects",
        "scoring": "final_score", "workers": "general",
        "players": "general", "arena": "top_100",
        "records": "elo_leaderboard", "mw_action_cards": "general",
    }
    _DEFAULT_SNAPSHOT_PATHS = {
        "phase4_simple_actions_upgrades_by_map": "card-stats/actions/upgrades_by_map/delta",
        "card_card": "card-stats/combinations/card-card",
        "phase4_remaining_card_map": "card-stats/combinations/card-map",
        "phase4_remaining_card_round": "card-stats/combinations/card-round",
        "phase4_remaining_card_action_card": "card-stats/combinations/card-action-card",
        "phase4_remaining_card_endgame": "card-stats/combinations/card-endgame",
        "phase4_final_mw_action_cards_general": "card-stats/mw-action-cards/general",
        "phase4_final_mw_action_cards_draft": "card-stats/mw-action-cards/draft",
        "phase4_final_mw_action_cards_by_map": "card-stats/mw-action-cards/by-map",
        "phase4_final_mw_action_cards_synergies": "card-stats/mw-action-cards/synergies",
        "phase4_next_conservation_cp_rewards": "card-stats/conservation/cp-rewards",
        "phase4_remaining_players_general": "card-stats/players/general",
    }
    _STANDARD_DEFAULT_MAPS = [
        "Map 1a: Observation Tower", "Map 2a: Outdoor Areas",
        "Map 3a: Silver Lake", "Map 4a: Commercial Harbor",
        "Map 5a: Park Restaurant", "Map 6a: Research Institute",
        "Map 7a: Ice Cream Parlors", "Map 8a: Hollywood Hills",
        "Map 9: Geographical Zoo", "Map 10: Rescue Station",
        "Map 11: Caves", "Map 12: Artificial Intelligence",
        "Map 13: Drawing Board", "Map 14: Lagoon", "Map T1: Tournament 1",
    ]

    def __init__(
        self,
        store: DuckDBServingStore,
        response_cache: Phase3ResponseCache | None = None,
        audit_log: Phase3AuditLog | None = None,
        allow_default_snapshots: bool = True,
    ) -> None:
        self.store = store
        self.cache = response_cache or Phase3ResponseCache()
        self.audit_log = audit_log
        self.allow_default_snapshots = bool(allow_default_snapshots)

    def _audit(self, event: str, **fields: Any) -> None:
        if self.audit_log is None:
            return
        try:
            self.audit_log.emit(event, **fields)
        except OSError:
            pass

    @classmethod
    def _route(cls, request: Mapping[str, Any]) -> tuple[str, str]:
        page = str(request.get("stats_page") or "").strip()
        if page not in PHASE3_PAGE_CATALOG:
            raise ValueError(f"unknown stats_page: {page or '<missing>'}")
        if page == "cards" and request.get("component_ci"):
            view = "component_ci"
        elif page == "players" and request.get("players_history") is True:
            view = "history"
        else:
            field = cls._VIEW_FIELDS.get(page)
            view = str(request.get(field) or cls._DEFAULT_VIEWS[page]) if field else cls._DEFAULT_VIEWS[page]
        if view not in PHASE3_PAGE_CATALOG[page]:
            raise ValueError(f"unknown {page} view: {view}")
        return page, view

    @classmethod
    def capabilities(cls) -> dict[str, Any]:
        pages = []
        native_count = 0
        pending_count = 0
        for page, views in PHASE3_PAGE_CATALOG.items():
            route_views = []
            for view in views:
                is_native = (page, view) in NATIVE_ROUTES
                native_count += int(is_native)
                pending_count += int(not is_native)
                route_views.append({
                    "view": view,
                    "status": (
                        "native_phase3" if (page, view) in PHASE3_NATIVE_ROUTES
                        else "native_phase4" if is_native
                        else "phase4_scaffolded" if (page, view) in SIMPLE_METRIC_FAMILY_ROUTES
                        else "phase4_pending"
                    ),
                })
            pages.append({
                "stats_page": page,
                "views": route_views,
            })
        return {
            "status": "ok",
            "native_route_count": native_count,
            "phase4_pending_route_count": pending_count,
            "phase4_required": pending_count > 0,
            "pages": pages,
        }

    @classmethod
    def _page(cls, request: Mapping[str, Any]) -> str:
        page, view = cls._route(request)
        if (page, view) not in NATIVE_ROUTES:
            raise UnsupportedRouteError(
                f"{page}/{view} is recognized but has no executable production adapter"
            )
        return {
            ("cards", "default"): "cards",
            ("cards", "component_ci"): "ordinary_card_ci",
            ("players", "history"): "players_history",
            ("combinations", "card_card"): "card_card",
            ("maps", "metrics"): "phase4_maps_metrics",
            ("endgames", "general"): "phase4_endgames_general",
            ("endgames", "cp_distribution"): "phase4_next_endgames_cp_distribution",
            ("endgames", "cp_by_map"): "phase4_next_endgames_cp_by_map",
            ("maps", "tournament_h2h"): "phase4_next_maps_tournament_h2h",
            ("sponsor_endgames", "cp"): "phase4_next_sponsor_endgames_cp",
            ("sponsor_endgames", "appeal"): "phase4_next_sponsor_endgames_appeal",
            ("predictors", "general"): "phase4_next_predictors_general",
            ("predictors", "icon"): "phase4_next_predictors_icon",
            ("predictors", "specific"): "phase4_next_predictors_specific",
            ("actions", "starting_position"): "phase4_next_actions_starting_position",
            ("conservation", "cp_rewards"): "phase4_next_conservation_cp_rewards",
            ("home", "default"): "phase4_remaining_home",
            ("opening_hand", "default"): "phase4_remaining_opening_hand",
            ("combinations", "card_map"): "phase4_remaining_card_map",
            ("combinations", "card_round"): "phase4_remaining_card_round",
            ("combinations", "card_endgame"): "phase4_remaining_card_endgame",
            ("combinations", "card_action_card"): "phase4_remaining_card_action_card",
            ("players", "general"): "phase4_remaining_players_general",
            ("players", "comparison"): "phase4_remaining_players_comparison",
            ("players", "performance_by_map"): "phase4_remaining_players_performance_by_map",
            ("players", "arena_top_100"): "phase4_remaining_players_arena_top_100",
            ("arena", "top_100"): "phase4_final_arena_top_100",
            ("records", "elo_leaderboard"): "phase4_final_records_elo_leaderboard",
            ("records", "fastest_games"): "phase4_final_records_fastest_games",
            ("records", "highest_scores"): "phase4_final_records_highest_scores",
            ("records", "biggest_turns"): "phase4_final_records_biggest_turns",
            ("records", "most_icons"): "phase4_final_records_most_icons",
            ("mw_action_cards", "general"): "phase4_final_mw_action_cards_general",
            ("mw_action_cards", "draft"): "phase4_final_mw_action_cards_draft",
            ("mw_action_cards", "by_map"): "phase4_final_mw_action_cards_by_map",
            ("mw_action_cards", "synergies"): "phase4_final_mw_action_cards_synergies",
            ("scoring", "final_score"): "phase4_scoring_final_score",
            ("scoring", "appeal"): "phase4_scoring_appeal",
            ("scoring", "conservation_points"): "phase4_scoring_conservation_points",
            ("scoring", "reputation"): "phase4_scoring_reputation",
            ("actions", "upgrades"): "phase4_simple_actions_upgrades",
            ("actions", "upgrade_order"): "phase4_simple_actions_upgrade_order",
            ("actions", "upgrades_by_map"): "phase4_simple_actions_upgrades_by_map",
            ("build", "enclosures"): "phase4_simple_build_enclosures",
            ("build", "hexes"): "phase4_simple_build_hexes",
            ("icons", "default"): "phase4_simple_icons_default",
            ("conservation", "projects"): "phase4_simple_conservation_projects",
            ("conservation", "project_rewards"): "phase4_simple_conservation_project_rewards",
            ("workers", "general"): "phase4_simple_workers_general",
            ("workers", "two_cp_worker"): "phase4_simple_workers_two_cp_worker",
        }[(page, view)]

    @classmethod
    def normalize_request(cls, request: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(request, Mapping):
            raise ValueError("request must be an object")
        view = cls._page(request)
        try:
            limit = int(request.get("limit", cls.MAX_LIMIT))
            offset = int(request.get("offset", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError("limit and offset must be integers") from exc
        if limit < 1 or limit > cls.MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {cls.MAX_LIMIT}")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        is_mw = request.get("is_mw")
        if is_mw is not None:
            try:
                is_mw = int(is_mw)
            except (TypeError, ValueError) as exc:
                raise ValueError("is_mw must be 0 or 1") from exc
            if is_mw not in (0, 1):
                raise ValueError("is_mw must be 0 or 1")
        normalized: dict[str, Any] = {
            "view": view,
            "stats_page": str(request.get("stats_page") or ""),
            "limit": limit,
            "offset": offset,
            "is_mw": is_mw,
        }
        if view in {"cards", "players_history", "card_card", "ordinary_card_ci", "phase4_maps_metrics", "phase4_endgames_general"} or view.startswith("phase4_scoring_") or view.startswith("phase4_simple_") or view.startswith("phase4_next_") or view.startswith("phase4_remaining_") or view.startswith("phase4_final_"):
            normalized.update(normalize_scope(request, require_dataset=not (view in {"cards", "players_history"} or view.startswith("phase4_remaining_home") or view.startswith("phase4_final_") or view == "phase4_remaining_players_arena_top_100")))
        if view.startswith("phase4_scoring_"):
            normalized["scoring_view"] = view.removeprefix("phase4_scoring_")
        if view.startswith("phase4_simple_"):
            normalized["simple_view"] = view.removeprefix("phase4_simple_")
        if view.startswith("phase4_next_"):
            normalized["next_view"] = view.removeprefix("phase4_next_")
        if view.startswith("phase4_remaining_"):
            normalized["remaining_view"] = view.removeprefix("phase4_remaining_")
        if view.startswith("phase4_final_"):
            normalized["final_view"] = view.removeprefix("phase4_final_")
        if view.startswith("phase4_final_records_"):
            player = request.get("records_player")
            normalized["records_player"] = str(player).strip() if player else None
            normalized["records_arena_only"] = bool(request.get("records_arena_only", False))
            normalized["records_tournament_only"] = bool(request.get("records_tournament_only", False))
        if view.startswith("phase4_remaining_players_"):
            player = request.get("players_player")
            normalized["players_player"] = str(player).strip() if player else None
            raw_players = request.get("players_players") or []
            if not isinstance(raw_players, (list, tuple)):
                raise ValueError("players_players must be an array")
            normalized["players_players"] = [
                str(value).strip() for value in raw_players if str(value).strip()
            ]
            raw_last_x = request.get("last_x_games")
            if raw_last_x in (None, ""):
                normalized["last_x_games"] = None
            else:
                try:
                    last_x = int(raw_last_x)
                except (TypeError, ValueError) as exc:
                    raise ValueError("last_x_games must be an integer") from exc
                if last_x < 1:
                    raise ValueError("last_x_games must be positive")
                normalized["last_x_games"] = last_x
        if view == "players_history":
            players_view = str(request.get("players_view") or "general").strip()
            if players_view not in {"general", "comparison"}:
                raise ValueError("players_history is only available for General or Comparison")
            player = str(request.get("players_player") or "").strip()
            raw_players = request.get("players_players") or []
            if not isinstance(raw_players, (list, tuple)):
                raise ValueError("players_players must be an array")
            players = [str(value).strip() for value in raw_players if str(value).strip()]
            aliases = [player] if players_view == "general" and player else players
            if not aliases:
                raise ValueError("at least one history player is required")
            if players_view == "comparison" and len(aliases) > 5:
                raise ValueError("players_history supports at most five comparison players")
            normalized["players_view"] = players_view
            normalized["players_player"] = player or None
            normalized["players_players"] = players
            normalized["history_aliases"] = aliases
            raw_metrics = request.get("players_history_metrics") or []
            if not isinstance(raw_metrics, (list, tuple)):
                raise ValueError("players_history_metrics must be an array")
            normalized["players_history_metrics"] = [
                str(value).strip() for value in raw_metrics if str(value).strip()
            ]
            if "elo" in normalized["players_history_metrics"] and len(normalized["players_history_metrics"]) > 1:
                raise ValueError("Elo cannot be combined with another history metric")
            raw_last_x = request.get("last_x_games")
            if raw_last_x in (None, ""):
                normalized["last_x_games"] = None
            else:
                try:
                    normalized["last_x_games"] = int(raw_last_x)
                except (TypeError, ValueError) as exc:
                    raise ValueError("last_x_games must be an integer") from exc
                if normalized["last_x_games"] < 1:
                    raise ValueError("last_x_games must be positive")
        elif view == "phase4_remaining_players_arena_top_100":
            # Compatibility alias of the Arena roster: only arena_season is honoured.
            raw_season = request.get("arena_season")
            if raw_season not in (None, ""):
                normalized["arena_season"] = str(raw_season).strip()
        elif view == "phase4_final_arena_top_100":
            raw_season = request.get("arena_season")
            if raw_season not in (None, ""):
                normalized["arena_season"] = str(raw_season).strip()
            raw_players = request.get("arena_series_players") or []
            if not isinstance(raw_players, (list, tuple)):
                raise ValueError("arena_series_players must be an array")
            if len(raw_players) > 50000:
                raise ValueError("arena_series_players exceeds the private bundle limit")
            normalized["arena_series_players"] = [
                str(value).strip() for value in raw_players if str(value).strip()
            ]
            raw_player_ids = request.get("arena_series_player_ids") or []
            if not isinstance(raw_player_ids, (list, tuple)):
                raise ValueError("arena_series_player_ids must be an array")
            if len(raw_player_ids) > 50000:
                raise ValueError("arena_series_player_ids exceeds the private bundle limit")
            try:
                normalized["arena_series_player_ids"] = sorted({int(value) for value in raw_player_ids})
            except (TypeError, ValueError) as exc:
                raise ValueError("arena_series_player_ids must contain integers") from exc
        elif view == "ordinary_card_ci":
            card_name = str(request.get("card_name") or "").strip()
            if not card_name:
                raise ValueError("card_name is required for component_ci")
            normalized["card_name"] = card_name
            card_type = str(request.get("card_type") or "").strip().lower()
            normalized["card_type"] = card_type or None
        elif view == "card_card" or view in {
            "phase4_remaining_card_map", "phase4_remaining_card_round",
            "phase4_remaining_card_endgame", "phase4_remaining_card_action_card",
        }:
            try:
                minimum = int(request.get("combination_min_plays", 1000))
            except (TypeError, ValueError) as exc:
                raise ValueError("combination_min_plays must be an integer") from exc
            if minimum < 1:
                raise ValueError("combination_min_plays must be positive")
            normalized["combination_min_plays"] = minimum
            public_view = str(request.get("combinations_view") or view.removeprefix("phase4_remaining_"))
            normalized["public_combination_view"] = public_view
            normalized["component_ci"] = bool(request.get("component_ci"))
            raw_ci_rows = request.get("component_ci_rows") or []
            if normalized["component_ci"]:
                if not isinstance(raw_ci_rows, (list, tuple)) or len(raw_ci_rows) > 100:
                    raise ValueError("component_ci_rows must contain at most 100 objects")
                normalized["component_ci_rows"] = [dict(row) for row in raw_ci_rows]
                for row in normalized["component_ci_rows"]:
                    component_row_key("combinations", public_view, row)
                normalized["limit"] = 100
                normalized["offset"] = 0
            normalized["combination_paged"] = bool(request.get("combination_paged"))
            if normalized["combination_paged"]:
                try:
                    normalized["combination_page"] = max(1, int(request.get("combination_page", 1)))
                    normalized["combination_page_size"] = min(250, max(1, int(request.get("combination_page_size", 50))))
                except (TypeError, ValueError) as exc:
                    raise ValueError("combination page values must be integers") from exc
                normalized["limit"] = cls.MAX_LIMIT
                normalized["offset"] = 0
            normalized["combination_sort"] = str(request.get("combination_sort") or "interaction")
            normalized["combination_sort_dir"] = "asc" if request.get("combination_sort_dir") == "asc" else "desc"
            for key in ("combination_pair_types", "combination_card_types", "combination_header_maps", "combination_header_rounds"):
                raw = request.get(key) or []
                if not isinstance(raw, (list, tuple)):
                    raise ValueError(f"{key} must be an array")
                normalized[key] = [str(value) for value in raw]
            normalized["combination_primary"] = str(request.get("combination_primary") or "").strip()
            normalized["combination_secondary"] = str(request.get("combination_secondary") or "").strip()
        if str(request.get("stats_page") or "") == "mw_action_cards" and request.get("component_ci"):
            public_view = str(request.get("mw_action_cards_view") or "synergies")
            if public_view != "synergies":
                raise ValueError("component confidence intervals are only available for MW Synergies")
            raw_ci_rows = request.get("component_ci_rows") or []
            if not isinstance(raw_ci_rows, (list, tuple)) or len(raw_ci_rows) > 100:
                raise ValueError("component_ci_rows must contain at most 100 objects")
            normalized["component_ci"] = True
            normalized["component_ci_rows"] = [dict(row) for row in raw_ci_rows]
            for row in normalized["component_ci_rows"]:
                component_row_key("mw_action_cards", public_view, row)
            normalized["public_mw_view"] = public_view
            normalized["limit"] = 100
            normalized["offset"] = 0
        return normalized

    def _default_snapshot_response(
        self, normalized: Mapping[str, Any], generation: Generation,
    ) -> dict[str, Any] | None:
        """Serve an exact default-scope request from the immutable snapshot.

        Default dashboard views already have a generation-local snapshot. Using
        it here prevents a private API caller or route smoke test from repeating
        the full analytical scan that produced the snapshot. Any filter, custom
        combination threshold, or missing/stale asset falls through to SQL.
        """

        path_fragment = self._DEFAULT_SNAPSHOT_PATHS.get(str(normalized.get("view")))
        if not path_fragment:
            return None
        if normalized.get("component_ci") or normalized.get("combination_paged"):
            return None
        if normalized.get("is_mw") not in (0, 1):
            return None
        is_players = str(normalized.get("view")) == "phase4_remaining_players_general"
        # The general Players snapshot contains only baseline cohorts. A player
        # selection must always reach the identity fact; otherwise the response
        # is fast but silently returns null player values from the default file.
        if is_players and (
            normalized.get("players_player")
            or normalized.get("players_players")
            or normalized.get("last_x_games") is not None
        ):
            return None
        defaults = {
            "maps": sorted(self._STANDARD_DEFAULT_MAPS),
            "player_elo_min": 0 if is_players else 300,
            "player_elo_max": None,
            "opponent_elo_min": 0 if is_players else 300,
            "opponent_elo_max": None,
            "date_from": None if is_players else "2025-01-01",
            "date_to": None,
            "starting_positions": ["First player", "Second player"],
            "completed_only": None, "arena_seasons": [], "arena_only": False,
            "rounds": [], "tournament_only": False,
        }
        if any(normalized.get(key) != value for key, value in defaults.items()):
            return None
        if normalized.get("combination_min_plays") not in (None, 1000):
            return None
        snapshot_root = self.store.manager.generations_dir.parent / "snapshots" / generation.generation_id
        suffix = "mw" if normalized["is_mw"] == 1 else "base"
        path = snapshot_root / path_fragment / f"default-{suffix}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if (
            not isinstance(payload, dict)
            or payload.get("data_version") != generation.data_version
            or payload.get("contract_schema_version") != PUBLIC_CONTRACT_SCHEMA_VERSION
        ):
            return None
        data = payload.get("data")
        if not isinstance(data, list):
            return None
        page = data[int(normalized["offset"]): int(normalized["offset"]) + int(normalized["limit"])]
        return {
            "status": "ok", "source": "duckdb_private_snapshot",
            "generation": generation.generation_id,
            "data_version": generation.data_version,
            "view": normalized["view"], "data": _json_safe(page),
            "row_count": len(page), "cache_status": "private_snapshot",
            "contract_schema_version": PUBLIC_CONTRACT_SCHEMA_VERSION,
        }

    @staticmethod
    def _cards_table_fact_sql(request: Mapping[str, Any]) -> tuple[str, list[Any]]:
        if request.get('maps'):
            # A table/card moment pools both players. Their maps can differ,
            # so ANY_VALUE(Map) cannot represent a focal-player map selection.
            # Keep the exact player-grain path until map-aware table moments
            # have been independently validated.
            return Phase3RequestAdapter._cards_sql(dict(request, _cards_table_fact=False))
        relation = (
            "card_filter_table_fact_mw_narrow"
            if int(request["is_mw"]) == 1
            else "card_filter_table_fact_base_narrow"
        )
        predicates = ["c.table_elo_count = c.table_player_count"]
        parameters: list[Any] = []
        if request.get("maps"):
            predicates.append(
                "c.Map IN (" + ", ".join("?" for _ in request["maps"]) + ")"
            )
            parameters.extend(request["maps"])
        if request.get("player_elo_min") is not None:
            predicates.append("c.min_pre_match_elo >= ?")
            parameters.append(request["player_elo_min"])
        if request.get("player_elo_max") is not None:
            predicates.append("c.max_pre_match_elo <= ?")
            parameters.append(request["player_elo_max"])
        if request.get("date_from"):
            predicates.append("CAST(c.game_ended_at AS DATE) >= CAST(? AS DATE)")
            parameters.append(request["date_from"])
        if request.get("date_to"):
            predicates.append("CAST(c.game_ended_at AS DATE) <= CAST(? AS DATE)")
            parameters.append(request["date_to"])
        if request.get("arena_seasons"):
            predicates.append(
                "c.arena_season IN ("
                + ", ".join("?" for _ in request["arena_seasons"]) + ")"
            )
            parameters.extend(request["arena_seasons"])
        elif request.get("arena_only"):
            predicates.append("c.is_arena_game")
        if request.get("tournament_only"):
            predicates.append("c.is_tournament")
        if request.get("completed_only") is True:
            predicates.append("c.is_completed_game")
        excluded_projects = ", ".join(
            "'" + value.replace("'", "''") + "'"
            for value in sorted(EXCLUDED_SUMMARY_PROJECTS)
        )
        where = " AND ".join(predicates)
        return f"""
        WITH moments AS (
          SELECT card_name, MAX(card_type) AS card_type,
            SUM(n_played) AS n_played,
            SUM(played_n) AS played_n,
            FSUM(played_sum) AS played_sum,
            FSUM(played_sumsq) AS played_sumsq,
            SUM(pre_match_n) AS pre_match_n,
            FSUM(pre_match_sum) AS pre_match_sum,
            SUM(hand_n) AS hand_n,
            FSUM(hand_sum) AS hand_sum,
            FSUM(hand_sumsq) AS hand_sumsq,
            SUM(n_seen) AS n_seen
          FROM {relation} c
          WHERE {where}
          GROUP BY card_name
        )
        SELECT card_name, card_type,
          ROUND(played_sum / played_n, 3) AS delta_played,
          ROUND(hand_sum / hand_n, 3) AS delta_in_hand,
          played_sum / played_n AS delta_played_ci_mean,
          SQRT(GREATEST(played_sumsq - played_sum * played_sum / played_n, 0)
            / NULLIF(played_n - 1, 0)) AS delta_played_ci_sd,
          played_n AS delta_played_ci_n,
          hand_sum / hand_n AS delta_in_hand_ci_mean,
          SQRT(GREATEST(hand_sumsq - hand_sum * hand_sum / hand_n, 0)
            / (CASE WHEN hand_n > 1 THEN hand_n - 1 END)) AS delta_in_hand_ci_sd,
          hand_n AS delta_in_hand_ci_n,
          ROUND(pre_match_sum / pre_match_n, 0) AS avg_elo,
          n_played, n_seen,
          CASE WHEN n_seen = 0 THEN NULL
            ELSE ROUND(100.0 * n_played / n_seen, 2)
          END AS playrate_pct,
          CAST(NULL AS DOUBLE) AS avg_cp
        FROM moments
        WHERE played_n > 0
          AND NOT (card_type = 'project' AND LOWER(card_name) IN ({excluded_projects}))
        ORDER BY card_type, playrate_pct DESC NULLS LAST,
          n_played DESC, card_name
        LIMIT ? OFFSET ?
        """, parameters

    @staticmethod
    def _cards_sql(request: Mapping[str, Any]) -> tuple[str, list[Any]]:
        if request.get('_cards_pair_fact'):
            return cards_pair_sql(request, EXCLUDED_SUMMARY_PROJECTS)
        if request.get("_cards_table_fact"):
            return Phase3RequestAdapter._cards_table_fact_sql(request)
        if request.get("_cards_filter_fact"):
            fact_relation = (
                "card_filter_fact_mw_narrow"
                if int(request["is_mw"]) == 1
                else "card_filter_fact_base_narrow"
            )
            predicates, parameters = scope_predicates(
                request, "c", hard_completed=False, include_corrupted=True
            )
            selected_rounds = list(request.get("rounds") or [])
            round_columns = {
                "1": "played_r1", "2": "played_r2", "3": "played_r3",
                "4": "played_r4", "5": "played_r5", "6+": "played_r6plus",
            }
            play_count = " + ".join(
                f"c.{round_columns[value]}" for value in selected_rounds
            ) if selected_rounds else "c.played_count"
            show_context = not bool(selected_rounds)
            excluded_projects = ", ".join(
                "'" + value.replace("'", "''") + "'"
                for value in sorted(EXCLUDED_SUMMARY_PROJECTS)
            )
            return f"""
            WITH scoped AS (
              SELECT c.*, ({play_count}) AS effective_play_count
              FROM {fact_relation} c
              WHERE {predicates}
            ), moments AS (
              SELECT card_name, MAX(card_type) AS card_type,
                COUNT(DISTINCT table_id) FILTER (
                  WHERE effective_play_count > 0 AND elo_delta IS NOT NULL
                ) AS n_played,
                SUM(effective_play_count) FILTER (
                  WHERE effective_play_count > 0 AND elo_delta IS NOT NULL
                ) AS played_n,
                FSUM(effective_play_count * elo_delta) FILTER (
                  WHERE effective_play_count > 0 AND elo_delta IS NOT NULL
                ) AS played_sum,
                FSUM(effective_play_count * elo_delta * elo_delta) FILTER (
                  WHERE effective_play_count > 0 AND elo_delta IS NOT NULL
                ) AS played_sumsq,
                SUM(effective_play_count) FILTER (
                  WHERE effective_play_count > 0 AND elo_delta IS NOT NULL
                    AND pre_match_elo IS NOT NULL
                ) AS pre_match_n,
                FSUM(effective_play_count * pre_match_elo) FILTER (
                  WHERE effective_play_count > 0 AND elo_delta IS NOT NULL
                    AND pre_match_elo IS NOT NULL
                ) AS pre_match_sum,
                COUNT(*) FILTER (WHERE in_hand > 0 AND elo_delta IS NOT NULL) AS hand_n,
                FSUM(elo_delta) FILTER (WHERE in_hand > 0 AND elo_delta IS NOT NULL) AS hand_sum,
                FSUM(elo_delta * elo_delta) FILTER (
                  WHERE in_hand > 0 AND elo_delta IS NOT NULL
                ) AS hand_sumsq,
                COUNT(DISTINCT table_id) FILTER (WHERE seen > 0) AS n_seen
              FROM scoped
              GROUP BY card_name
            )
            SELECT card_name, card_type,
              ROUND(played_sum / played_n, 3) AS delta_played,
              {"ROUND(hand_sum / hand_n, 3)" if show_context else "CAST(NULL AS DOUBLE)"} AS delta_in_hand,
              played_sum / played_n AS delta_played_ci_mean,
              SQRT(GREATEST(played_sumsq - played_sum * played_sum / played_n, 0)
                / NULLIF(played_n - 1, 0)) AS delta_played_ci_sd,
              played_n AS delta_played_ci_n,
              {"hand_sum / hand_n" if show_context else "CAST(NULL AS DOUBLE)"} AS delta_in_hand_ci_mean,
              {"SQRT(GREATEST(hand_sumsq - hand_sum * hand_sum / hand_n, 0) / (CASE WHEN hand_n > 1 THEN hand_n - 1 END))" if show_context else "CAST(NULL AS DOUBLE)"} AS delta_in_hand_ci_sd,
              {"hand_n" if show_context else "CAST(0 AS BIGINT)"} AS delta_in_hand_ci_n,
              ROUND(pre_match_sum / pre_match_n, 0) AS avg_elo,
              n_played,
              {"n_seen" if show_context else "CAST(NULL AS BIGINT)"} AS n_seen,
              CASE WHEN {str(not show_context).upper()} OR n_seen = 0 THEN NULL
                ELSE ROUND(100.0 * n_played / n_seen, 2)
              END AS playrate_pct,
              CAST(NULL AS DOUBLE) AS avg_cp
            FROM moments
            WHERE played_n > 0
              AND NOT (card_type = 'project' AND LOWER(card_name) IN ({excluded_projects}))
            ORDER BY card_type, playrate_pct DESC NULLS LAST,
              n_played DESC, card_name
            LIMIT ? OFFSET ?
            """, parameters

        # A real filtered request carries a dataset or an explicit scope and
        # therefore uses the shared predicate builder below. Unscoped internal
        # diagnostics still read the same canonical prepared population.
        has_scope = (
            request.get("is_mw") is not None
            or bool(request.get("maps"))
            or any(request.get(key) not in (None, "", 0, []) for key in (
                "player_elo_max", "opponent_elo_max", "date_from", "date_to",
                "arena_seasons", "arena_only", "rounds", "tournament_only",
            ))
            or request.get("player_elo_min") not in (None, "", 0)
            or request.get("opponent_elo_min") not in (None, "", 0)
            or request.get("completed_only") is True
            or request.get("starting_positions") not in (None, [], ["First player", "Second player"])
        )
        if has_scope:
            predicates, parameters = scope_predicates(request, "f", hard_completed=False)
        else:
            predicates, parameters = "TRUE", []
        selected_rounds = list(request.get("rounds") or [])
        round_terms: list[str] = []
        exact_rounds = [int(value) for value in selected_rounds if value != "6+"]
        if exact_rounds:
            round_terms.append(
                "cp.played_round IN (" + ", ".join("?" for _ in exact_rounds) + ")"
            )
            parameters.extend(exact_rounds)
        if "6+" in selected_rounds:
            round_terms.append("cp.played_round >= 6")
        round_predicate = " AND (" + " OR ".join(round_terms) + ")" if round_terms else ""
        show_context = not bool(selected_rounds)
        excluded_projects = ", ".join(
            "'" + value.replace("'", "''") + "'" for value in sorted(EXCLUDED_SUMMARY_PROJECTS)
        )
        # The filtered player-game relation is the authoritative scope and is
        # joined directly by played/in-hand facts. Do not rejoin the full
        # prepared population here: that duplicates the dominant scan and can
        # push uncached Cards filters beyond the public deadline.
        return (
            f"""
            WITH filtered AS (
              SELECT f.table_id, f.player, f.pre_match_elo, f.elo_delta
              FROM prepared_full_sample_narrow f WHERE {predicates}
            ), played AS (
              SELECT cp.table_id, cp.player, cp.card_name, cp.card_type,
                cp.elo_delta, f.pre_match_elo
              FROM card_play_narrow cp
              JOIN filtered f
                ON f.table_id = cp.table_id AND f.player = cp.player
              WHERE cp.elo_delta IS NOT NULL
                AND NOT (cp.card_type = 'project' AND LOWER(cp.card_name) IN ({excluded_projects}))
                {round_predicate}
            ), played_agg AS (
              SELECT card_name, card_type,
                COUNT(DISTINCT table_id) AS n_played,
                ROUND(AVG(elo_delta), 3) AS delta_played,
                AVG(elo_delta) AS delta_played_ci_mean,
                STDDEV_SAMP(elo_delta) AS delta_played_ci_sd,
                COUNT(elo_delta) AS delta_played_ci_n,
                ROUND(AVG(pre_match_elo), 0) AS avg_elo
              FROM played
              GROUP BY card_name, card_type
            ), in_hand AS (
              SELECT DISTINCT h.table_id, h.player, h.card_name, f.elo_delta
              FROM card_in_hand_narrow h
              JOIN filtered f
                ON f.table_id = h.table_id AND f.player = h.player
              WHERE f.elo_delta IS NOT NULL
                AND LOWER(h.card_name) NOT IN ({excluded_projects})
            ), in_hand_agg AS (
              SELECT card_name,
                ROUND(AVG(elo_delta), 3) AS delta_in_hand,
                AVG(elo_delta) AS delta_in_hand_ci_mean,
                STDDEV_SAMP(elo_delta) AS delta_in_hand_ci_sd,
                COUNT(elo_delta) AS delta_in_hand_ci_n
              FROM in_hand
              GROUP BY card_name
            ), seen_agg AS (
              SELECT s.card_name, COUNT(DISTINCT s.table_id) AS n_seen
              FROM card_seen_narrow s
              JOIN filtered scope
                ON scope.table_id = s.table_id AND scope.player = s.player
              WHERE LOWER(s.card_name) NOT IN ({excluded_projects})
              GROUP BY card_name
            )
            SELECT p.card_name, p.card_type,
              p.delta_played,
              {"h.delta_in_hand" if show_context else "CAST(NULL AS DOUBLE)"} AS delta_in_hand,
              p.delta_played_ci_mean, p.delta_played_ci_sd,
              p.delta_played_ci_n,
              {"h.delta_in_hand_ci_mean" if show_context else "CAST(NULL AS DOUBLE)"} AS delta_in_hand_ci_mean,
              {"h.delta_in_hand_ci_sd" if show_context else "CAST(NULL AS DOUBLE)"} AS delta_in_hand_ci_sd,
              {"COALESCE(h.delta_in_hand_ci_n, 0)" if show_context else "CAST(0 AS BIGINT)"} AS delta_in_hand_ci_n,
              p.avg_elo, p.n_played,
              {"COALESCE(s.n_seen, 0)" if show_context else "CAST(NULL AS BIGINT)"} AS n_seen,
              CASE WHEN {str(not show_context).upper()} OR COALESCE(s.n_seen, 0) = 0 THEN NULL
                ELSE ROUND(100.0 * p.n_played / s.n_seen, 2)
              END AS playrate_pct,
              CAST(NULL AS DOUBLE) AS avg_cp
            FROM played_agg p
            LEFT JOIN in_hand_agg h USING(card_name)
            LEFT JOIN seen_agg s USING(card_name)
            ORDER BY p.card_type, playrate_pct DESC NULLS LAST,
              p.n_played DESC, p.card_name
            LIMIT ? OFFSET ?
            """,
            parameters,
        )

    @staticmethod
    def _players_history_sql(request: Mapping[str, Any]) -> tuple[str, list[Any]]:
        metrics = list(request.get("players_history_metrics") or [])
        catalog = {item[0]: item for item in PLAYERS_METRICS}
        invalid = [key for key in metrics if key != "elo" and key not in catalog]
        if invalid:
            raise ValueError(f"Unknown Players history metric: {invalid[0]}")
        elo_only = metrics == ["elo"]
        aliases = list(request.get("history_aliases") or [])
        requested_values = ", ".join(f"({index}, ?)" for index in range(len(aliases)))
        money_total = " + ".join(
            f"COALESCE(TRY_CAST({column} AS DOUBLE), 0)"
            for column in PLAYERS_MONEY_FIELDS.values()
        )

        def value_expression(key: str) -> str:
            if key == "elo":
                return "TRY_CAST(post_match_elo AS DOUBLE)"
            if key in PLAYERS_MONEY_FIELDS:
                column = PLAYERS_MONEY_FIELDS[key]
                return f"100.0 * TRY_CAST({column} AS DOUBLE) / NULLIF(({money_total}), 0)"
            aggregate = str(catalog[key][-1]).strip()
            if not (aggregate.startswith("AVG(") and aggregate.endswith(")")):
                raise ValueError(f"Players history metric {key} has no row expression")
            return aggregate[4:-1]

        value_selects = ",\n                ".join(
            f"{value_expression(key)} AS {key}" for key in metrics
        )
        rolling_selects = ",\n                ".join(
            f"AVG({key}) OVER (PARTITION BY position ORDER BY game_ended_at, "
            f"CAST(table_id AS VARCHAR) ROWS BETWEEN 99 PRECEDING AND CURRENT ROW) AS {key}"
            for key in metrics
        )
        if elo_only:
            predicates = "NOT f.is_corrupted_game AND f.post_match_elo IS NOT NULL"
            scope_parameters: list[Any] = []
            source = "prepared_full_sample_narrow"
        else:
            predicates, scope_parameters = scope_predicates(
                request, "f", hard_completed=True, population_prepared=True
            )
            source = "players_metrics_narrow"
        last_x = request.get("last_x_games")
        effective_last_x = 0 if elo_only or last_x is None else int(last_x)
        parameters: list[Any] = [*aliases, *scope_parameters]
        return (
            f"""
            WITH requested(position, player) AS (VALUES {requested_values}),
            resolved AS (
              SELECT r.position, r.player,
                COALESCE(m.player_identity, 'player:' || r.player) AS player_identity
              FROM requested r LEFT JOIN player_identity_metadata m
                ON m.player_casefold = LOWER(TRIM(r.player))
            ), filtered AS (
              SELECT r.position, r.player AS requested_player,
                f.table_id, f.game_ended_at,
                {value_selects},
                ROW_NUMBER() OVER (
                  PARTITION BY r.position
                  ORDER BY f.game_ended_at DESC, CAST(f.table_id AS VARCHAR) DESC
                ) AS recent_rank
              FROM {source} f JOIN resolved r USING(player_identity)
              WHERE {predicates}
            ), limited AS (
              SELECT * FROM filtered
              WHERE {effective_last_x} = 0 OR recent_rank <= {effective_last_x}
            ), ordered AS (
              SELECT *,
                ROW_NUMBER() OVER (
                  PARTITION BY position
                  ORDER BY game_ended_at, CAST(table_id AS VARCHAR)
                ) AS game_number,
                COUNT(*) OVER (PARTITION BY position) AS game_count
              FROM limited
            ), rolled AS (
              SELECT position, requested_player, game_number, game_count,
                game_ended_at, {rolling_selects}
              FROM ordered
            )
            SELECT * FROM rolled WHERE game_number >= 100
            ORDER BY position, game_number
            LIMIT ? OFFSET ?
            """,
            parameters,
        )

    @staticmethod
    def _card_card_sql(request: Mapping[str, Any]) -> tuple[str, list[Any]]:
        return combination_sql(request, "card_card")

    @staticmethod
    def _ordinary_ci_sql(request: Mapping[str, Any]) -> tuple[str, list[Any]]:
        """cards/component_ci: table-clustered 95% interval of one card's mean Elo delta.

        Population = the Cards row's own scope (every filter in the request, via
        scope_predicates) joined to the card's distinct player-game plays, with the
        selected rounds applied to the play round. Both players of one table form a
        single cluster. Default and restrictive requests share this scoped
        canonical path; validation-only component/pair relations are not inputs.
        """
        predicates, scope_params = scope_predicates(request, "g", hard_completed=False)
        round_clause = _round_clause("cp", request.get("rounds") or [])
        excluded = ", ".join(_quoted(value) for value in EXCLUDED_PROJECTS)
        return (
            f"""
            WITH scoped_players AS (
              SELECT g.table_id, g.player
              FROM prepared_full_sample_narrow g
              WHERE {predicates}
            ), played AS (
              SELECT DISTINCT s.table_id, s.player, cp.card_name, cp.card_type, cp.elo_delta
              FROM scoped_players s JOIN card_play_narrow cp USING(table_id, player)
              WHERE cp.card_name = ?
                AND (? IS NULL OR cp.card_type = ?)
                AND cp.elo_delta IS NOT NULL
                AND NOT (cp.card_type = 'project' AND LOWER(cp.card_name) IN ({excluded})){round_clause}
            ), by_table AS (
              SELECT table_id, COUNT(elo_delta) AS delta_count, SUM(elo_delta) AS delta_sum
              FROM played GROUP BY table_id
            ), totals AS (
              SELECT SUM(delta_count) AS n, SUM(delta_sum) AS total_sum, COUNT(*) AS clusters
              FROM by_table
            ), means AS (
              SELECT n, total_sum, clusters, total_sum / NULLIF(n, 0) AS delta FROM totals
            ), variance AS (
              SELECT m.*,
                SUM(POW((c.delta_sum - c.delta_count * m.delta) / NULLIF(m.n, 0), 2)) AS influence_sum
              FROM means m LEFT JOIN by_table c ON TRUE
              GROUP BY m.n, m.total_sum, m.clusters, m.delta
            )
            SELECT delta, n AS n_played, clusters AS cluster_n,
              CASE WHEN clusters >= 2 AND n > 0 THEN
                SQRT(clusters / (clusters - 1) * influence_sum)
              END AS se,
              CASE WHEN clusters >= 2 AND n > 0 THEN
                delta - 1.96 * SQRT(clusters / (clusters - 1) * influence_sum)
              END AS ci95_low,
              CASE WHEN clusters >= 2 AND n > 0 THEN
                delta + 1.96 * SQRT(clusters / (clusters - 1) * influence_sum)
              END AS ci95_high
            FROM variance
            """,
            [*scope_params, request["card_name"], request["card_type"], request["card_type"]],
        )

    @classmethod
    def _sql_for(cls, normalized: Mapping[str, Any]) -> tuple[str, list[Any]]:
        view = normalized["view"]
        if normalized.get("component_ci"):
            stats_page = str(normalized.get("stats_page"))
            public_view = str(normalized.get("public_combination_view") or normalized.get("public_mw_view") or "")
            return component_ci_sql(
                normalized, stats_page, public_view,
                normalized.get("component_ci_rows") or [],
            )
        if view == "cards":
            return cls._cards_sql(normalized)
        if view == "players_history":
            return cls._players_history_sql(normalized)
        if view == "card_card":
            return cls._card_card_sql(normalized)
        if view == "ordinary_card_ci":
            return cls._ordinary_ci_sql(normalized)
        if view == "phase4_maps_metrics":
            return maps_metrics_sql(normalized)
        if view == "phase4_endgames_general":
            return endgames_general_sql(normalized)
        if view.startswith("phase4_scoring_"):
            return scoring_sql(normalized)
        if view.startswith("phase4_simple_"):
            return _simple_metric_sql(normalized)
        if view.startswith("phase4_next_"):
            return _next_route_sql(normalized)
        if view.startswith("phase4_remaining_"):
            return _remaining_route_sql(normalized)
        if view.startswith("phase4_final_"):
            return _final_route_sql(normalized)
        raise ServingStateError(f"no query builder registered for {view}")

    def execute(self, request: Mapping[str, Any]) -> dict[str, Any]:
        normalized = self.normalize_request(request)
        generation = self.store.generation()
        if generation is None:
            raise ServingStateError("no active DuckDB generation")
        # Optimized facts are generation capabilities, never public request
        # switches. This keeps a newly deployed service compatible with the
        # previous rollback generation while allowing the corrected candidate
        # to take the fast path immediately after activation.
        built_relations = set(
            (generation.manifest.get("builder") or {}).get("relations", {})
        )
        relation_descriptors = (generation.manifest.get('builder') or {}).get('relations', {})
        normalized['_cards_pair_fact'] = (
            normalized['view'] == 'cards' and normalized.get('is_mw') in (0, 1)
            and {f'cards_pair_scope_{"mw" if normalized["is_mw"] else "base"}_narrow',
                 f'cards_pair_fact_{"mw" if normalized["is_mw"] else "base"}_narrow',
                 'card_catalog_narrow'}.issubset(built_relations)
            and relation_descriptors[f'cards_pair_fact_{"mw" if normalized["is_mw"] else "base"}_narrow'].get('schema_version') == 2
        )
        normalized['_cards_pair_pooled_fact'] = (
            normalized['_cards_pair_fact']
            and f'cards_pair_pooled_fact_{"mw" if normalized["is_mw"] else "base"}_narrow' in built_relations
            and relation_descriptors[f'cards_pair_pooled_fact_{"mw" if normalized["is_mw"] else "base"}_narrow'].get('schema_version') == 2
        )
        normalized["_cards_filter_fact"] = (
            normalized["view"] == "cards"
            and normalized.get("is_mw") in (0, 1)
            and {
                "card_filter_fact_mw_narrow",
                "card_filter_fact_base_narrow",
            }.issubset(built_relations)
        )
        normalized["_cards_table_fact"] = (
            normalized["view"] == "cards"
            and normalized.get("is_mw") in (0, 1)
            and not normalized.get("maps")
            and not normalized.get("rounds")
            and set(normalized.get("starting_positions") or ()) == {
                "First player", "Second player"
            }
            and normalized.get("player_elo_min")
                == normalized.get("opponent_elo_min")
            and normalized.get("player_elo_max")
                == normalized.get("opponent_elo_max")
            and {
                "card_filter_table_fact_mw_narrow",
                "card_filter_table_fact_base_narrow",
            }.issubset(built_relations)
        )
        normalized["_combos_filter_fact"] = (
            normalized["view"] in {
                "card_card", "phase4_remaining_card_action_card",
                "phase4_remaining_card_map", "phase4_remaining_card_round",
                "phase4_remaining_card_endgame",
            }
            and {
                "card_filter_fact_mw_narrow",
                "card_filter_fact_base_narrow",
            }.issubset(built_relations)
        )
        normalized["_combos_played_fact"] = normalized["_combos_filter_fact"] and {
            "card_play_filter_fact_mw_narrow", "card_play_filter_fact_base_narrow",
            "card_catalog_narrow",
        }.issubset(built_relations)
        normalized['_combo_card_pair_fact'] = (
            normalized['view'] == 'card_card' and normalized.get('is_mw') in (0, 1)
            and normalized['_combos_played_fact']
            and {f'cards_pair_scope_{"mw" if normalized["is_mw"] else "base"}_narrow',
                 f'combo_card_pair_fact_{"mw" if normalized["is_mw"] else "base"}_narrow'}.issubset(built_relations)
            and relation_descriptors[f'combo_card_pair_fact_{"mw" if normalized["is_mw"] else "base"}_narrow'].get('schema_version') == 2
        )
        normalized['_combo_card_component_pair_fact'] = (
            normalized['_combo_card_pair_fact']
            and f'cards_pair_fact_{"mw" if normalized["is_mw"] else "base"}_narrow' in built_relations
            and relation_descriptors[f'cards_pair_fact_{"mw" if normalized["is_mw"] else "base"}_narrow'].get('schema_version') == 2
        )
        normalized["_mw_filter_facts"] = normalized["view"] in {
            "phase4_final_mw_action_cards_general", "phase4_final_mw_action_cards_draft",
            "phase4_final_mw_action_cards_by_map", "phase4_final_mw_action_cards_synergies",
        } and "mw_action_card_same_map_tables_narrow" in built_relations
        normalized["_card_action_pair_fact"] = (
            normalized["view"] == "phase4_remaining_card_action_card"
            and "card_action_pair_filter_fact_narrow" in built_relations
        )
        normalized["_players_filter_facts"] = (
            normalized["view"] == "phase4_remaining_players_general"
            and {
                "players_by_identity_narrow",
                "players_default_cohorts_narrow",
            }.issubset(built_relations)
        )
        key = self.cache.key_for(generation, normalized)
        request_fingerprint = key.rsplit("/", 1)[-1]
        started = time.perf_counter()
        cached = self.cache.get(key)
        if cached is not None:
            cached["cache_status"] = "private_hit"
            self._audit(
                "query_cache_hit",
                generation=generation.generation_id,
                data_version=generation.data_version,
                view=normalized["view"],
                request_fingerprint=request_fingerprint,
                cache_status="private_hit",
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
                row_count=cached.get("row_count"),
            )
            return cached
        snapshot_response = (
            self._default_snapshot_response(normalized, generation)
            if self.allow_default_snapshots else None
        )
        if snapshot_response is not None:
            self.cache.put(key, snapshot_response)
            return snapshot_response
        sql, parameters = self._sql_for(normalized)
        # Arena is a season bundle rather than a paged row list.  Its query
        # deliberately returns every imported roster row for the bundle.
        if normalized["view"] != "phase4_final_arena_top_100":
            parameters.extend([normalized["limit"], normalized["offset"]])
        # The CI query supplies one row and does not use pagination parameters.
        if normalized["view"] == "ordinary_card_ci":
            parameters = parameters[:-2]
        try:
            result = self.store.query(sql, parameters)
            expanded_result = None
            expanded_flag = None
            if normalized["view"].startswith("phase4_scoring_"):
                expanded_flag = "scoring_expanded"
            elif normalized["view"] == "phase4_simple_build_hexes":
                expanded_flag = "build_expanded"
            if expanded_flag:
                expanded_request = dict(normalized)
                expanded_request[expanded_flag] = True
                expanded_sql, expanded_parameters = self._sql_for(expanded_request)
                expanded_parameters.extend([normalized["limit"], normalized["offset"]])
                expanded_result = self.store.query(expanded_sql, expanded_parameters)
        except Exception as exc:
            self._audit(
                "query_failed",
                generation=generation.generation_id,
                data_version=generation.data_version,
                view=normalized["view"],
                request_fingerprint=request_fingerprint,
                error_type=type(exc).__name__,
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
            )
            raise
        response_extras: dict[str, Any] = {}
        if normalized["view"] == "phase4_final_arena_top_100":
            payload_data: Any = _json_safe(_project_arena_bundle(result["rows"]))
            payload_count = sum(len(item["rows"]) for item in payload_data.values())
        else:
            projected_rows = _json_safe([
                project_ordinary_ci_fields(row) for row in result["rows"]
            ])
            if normalized.get("component_ci"):
                payload_data = projected_rows
            elif normalized["view"] == "phase4_remaining_players_general":
                payload_data, response_extras = _project_players_general(projected_rows, normalized)
            elif normalized["view"] == "phase4_remaining_players_comparison":
                payload_data, response_extras = _project_players_comparison(projected_rows, normalized)
            elif normalized["view"] == "phase4_remaining_players_performance_by_map":
                payload_data, response_extras = _project_players_performance(projected_rows, normalized)
            elif normalized["view"] == "players_history":
                history = _project_players_history(projected_rows, normalized)
                payload_data = []
                response_extras = history
            elif normalized["view"] == "card_card" or normalized["view"] in {
                "phase4_remaining_card_map", "phase4_remaining_card_round",
                "phase4_remaining_card_endgame", "phase4_remaining_card_action_card",
            }:
                public_view = str(
                    normalized.get("public_combination_view")
                    or normalized["view"].removeprefix("phase4_remaining_")
                )
                payload_data, response_extras = _project_combination_rows(
                    projected_rows, normalized, public_view,
                )
            else:
                payload_data = projected_rows
            payload_count = len(payload_data)
            if expanded_result is not None:
                response_extras["expanded_data"] = _json_safe([
                    project_ordinary_ci_fields(row) for row in expanded_result["rows"]
                ])
        response = {
            "status": "ok",
            "source": "duckdb_private",
            "generation": result["generation"],
            "data_version": result["data_version"],
            "view": normalized["view"],
            "data": payload_data,
            "row_count": payload_count,
            "cache_status": "private_miss",
            "contract_schema_version": PUBLIC_CONTRACT_SCHEMA_VERSION,
        }
        response.update(response_extras)
        if normalized["view"] in {"cards", "phase4_remaining_opening_hand"}:
            response["round_filter_active"] = bool(normalized.get("rounds"))
        actual_generation = self.store.manager.inspect(result["generation"])
        actual_key = self.cache.key_for(actual_generation, normalized)
        self.cache.put(actual_key, response)
        self._audit(
            "query_completed",
            generation=actual_generation.generation_id,
            data_version=actual_generation.data_version,
            view=normalized["view"],
            request_fingerprint=actual_key.rsplit("/", 1)[-1],
            cache_status="private_miss",
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            row_count=len(result["rows"]),
        )
        return response


def create_private_adapter(
    manager: GenerationManager,
    persistent_cache_path: str | Path | None = None,
    memory_items: int = 128,
    persistent_items: int = 512,
    audit_log: Phase3AuditLog | None = None,
    generation_id: str | None = None,
    allow_default_snapshots: bool = True,
    query_timeout_seconds: float | None = None,
    memory_limit: str | None = None,
) -> Phase3RequestAdapter:
    """Create the private adapter with the standard persistent cache location."""

    cache_path = Path(
        persistent_cache_path
        or manager.pointer_path.parent / "response-cache.sqlite3"
    )
    persistent = Phase3PersistentResponseCache(cache_path, persistent_items)
    effective_audit = audit_log or manager.audit_log
    return Phase3RequestAdapter(
        DuckDBServingStore(
            manager,
            generation_id=generation_id,
            query_timeout_seconds=query_timeout_seconds,
            memory_limit=memory_limit,
        ),
        Phase3ResponseCache(memory_items, persistent),
        audit_log=effective_audit,
        allow_default_snapshots=allow_default_snapshots,
    )


def warm_interactive_generation(
    manager: GenerationManager,
    generation_id: str | None = None,
) -> list[dict[str, Any]]:
    """Prime disk/page caches for the dominant uncached Cards relations.

    This intentionally uses an isolated memory-only response cache and disables
    snapshots. It therefore performs the analytical reads even when an equal
    request was cached by an earlier API process. Publication calls it before
    pointer activation; API startup calls it before opening the listening port.
    """

    adapter = Phase3RequestAdapter(
        DuckDBServingStore(manager, generation_id=generation_id),
        Phase3ResponseCache(max_items=2),
        allow_default_snapshots=False,
    )
    maps = [
        "1a", "2a", "3a", "4a", "5a", "6a", "7a", "8a",
        "9", "10", "11", "12", "13", "14", "T1",
    ]
    results: list[dict[str, Any]] = []
    for dataset in (1, 0):
        started = time.perf_counter()
        response = adapter.execute({
            "stats_page": "cards", "is_mw": dataset,
            "maps": maps, "player_elo_min": 301,
            "opponent_elo_min": 301, "date_from": "2025-01-01",
            "starting_positions": ["First player", "Second player"],
            "limit": 1,
        })
        results.append({
            "dataset": dataset,
            "generation": response.get("generation"),
            "seconds": round(time.perf_counter() - started, 3),
        })
    return results


def _manager_from_args(args: argparse.Namespace) -> GenerationManager:
    return GenerationManager(args.generations_dir, args.pointer, args.lock)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generations-dir", type=Path, required=True)
    parser.add_argument("--pointer", type=Path)
    parser.add_argument("--lock", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status")
    activate = subparsers.add_parser("activate")
    activate.add_argument("generation")
    activate.add_argument("--database", type=Path)
    activate.add_argument("--manifest", type=Path)
    rollback = subparsers.add_parser("rollback")
    rollback.add_argument("generation", nargs="?")
    args = parser.parse_args(argv)
    manager = _manager_from_args(args)
    if args.command == "status":
        result = manager.status()
    elif args.command == "activate":
        result = manager.activate(args.generation, args.database, args.manifest).__dict__
        result["database_path"] = str(result["database_path"])
        result["manifest_path"] = str(result["manifest_path"])
    else:
        result = manager.rollback(args.generation).__dict__
        result["database_path"] = str(result["database_path"])
        result["manifest_path"] = str(result["manifest_path"])
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
