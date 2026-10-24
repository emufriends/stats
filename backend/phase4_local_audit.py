"""Read-only readiness audit for the private Phase 4 DuckDB port.

This module deliberately does not activate routes or mutate a generation.  It
records which local relations and metadata are available, then combines that
with the request adapter's route inventory.  A missing prerequisite is a
porting blocker, not permission to fall back to a wide Full Sample scan.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from phase3_duckdb_service import (
    PHASE3_PAGE_CATALOG,
    PHASE4_NATIVE_ROUTES,
    Phase3RequestAdapter,
    _load_duckdb,
)


REQUIRED_RELATIONS = (
    "source_full_sample",
    "source_logs",
    "game_player_narrow",
    "card_play_narrow",
    "corrupted_tables_narrow",
    "arena_roster_narrow",
    "records_manual_narrow",
    "records_elo_leaderboard_narrow",
)

METADATA_RELATIONS = {
    "arena_seasons": "arena_seasons_metadata",
    "tournament_tables": "tournament_tables_metadata",
}


def _table_names(connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main'"
        ).fetchall()
    }


def audit_generation(database: str | Path) -> dict[str, Any]:
    """Return a JSON-safe audit for one immutable DuckDB generation."""

    database = str(database)
    duckdb = _load_duckdb()
    connection = duckdb.connect(database, read_only=True)
    try:
        tables = _table_names(connection)
        missing_relations = [name for name in REQUIRED_RELATIONS if name not in tables]
        metadata = {
            key: {"relation": relation, "present": relation in tables}
            for key, relation in METADATA_RELATIONS.items()
        }
    finally:
        connection.close()

    capabilities = Phase3RequestAdapter.capabilities()
    pending = [
        f"{page}/{view}"
        for page, views in PHASE3_PAGE_CATALOG.items()
        for view in views
        if next(
            item["status"]
            for page_info in capabilities["pages"]
            if page_info["stats_page"] == page
            for item in page_info["views"]
            if item["view"] == view
        ) not in {"native_phase3", "native_phase4"}
    ]
    blockers = list(missing_relations)
    blockers.extend(
        f"missing metadata relation: {relation}"
        for metadata_item in metadata.values()
        for relation in [metadata_item["relation"]]
        if not metadata_item["present"]
    )
    if pending:
        blockers.append(f"{len(pending)} route contracts still pending")
    return {
        "status": "ready" if not blockers else "partial",
        "database": database,
        "required_relations": {
            name: name in tables for name in REQUIRED_RELATIONS
        },
        "independent_card_references": {
            "mode": "on_demand_scratch_database",
            "command": "python phase5_cardcard_reconcile.py <inactive-generation.duckdb>",
            "not_required_for_serving": True,
        },
        "missing_relations": missing_relations,
        "metadata": metadata,
        "native_phase4_routes": sorted(
            f"{page}/{view}" for page, view in PHASE4_NATIVE_ROUTES
        ),
        "pending_routes": pending,
        "blockers": blockers,
        "capabilities": {
            "native_route_count": capabilities["native_route_count"],
            "phase4_pending_route_count": capabilities["phase4_pending_route_count"],
        },
        "notes": [
        "Arena-season and tournament filters require imported metadata.",
        "The Arena season bundle requires arena_roster_narrow; roster identity is joined by player_id.",
        "Manual Records spreadsheet rows are imported into the immutable generation with source hashes.",
            "Page-specific log projections must be compact before activation.",
            "No additive Synergy or combination confidence intervals are in scope.",
        ],
    }
