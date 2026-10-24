"""Independent unrounded Card+Card check; source read-only, disk scratch.

Fixed historical default scope. No serving fact builds a reference value.
Nulls and counts are exact; independent unrounded reductions allow only
1e-12 + 2e-12 relative floating-point reduction noise. Before/after snapshot
bytes are a separate mandatory gate: rounding at exact half steps can amplify
harmless final-bit reduction differences in independent reference algorithms.
"""
from pathlib import Path
import re
import tempfile

from phase3_duckdb_service import Phase3RequestAdapter, _load_duckdb
from phase4_combo_mw_contracts import combination_sql, CARD_PAIR_TYPE_SQL
from phase5_card_validation_references import create_validation_references, validation_scoped_sql
from phase2_local_vertical_slice import VALID_MAPS


def compare_results(c):
    fields = [r[0] for r in c.execute('DESCRIBE observed').fetchall()]
    if fields != [r[0] for r in c.execute('DESCRIBE expected').fetchall()]:
        raise ValueError('Reference/serving field inventory differs')
    for name in ('expected','observed'):
        if c.execute(f'''SELECT COUNT(*) FROM (SELECT card_1,card_2 FROM {name}
            GROUP BY ALL HAVING COUNT(*)<>1)''').fetchone()[0]:
            raise ValueError('Duplicate reconciliation pair keys')
    expressions = []
    for field in fields:
        same = f'a.{field} IS NOT DISTINCT FROM b.{field}'
        if field in ('delta_1','delta_2','delta_combined','delta_actual',
                     'delta_actual_ci_mean','delta_actual_ci_sd','interaction','avg_elo'):
            same = f'''({same} OR (a.{field} IS NOT NULL AND b.{field} IS NOT NULL
                AND isfinite(a.{field}) AND isfinite(b.{field})
                AND abs(a.{field}-b.{field}) <= 1e-12 +
                    2e-12*greatest(abs(a.{field}),abs(b.{field}))))'''
        expressions.append(f'COUNT(*) FILTER (WHERE NOT ({same})) AS {field}')
    row = c.execute(f'''SELECT COUNT(*) FILTER (WHERE a.__present IS NULL
        OR b.__present IS NULL) AS missing_pairs,{','.join(expressions)}
        FROM (SELECT *,TRUE AS __present FROM expected) a FULL OUTER JOIN
             (SELECT *,TRUE AS __present FROM observed) b
        ON a.card_1 IS NOT DISTINCT FROM b.card_1
        AND a.card_2 IS NOT DISTINCT FROM b.card_2''').fetchone()
    return {'status':'pass' if not any(row) else 'fail',
            'expected_rows':c.execute('SELECT COUNT(*) FROM expected').fetchone()[0],
            'observed_rows':c.execute('SELECT COUNT(*) FROM observed').fetchone()[0],
            'differences':dict(zip(('missing_pairs',*fields),row))}


