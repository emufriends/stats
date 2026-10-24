"""Conservative reuse of immutable log-population derivatives.

Reuse requires identical producer inputs, Logs data/schema and every canonical
Full Sample row belonging to a logged table. Two-sided scopes are rebuilt and
numeric table keys must match for all logged tables. Late arrivals, corrections,
deletions, changed corruption/completion/identity/telemetry or shifted keys
therefore fall back to the exact full builder. MW-only/full-population facts
and Home/Players are always rebuilt; immutable parent files are never modified.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from phase3_cards_pair_contracts import create_cards_pair_scope
from phase5_operational_controls import _runtime_code_paths, sha256_file


LOG_RELATIONS = (
    'card_play_event_narrow', 'card_play_narrow',
    'card_log_narrow', 'card_in_hand_narrow', 'card_seen_narrow', 'card_catalog_narrow',
    'opening_hand_narrow', 'endgame_score_event_narrow', 'conservation_cp_player_narrow',
    'conservation_cp_opportunity_narrow',
    *tuple(f'{prefix}_{suffix}_narrow' for suffix in ('mw','base') for prefix in (
        'card_filter_fact','card_filter_table_fact','card_play_filter_fact',
        'cards_pair_fact','cards_pair_pooled_fact','combo_card_pair_fact')),
)

# Root the inventory in the actual producers, not snapshot/publication modules.
# Follow local imports too so new producer helpers fail closed. A shared route
# module imported for builder catalogues remains conservatively file-versioned.
LOG_PRODUCER_INPUTS = ('phase2_local_vertical_slice.py',
                       'phase3_cards_pair_contracts.py', 'cards_attributes.csv')


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',',':'), default=str).encode()).hexdigest()


def _row_multiset_digest(connection, relation, predicate='TRUE'):
    # Fixed-width SHA-256 hashes, sorted with multiplicity intact and fetched in
    # bounded chunks. The query may spill; never concatenate wide rows in Python.
    cursor = connection.execute(f'SELECT sha256(to_json(r)) AS row_hash FROM {relation} r WHERE {predicate} ORDER BY row_hash')
    digest = hashlib.sha256()
    rows = 0
    while chunk := cursor.fetchmany(4096):
        for (row_hash,) in chunk:
            digest.update(row_hash.encode('ascii'))
            rows += 1
    return {'rows': rows, 'sha256': digest.hexdigest()}


def log_dependency_signature(connection, source_manifest=None):
    root = Path(__file__).resolve().parent
    code = sorted((p.relative_to(root).as_posix(), sha256_file(p))
                  for p in _runtime_code_paths(root, LOG_PRODUCER_INPUTS))
    source = json.loads(Path(source_manifest).read_text()) if source_manifest else {}
    log_files = sorted((f['name'],f['bytes'],f['sha256']) for f in source.get('files',[]) if f['name'].startswith('logs-'))
    logs = {'files': log_files} if log_files else _row_multiset_digest(connection,'source_logs')
    prepared = _row_multiset_digest(connection,'prepared_full_sample_narrow',
                                   'table_id IN (SELECT table_id FROM source_logs)')
    # Include compact canonical values too: the wide relation does not expose
    # every compact alias/type used in Cards, Opening Hand and action histories.
    compact = _row_multiset_digest(connection,'game_player_narrow',
                                  'table_id IN (SELECT table_id FROM source_logs)')
    schemas = {table: connection.execute(f'DESCRIBE {table}').fetchall() for table in (
        'source_logs','prepared_full_sample_narrow','game_player_narrow')}
    return {'schema_version':2,
            'engine_version':connection.execute('SELECT version()').fetchone()[0],
            'producer_sha256':_digest(code),
            'population_sha256':_digest({'logs':logs,'prepared':prepared,'compact':compact,'schemas':schemas})}


def reuse_log_relations(connection, previous_database, previous_report, signature, decision=None):
    def record(reason, **details):
        if decision is not None:
            decision.update(reason=reason, **details)
    prior = previous_report.get('log_dependency') or {}
    if not previous_database or not prior:
        record('no_qualified_parent')
        return None
    if prior != signature:
        record('dependency_changed', changed=[key for key in signature if prior.get(key) != signature[key]])
        return None
    quoted = str(Path(previous_database).resolve()).replace("'", "''")
    connection.execute(f"ATTACH '{quoted}' AS reuse_parent (READ_ONLY)")
    try:
        available = {row[0] for row in connection.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_catalog='reuse_parent' AND table_schema='main'"
        ).fetchall()}
        scopes = {f'cards_pair_scope_{s}_narrow' for s in ('mw','base')}
        if not set(LOG_RELATIONS).union(scopes).issubset(available):
            record('missing_parent_relations')
            return None
        for suffix, dataset in (('mw',1),('base',0)):
            if not create_cards_pair_scope(connection,suffix,dataset):
                record('malformed_two_player_scope', dataset=suffix)
                return None
            name = f'cards_pair_scope_{suffix}_narrow'
            shifted = connection.execute(f'''SELECT COUNT(*) FROM (
                SELECT COALESCE(a.table_id,b.table_id) AS table_id,
                    a.table_key AS old_key,b.table_key AS new_key
                FROM reuse_parent.{name} a FULL OUTER JOIN main.{name} b USING(table_id)
                WHERE COALESCE(a.table_id,b.table_id) IN (SELECT table_id FROM source_logs)
                  AND a.table_key IS DISTINCT FROM b.table_key)''').fetchone()[0]
            if shifted:
                record('shifted_numeric_table_keys', dataset=suffix, count=shifted)
                return None
        for name in LOG_RELATIONS:
            connection.execute(f'DROP TABLE IF EXISTS main.{name}')
            connection.execute(f'CREATE TABLE main.{name} AS SELECT * FROM reuse_parent.{name}')
        cards, combos = {}, {}
        for suffix in ('mw','base'):
            for prefix in ('cards_pair_scope','cards_pair_fact','cards_pair_pooled_fact'):
                name=f'{prefix}_{suffix}_narrow'
                cards[name]=int(connection.execute(f'SELECT COUNT(*) FROM main.{name}').fetchone()[0])
            name=f'combo_card_pair_fact_{suffix}_narrow'
            combos[name]=int(connection.execute(f'SELECT COUNT(*) FROM main.{name}').fetchone()[0])
        record('reused', relation_count=len(LOG_RELATIONS))
        return cards,combos
    finally:
        connection.execute('DETACH reuse_parent')
