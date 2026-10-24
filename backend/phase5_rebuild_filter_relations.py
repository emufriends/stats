"""Rebuild optimized filter relations in an inactive candidate generation."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from phase2_local_vertical_slice import (
    create_card_filter_fact_relation,
    create_card_table_filter_relations,
    create_players_metrics_relation,
    create_card_action_pair_filter_relation,
    EXCLUDED_PROJECTS,
)
from phase3_duckdb_service import _load_duckdb, GENERATION_RE
from phase3_cards_pair_contracts import create_cards_pair_relations, create_combo_card_pair_relations


def candidate_paths(root: Path, generation: str) -> tuple[Path, Path]:
    """Fail before opening a database if the target is active or rollback."""
    if not GENERATION_RE.fullmatch(generation):
        raise ValueError('invalid candidate generation identifier')
    generations = (root / 'phase2_private_data' / 'generations').resolve()
    database = generations / f'{generation}.duckdb'
    manifest = generations / f'{generation}.manifest.json'
    if database.is_symlink() or database.resolve().parent != generations:
        raise RuntimeError('candidate database is outside the generations directory')
    pointer = json.loads((root / 'phase3_private_serving' / 'current.json').read_text(encoding='utf-8'))
    if generation in (pointer.get('generation'), pointer.get('previous_generation')):
        raise RuntimeError('refusing to mutate an active or rollback generation')
    if not database.is_file() or not manifest.is_file():
        raise FileNotFoundError('candidate database and manifest must already exist')
    return database, manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/home/ascri"))
    parser.add_argument("--generation", required=True)
    parser.add_argument(
        "--table-facts-only",
        action="store_true",
        help="Build only the compact table-grain Cards relations.",
    )
    args = parser.parse_args()
    database, manifest_path = candidate_paths(args.root, args.generation)
    if shutil.disk_usage(database.parent).free < 2 * 1024**3:
        raise RuntimeError('at least 2 GiB free is required for a candidate rebuild')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest.setdefault('release', {})['status'] = 'candidate_requires_revalidation'
    # Invalidate publication eligibility before any mutation, including a
    # failed or interrupted rebuild. Existing snapshot hashes no longer prove
    # the modified database and must be regenerated/reconciled separately.
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True)+'\n',encoding='utf-8')
    duckdb = _load_duckdb()
    connection = duckdb.connect(str(database))
    try:
        connection.execute("SET threads=1")
        connection.execute("SET memory_limit='2000MB'")
        connection.execute("SET max_temp_directory_size='512MB'")
        pair_rows = {}
        if args.table_facts_only:
            create_card_table_filter_relations(connection)
            players = connection.execute(
                "SELECT COUNT(*) FROM players_by_identity_narrow"
            ).fetchone()[0]
            cards = connection.execute("""
                SELECT
                  (SELECT COUNT(*) FROM card_filter_fact_mw_narrow)
                  + (SELECT COUNT(*) FROM card_filter_fact_base_narrow)
            """).fetchone()[0]
        else:
            players = create_players_metrics_relation(connection, rebuild_base=False)
            cards = create_card_filter_fact_relation(connection)
            pair_rows = create_cards_pair_relations(connection)
            pair_rows.update(create_combo_card_pair_relations(connection, EXCLUDED_PROJECTS))
            action_pair_rows = create_card_action_pair_filter_relation(connection)
            pair_rows['card_action_pair_filter_fact_narrow'] = action_pair_rows
        cohorts = connection.execute(
            "SELECT COUNT(*) FROM players_default_cohorts_narrow"
        ).fetchone()[0]
        card_mw = connection.execute(
            "SELECT COUNT(*) FROM card_filter_fact_mw_narrow"
        ).fetchone()[0]
        card_base = connection.execute(
            "SELECT COUNT(*) FROM card_filter_fact_base_narrow"
        ).fetchone()[0]
        card_table_mw = connection.execute(
            "SELECT COUNT(*) FROM card_filter_table_fact_mw_narrow"
        ).fetchone()[0]
        card_table_base = connection.execute(
            "SELECT COUNT(*) FROM card_filter_table_fact_base_narrow"
        ).fetchone()[0]
        connection.execute("CHECKPOINT")
    finally:
        connection.close()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    relations = manifest["builder"]["relations"]
    relations["players_by_identity_narrow"] = {"rows": int(players)}
    relations["players_default_cohorts_narrow"] = {"rows": int(cohorts)}
    relations.pop("card_filter_fact_narrow", None)
    relations["card_filter_fact_mw_narrow"] = {"rows": int(card_mw)}
    relations["card_filter_fact_base_narrow"] = {"rows": int(card_base)}
    relations["card_filter_table_fact_mw_narrow"] = {"rows": int(card_table_mw)}
    relations["card_filter_table_fact_base_narrow"] = {"rows": int(card_table_base)}
    for name, rows in pair_rows.items():
        relations[name] = {'rows':int(rows), **({'schema_version':2} if name != 'card_action_pair_filter_fact_narrow' else {})}
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"players": players, "cohorts": cohorts, "cards": cards}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