def reconcile(database, *, threads=1, memory_limit='600MB'):
    database = Path(database).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='card-reference-') as folder:
        c = _load_duckdb().connect(str(Path(folder)/'references.duckdb'))
        try:
            c.execute('SET threads=?',[threads])
            c.execute('SET preserve_insertion_order=false')
            c.execute('SET memory_limit=?',[memory_limit])
            c.execute('SET temp_directory=?',[str(Path(folder)/'spill')])
            quoted = str(database).replace("'","''")
            c.execute(f"ATTACH '{quoted}' AS audited (READ_ONLY)")
            canonical = {'card_play_narrow','game_player_narrow','corrupted_tables_narrow'}
            for name in sorted(canonical):
                c.execute(f'CREATE VIEW {name} AS SELECT * FROM audited.main.{name}')
            counts = create_validation_references(c)
            # Keep all-null components present, as in the public Combo query.
            # The historical table-moment diagnostic excludes these groups and
            # therefore cannot by itself provide the complete component domain.
            c.execute(f'''CREATE TEMP TABLE reference_components AS
                WITH scoped AS ({validation_scoped_sql()})
                SELECT is_mw,card_name,AVG(elo_delta) AS delta
                FROM scoped GROUP BY is_mw,card_name''')
            # STDDEV_SAMP avoids cancellation when a constant/near-constant
            # sample's raw sum of squares is reduced independently. No serving
            # fact participates in this reference query.
            c.execute(f'''CREATE TEMP TABLE reference_pair_ci AS
                WITH scoped AS ({validation_scoped_sql()})
                SELECT a.is_mw,a.card_name AS card_1,b.card_name AS card_2,
                    STDDEV_SAMP(a.elo_delta) AS sd
                FROM scoped a JOIN scoped b ON a.table_id=b.table_id
                    AND a.player=b.player AND a.is_mw=b.is_mw
                    AND a.card_name<b.card_name GROUP BY ALL''')
            present = {r[0] for r in c.execute("SELECT table_name FROM information_schema.tables WHERE table_catalog='audited'").fetchall()}
            # These views serve only the observed query, never the reference SQL.
            for name in sorted(present-canonical-set(counts)):
                escaped = name.replace('"','""')
                c.execute(f'CREATE VIEW "{escaped}" AS SELECT * FROM audited.main."{escaped}"')
            results = []
            for dataset,suffix in ((1,'mw'),(0,'base')):
                request = Phase3RequestAdapter.normalize_request({
                    'stats_page':'combinations','combinations_view':'card_card','is_mw':dataset,
                    'maps':list(VALID_MAPS),'date_from':'2025-01-01',
                    'player_elo_min':300,'opponent_elo_min':300,'completed_only':False})
                request['_combos_filter_fact'] = f'card_filter_fact_{suffix}_narrow' in present
                request['_combos_played_fact'] = f'card_play_filter_fact_{suffix}_narrow' in present
                request['_combo_card_pair_fact'] = {f'combo_card_pair_fact_{suffix}_narrow',f'cards_pair_scope_{suffix}_narrow'}.issubset(present)
                request['_combo_card_component_pair_fact'] = request['_combo_card_pair_fact'] and f'cards_pair_fact_{suffix}_narrow' in present
                sql,params = combination_sql(request,'card_card')
                # Validate raw statistics, not independently rounded half-step
                # values. This transforms only the audit query, not serving SQL.
                sql = re.sub(r'ROUND\(([^()]*)\s*,\s*[03]\)', r'(\1)', sql)
                c.execute('DROP TABLE IF EXISTS observed')
                c.execute('CREATE TEMP TABLE observed AS '+sql,[*params,2147483647,0])
                c.execute('DROP TABLE IF EXISTS expected')
                c.execute(f'''CREATE TEMP TABLE expected AS
                    WITH components AS (SELECT * FROM reference_components WHERE is_mw={dataset}),
                    p AS (SELECT *,delta_sum/NULLIF(delta_count,0) AS actual
                        FROM card_pair_aggregate_narrow WHERE is_mw={dataset})
                    SELECT p.card_1,p.type_1,p.card_2,p.type_2,
                        c1.delta AS delta_1,c2.delta AS delta_2,
                        c1.delta+c2.delta AS delta_combined,
                        p.actual AS delta_actual,p.actual AS delta_actual_ci_mean,
                        reference_pair_ci.sd AS delta_actual_ci_sd,
                        p.delta_count AS delta_actual_ci_n,
                        p.actual-c1.delta-c2.delta AS interaction,
                        p.elo_sum/NULLIF(p.elo_count,0) AS avg_elo,
                        p.observation_count AS n_played,{CARD_PAIR_TYPE_SQL} AS pair_type
                    FROM p JOIN components c1 ON c1.card_name=p.card_1
                    JOIN components c2 ON c2.card_name=p.card_2
                    JOIN reference_pair_ci ON reference_pair_ci.is_mw=p.is_mw
                        AND reference_pair_ci.card_1=p.card_1
                        AND reference_pair_ci.card_2=p.card_2''')
                results.append({'is_mw':dataset,**compare_results(c)})
            return {'status':'pass' if all(r['status']=='pass' for r in results) else 'fail',
                    'source_read_only':True,'reference_rows':counts,'datasets':results,
                    'scope':{'maps':list(VALID_MAPS),'date_from':'2025-01-01',
                             'player_elo_min':300,'opponent_elo_min':300,'completed_only':False}}
        finally:
            c.close()
