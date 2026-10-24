"""Generation-scoped offline ordinary-component intervals, never Synergy CIs.

The serial snapshot builder computes a complete component population once per
normalized scope/kind. Only small final statistics enter SQLite; table-level
observations stay in DuckDB and may spill within the existing memory ceiling.
Interactive requests keep the independently tested public component endpoint.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import time

from phase4_combo_mw_contracts import EXCLUDED_PROJECTS, _quoted, _round_clause
from phase4_local_scope import normalize_scope, scope_predicates

def _measure_population(sink, kind, telemetry, scope):
    """Resource window for one population query (labels: kind and scope SIZE only,
    never the filter values themselves)."""
    from phase5_refresh_metrics import measure_resources
    return measure_resources(sink, 'component_population', kind=kind, telemetry=bool(telemetry),
                                 scope_keys=len(scope) if hasattr(scope, '__len__') else None)


FIELDS = ('mean', 'ci95_low', 'ci95_high', 'ci95_se', 'ci95_n', 'ci95_cluster_n')


class OfflineComponentCIs:
    def __init__(self, store, path: Path):
        self.store = store
        # The build creates a fresh private cache. A killed/retried candidate
        # cannot reuse statistics from a different code/input validation attempt.
        self.database = sqlite3.connect(str(path))
        self.database.execute('CREATE TABLE IF NOT EXISTS components '
                              '(population TEXT, name TEXT, value TEXT, PRIMARY KEY(population,name))')
        self.database.execute('CREATE TABLE IF NOT EXISTS complete (population TEXT PRIMARY KEY)')
        self.database.execute('DELETE FROM components')
        self.database.execute('DELETE FROM complete')
        self.database.commit()
        self.population_queries = 0
        self.population_seconds = 0.0
        # Measurement only: how often values() is asked, and what each distinct
        # population cost (time and memory). Bounded by the number of populations.
        self.lookups = 0
        self.population_log = []

    def close(self):
        self.database.close()

    def values(self, request, *, telemetry: bool, kind: str, names):
        if kind not in {'card', 'action_card', 'endgame'}:
            raise ValueError('unsupported standalone component kind')
        self.lookups += 1
        scope = normalize_scope(request)
        population = json.dumps([scope, telemetry, kind], sort_keys=True, separators=(',', ':'))
        if not self.database.execute('SELECT 1 FROM complete WHERE population=?', [population]).fetchone():
            query, parameters = component_population_sql(request, telemetry=telemetry, kind=kind)
            started = time.perf_counter()
            with _measure_population(self.population_log, kind, telemetry, scope):
                result = self.store.query(query, parameters)
            self.population_seconds += time.perf_counter() - started
            rows = result['rows']
            # Catalogues are small; fail rather than retain an unexpected fact
            # expansion in Python. The cache never stores individual game rows.
            if len(rows) > 4096:
                raise RuntimeError('component population exceeded its catalogue bound')
            with self.database:
                self.database.executemany('INSERT INTO components VALUES (?,?,?)', [
                    (population, row['name'], json.dumps({field: row[field] for field in FIELDS}))
                    for row in rows])
                self.database.execute('INSERT INTO complete VALUES (?)', [population])
            self.population_queries += 1
        unavailable = {field: (0 if field in {'ci95_n', 'ci95_cluster_n'} else None) for field in FIELDS}
        values = {}
        for name in set(names):
            row = self.database.execute('SELECT value FROM components WHERE population=? AND name=?',
                                        [population, name]).fetchone()
            values[name] = json.loads(row[0]) if row else dict(unavailable)
        return values


def component_population_sql(request, *, telemetry: bool, kind: str):
    """Same distinct-event/null/cluster grain as component_ci_sql, without pairs."""
    scope = normalize_scope(request)
    predicates, parameters = scope_predicates(scope, 'g', hard_completed=False)
    eligible = 'JOIN mw_action_card_eligible_tables_narrow e USING(table_id)' if telemetry else ''
    scoped = f'''scoped_players AS MATERIALIZED (
      SELECT g.table_id,g.player,g.elo_delta,g.Map AS map_name
      FROM prepared_full_sample_narrow g {eligible} WHERE {predicates})'''
    if kind == 'card':
        excluded = ','.join(_quoted(value) for value in EXCLUDED_PROJECTS)
        rounds = _round_clause('cp', scope.get('rounds') or [])
        observations = f'''SELECT DISTINCT s.table_id,s.player,cp.card_name AS name,
            cp.card_type,s.map_name,s.elo_delta
          FROM scoped_players s JOIN card_play_narrow cp USING(table_id,player)
          WHERE NOT (cp.card_type='project' AND LOWER(cp.card_name) IN ({excluded})){rounds}'''
    elif kind == 'action_card':
        observations = '''SELECT a.table_id,a.card_key AS name,a.elo_delta
          FROM mw_action_card_selection_narrow a JOIN scoped_players s USING(table_id,player)'''
    elif kind == 'endgame':
        observations = '''SELECT e.table_id,e.endgame_name AS name,s.elo_delta
          FROM endgame_score_event_narrow e JOIN scoped_players s USING(table_id,player)'''
    else:
        raise ValueError('unsupported standalone component kind')
    return f'''WITH {scoped}, observations AS ({observations}), raw AS (
      SELECT name,table_id,COUNT(elo_delta) AS n,SUM(elo_delta) AS value_sum
      FROM observations GROUP BY name,table_id), means AS (
      SELECT name,SUM(n) AS total_n,SUM(value_sum)/NULLIF(SUM(n),0) AS mean
      FROM raw WHERE n>0 GROUP BY name), stats AS (
      SELECT m.name,m.mean,m.total_n,COUNT(r.table_id) AS cluster_n,
        CASE WHEN COUNT(r.table_id)>=2 THEN SQRT(
          COUNT(r.table_id)*1.0/(COUNT(r.table_id)-1)
          * SUM(POW((r.value_sum-r.n*m.mean)/m.total_n,2))) END AS se
      FROM means m JOIN raw r USING(name) WHERE r.n>0
      GROUP BY m.name,m.mean,m.total_n)
      SELECT name,mean,CASE WHEN cluster_n>=2 THEN mean-1.96*se END AS ci95_low,
        CASE WHEN cluster_n>=2 THEN mean+1.96*se END AS ci95_high,
        se AS ci95_se,total_n AS ci95_n,cluster_n AS ci95_cluster_n
      FROM stats ORDER BY name''', parameters
