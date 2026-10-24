"""Exact Cards moments without request-time DISTINCT table/card hashing.

The refresh stores both focal players separately. Maps, Elo, starting position,
and every other predicate are evaluated for each side before their moments are
pooled. A table contributes at most once to Played/Seen, but repeated played
rounds retain their original weight in EV and its ordinary sample interval.
"""
from phase4_local_scope import scope_predicates


SIDE_FIELDS = (
    'map_name', 'game_ended_at', 'starting_position', 'pre_match_elo',
    'opponent_pre_match_elo', 'elo_delta', 'is_completed_game', 'arena_season',
    'is_arena_game', 'is_tournament',
)
CARD_COUNTS = ('played_count', 'played_r1', 'played_r2', 'played_r3',
               'played_r4', 'played_r5', 'played_r6plus', 'in_hand', 'seen')
MOMENT_FIELDS = ('played_n','played_sum','played_sumsq','pre_match_n','pre_match_sum',
                 'hand_n','hand_sum','hand_sumsq','n_played','n_seen')


def create_cards_pooled_relations(connection):
    """Numeric-key moments for tables whose two focal sides both qualify.

    The source table's arbitrary Map is never copied or queried. Eligibility is
    decided from the exact two-sided metadata. Partially eligible tables retain
    separate-side moments, so no symmetric-population assumption is made.
    """
    counts={}
    for suffix in ('mw','base'):
        name=f'cards_pair_pooled_fact_{suffix}_narrow'
        connection.execute(f'DROP TABLE IF EXISTS {name}')
        source=f'card_filter_table_fact_{suffix}_narrow'
        required=[source,f'cards_pair_scope_{suffix}_narrow']
        if connection.execute('SELECT COUNT(*) FROM duckdb_tables() WHERE table_name IN (?,?)',required).fetchone()[0]!=2:
            continue
        fields=', '.join('c.'+field for field in MOMENT_FIELDS)
        connection.execute(f'''CREATE TABLE {name} AS
          SELECT s.table_key,k.card_id,{fields} FROM {source} c
          JOIN cards_pair_scope_{suffix}_narrow s USING(table_id)
          JOIN card_catalog_narrow k USING(card_name)
          ORDER BY s.table_key,k.card_id''')
        counts[name]=int(connection.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0])
    return counts


def paired_side_scope_sql(request):
    """Expose independently filtered focal rows from the two-sided metadata."""
    suffix = 'mw' if int(request['is_mw']) == 1 else 'base'
    selects, parameters = [], []
    for side in (0, 1):
        predicate, values = scope_predicates(request, 's', include_corrupted=True)
        for field in ('Map', *SIDE_FIELDS[1:]):
            predicate = predicate.replace(f's.{field}', f's.{field}_{side}')
        parameters.extend(values)
        selects.append(f'''SELECT s.table_id, {side}::UTINYINT AS side,
          (s.table_key * 2 + {side})::INTEGER AS player_key,
          s.elo_delta_{side} AS elo_delta, s.pre_match_elo_{side} AS pre_match_elo
          FROM cards_pair_scope_{suffix}_narrow s WHERE {predicate or 'TRUE'}''')
    return ' UNION ALL '.join(selects), parameters


def create_combo_card_pair_relations(connection, excluded_projects=()):
    """Expand deduplicated pairs once, using narrow IDs and round bitmasks.

    The request filters both cards' played rounds independently. Storing a mask
    per card avoids losing the pair when the cards matched different selected
    rounds. No Synergy interval or request-time pair self-join is introduced.
    """
    counts = {}
    excluded = ', '.join("'" + value.replace("'", "''") + "'" for value in sorted(excluded_projects))
    card_where = f"WHERE NOT (c.card_type='project' AND LOWER(c.card_name) IN ({excluded}))" if excluded else ''
    for suffix, dataset in (('mw', 1), ('base', 0)):
        relation = f'combo_card_pair_fact_{suffix}_narrow'
        connection.execute(f'DROP TABLE IF EXISTS {relation}')
        available = connection.execute('SELECT COUNT(*) FROM duckdb_tables() WHERE table_name=?',
                                       [f'cards_pair_scope_{suffix}_narrow']).fetchone()[0]
        if not available:
            continue
        connection.execute('DROP TABLE IF EXISTS combo_pair_cards')
        mask = ' + '.join(f'CASE WHEN c.{column}>0 THEN {1 << i} ELSE 0 END'
                          for i, column in enumerate(CARD_COUNTS[1:7]))
        connection.execute(f'''CREATE TEMP TABLE combo_pair_cards AS
          WITH ranked AS (
            SELECT table_id, player,
              (ROW_NUMBER() OVER (PARTITION BY table_id ORDER BY player)-1)::UTINYINT AS side
            FROM game_player_narrow WHERE is_mw={dataset} AND NOT is_corrupted_game
          ) SELECT (s.table_key * 2 + g.side)::INTEGER AS player_key,
            c.card_id, ({mask})::UTINYINT AS round_mask
          FROM card_play_filter_fact_{suffix}_narrow c JOIN ranked g USING(table_id,player)
          JOIN cards_pair_scope_{suffix}_narrow s USING(table_id)
          {card_where}''')
        query = '''SELECT a.player_key, a.card_id AS card_1, b.card_id AS card_2,
            a.round_mask AS round_mask_1, b.round_mask AS round_mask_2
          FROM combo_pair_cards a JOIN combo_pair_cards b USING(player_key)
          WHERE a.card_id<b.card_id AND a.card_id>=? AND a.card_id<?'''
        connection.execute(f'CREATE TABLE {relation} AS {query}', [0, 0])
        maximum = connection.execute('SELECT COALESCE(MAX(card_id),0) FROM card_catalog_narrow').fetchone()[0]
        for first in range(1, maximum + 1, 32):
            connection.execute(f'INSERT INTO {relation} {query}', [first, first + 32])
        connection.execute('DROP TABLE combo_pair_cards')
        counts[relation] = int(connection.execute(f'SELECT COUNT(*) FROM {relation}').fetchone()[0])
    return counts




def create_cards_pair_scope(connection, suffix, dataset, *, batch_size=65536):
    """Build fresh two-sided metadata with bounded wide ranking/pivot memory.

    Validate the entire population first, then assign globally ordered keys.
    Batches preserve exact player ordering, nulls and both sides' filter fields.
    ``None`` retains the unbounded algorithm for independent qualification.
    The same producer is used for fresh builds and reusable-fact refreshes.
    """
    if batch_size is not None and (type(batch_size) is not int or batch_size < 1):
        raise ValueError('batch_size must be a positive integer or None')
    scope_name = f'cards_pair_scope_{suffix}_narrow'
    connection.execute(f'DROP TABLE IF EXISTS {scope_name}')
    invalid = connection.execute(f'''SELECT COUNT(*) FROM (
      SELECT table_id FROM game_player_narrow
      WHERE is_mw={dataset} AND NOT is_corrupted_game
      GROUP BY table_id HAVING COUNT(*)<>2 OR COUNT(DISTINCT player)<>2
    )''').fetchone()[0]
    if invalid:
        return False
    fields = ', '.join(
        f'MAX({field}) FILTER (WHERE side={side}) AS {"Map" if field == "map_name" else field}_{side}'
        for side in (0, 1) for field in SIDE_FIELDS
    )
    if batch_size is not None:
        index = f'cards_pair_index_{suffix}_scratch'
        connection.execute(f'DROP TABLE IF EXISTS {index}')
        try:
            connection.execute(f'''CREATE TEMP TABLE {index} AS
              SELECT (ROW_NUMBER() OVER (ORDER BY table_id)-1)::INTEGER AS table_key,
                table_id
              FROM (SELECT DISTINCT table_id FROM game_player_narrow
                    WHERE is_mw={dataset} AND NOT is_corrupted_game)''')
            query = f'''WITH ranked AS (
              SELECT i.table_key,g.table_id,{", ".join("g."+field for field in SIDE_FIELDS)},
                ROW_NUMBER() OVER (PARTITION BY g.table_id ORDER BY g.player)-1 AS side
              FROM game_player_narrow g JOIN {index} i
                ON g.table_id IS NOT DISTINCT FROM i.table_id
              WHERE g.is_mw={dataset} AND NOT g.is_corrupted_game
                AND i.table_key>=? AND i.table_key<?
            ) SELECT table_key,table_id,{dataset}::BIGINT AS is_mw,{fields}
              FROM ranked GROUP BY table_key,table_id ORDER BY table_key'''
            connection.execute(f'CREATE TABLE {scope_name} AS {query}', [0,0])
            total = connection.execute(f'SELECT COUNT(*) FROM {index}').fetchone()[0]
            for first in range(0,total,batch_size):
                connection.execute(f'INSERT INTO {scope_name} {query}',
                                   [first,first+batch_size])
        except BaseException:
            connection.execute(f'DROP TABLE IF EXISTS {scope_name}')
            raise
        finally:
            connection.execute(f'DROP TABLE IF EXISTS {index}')
        return True
    connection.execute(f'''CREATE TABLE {scope_name} AS
      WITH ranked AS (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY table_id ORDER BY player)-1 AS side
        FROM game_player_narrow WHERE is_mw={dataset} AND NOT is_corrupted_game
      ), pooled AS (
        SELECT table_id, {dataset}::BIGINT AS is_mw, {fields}
        FROM ranked GROUP BY table_id
      ) SELECT (ROW_NUMBER() OVER (ORDER BY table_id)-1)::INTEGER AS table_key,
        * FROM pooled''')
    return True
def create_cards_pair_relations(connection):
    """Bound build memory by numeric-card batches; keep an exact slow fallback.

    The paired representation requires two distinct source players per table.
    If that invariant does not hold, omit the capability rather than silently
    dropping observations. The canonical player/card facts remain authoritative.
    """
    counts = {}
    for suffix, dataset in (('mw', 1), ('base', 0)):
        scope_name = f'cards_pair_scope_{suffix}_narrow'
        fact_name = f'cards_pair_fact_{suffix}_narrow'
        connection.execute(f'DROP TABLE IF EXISTS {fact_name}')
        if not create_cards_pair_scope(connection, suffix, dataset):
            continue
        connection.execute('DROP TABLE IF EXISTS cards_pair_player_side')
        connection.execute(f'''CREATE TEMP TABLE cards_pair_player_side AS
          SELECT g.table_id, g.player, s.table_key,
            ROW_NUMBER() OVER (PARTITION BY g.table_id ORDER BY g.player)-1 AS side
          FROM game_player_narrow g JOIN {scope_name} s USING(table_id)
          WHERE g.is_mw={dataset} AND NOT g.is_corrupted_game''')
        pivot = ', '.join(
            f'COALESCE(MAX(c.{field}) FILTER (WHERE g.side={side}), 0)::USMALLINT AS {field}_{side}'
            for side in (0, 1) for field in CARD_COUNTS
        )
        query = f'''SELECT g.table_key, k.card_id, {pivot}
          FROM card_filter_fact_{suffix}_narrow c
          JOIN cards_pair_player_side g USING(table_id, player)
          JOIN card_catalog_narrow k USING(card_name)
          WHERE k.card_id>=? AND k.card_id<? GROUP BY g.table_key, k.card_id
          ORDER BY g.table_key,k.card_id'''
        connection.execute(f'CREATE TABLE {fact_name} AS {query}', [0, 0])
        maximum = connection.execute('SELECT COALESCE(MAX(card_id),0) FROM card_catalog_narrow').fetchone()[0]
        for first in range(1, maximum + 1, 32):
            connection.execute(f'INSERT INTO {fact_name} {query}', [first, first + 32])
        connection.execute('DROP TABLE cards_pair_player_side')
        counts[scope_name] = int(connection.execute(f'SELECT COUNT(*) FROM {scope_name}').fetchone()[0])
        counts[fact_name] = int(connection.execute(f'SELECT COUNT(*) FROM {fact_name}').fetchone()[0])
    counts.update(create_cards_pooled_relations(connection))
    return counts


def cards_pair_sql(request, excluded_projects):
    suffix = 'mw' if int(request['is_mw']) == 1 else 'base'
    predicates, parameters = [], []
    for side in (0, 1):
        predicate, values = scope_predicates(request, 's', include_corrupted=True)
        for field in ('Map', *SIDE_FIELDS[1:]):
            predicate = predicate.replace(f's.{field}', f's.{field}_{side}')
        predicates.append(predicate or 'TRUE')
        parameters.extend(values)
    rounds = request.get('rounds') or []
    round_columns = {'1': 'played_r1', '2': 'played_r2', '3': 'played_r3',
                     '4': 'played_r4', '5': 'played_r5', '6+': 'played_r6plus'}
    played = [' + '.join(f'c.{round_columns[r]}_{side}' for r in rounds)
              if rounds else f'c.played_count_{side}' for side in (0, 1)]
    weights = ', '.join(
        f'CASE WHEN s.eligible_{i} AND s.delta_valid_{i} THEN CAST(({played[i]}) AS INTEGER) ELSE 0 END AS p{i}, '
        f'CASE WHEN s.eligible_{i} AND s.delta_valid_{i} AND c.in_hand_{i}>0 THEN 1 ELSE 0 END AS h{i}'
        for i in (0, 1)
    )
    moments = {
        'played_n': ('SUM', 'p0+p1'),
        'played_sum': ('FSUM', 'CASE WHEN p0+p1>0 THEN p0*delta_0+p1*delta_1 ELSE 0 END'),
        'played_sumsq': ('FSUM', 'CASE WHEN p0+p1>0 THEN p0*delta_sq_0+p1*delta_sq_1 ELSE 0 END'),
        'pre_match_n': ('SUM', 'p0*pre_valid_0+p1*pre_valid_1'),
        'pre_match_sum': ('FSUM', 'CASE WHEN p0+p1>0 THEN p0*pre_0+p1*pre_1 ELSE 0 END'),
        'hand_n': ('SUM', 'h0+h1'),
        'hand_sum': ('FSUM', 'CASE WHEN h0+h1>0 THEN h0*delta_0+h1*delta_1 ELSE 0 END'),
        'hand_sumsq': ('FSUM', 'CASE WHEN h0+h1>0 THEN h0*delta_sq_0+h1*delta_sq_1 ELSE 0 END'),
    }
    aggregates = ', '.join(f'{aggregate}({expression}) AS {key}' for key, (aggregate, expression) in moments.items())
    excluded = ', '.join("'" + value.replace("'", "''") + "'" for value in sorted(excluded_projects))
    show_context = not rounds
    use_pooled=bool(request.get('_cards_pair_pooled_fact')) and show_context
    # Round-restricted views hide Hand/Seen, so nonplayed table/card rows cannot
    # contribute to any output. Prune them before the dominant metadata join.
    played_where = f'WHERE ({played[0]})>0 OR ({played[1]})>0' if rounds else ''
    side_values = ', '.join(
        f'COALESCE(s.elo_delta_{i},0) AS delta_{i}, '
        f'COALESCE(s.elo_delta_{i}*s.elo_delta_{i},0) AS delta_sq_{i}, '
        f'(s.elo_delta_{i} IS NOT NULL) AS delta_valid_{i}, '
        f'COALESCE(s.pre_match_elo_{i},0) AS pre_{i}, '
        f'CAST(s.pre_match_elo_{i} IS NOT NULL AS INTEGER) AS pre_valid_{i}'
        for i in (0, 1)
    )
    def sample_sd(prefix):
        count = 'played_n' if prefix == 'played' else 'hand_n'
        centered = f'({prefix}_sumsq - {prefix}_sum * {prefix}_sum / NULLIF({count},0))'
        scale = f'GREATEST(ABS({prefix}_sumsq), ABS({prefix}_sum * {prefix}_sum / NULLIF({count},0)))'
        # Subtracting two nearly equal raw second moments can leave a few ULPs
        # for a constant sample. Clamp only that machine-roundoff envelope,
        # not a statistical variance threshold. Samples with n<2 remain null.
        residual = f'CASE WHEN ABS({centered}) <= 3.552713678800501e-15 * {scale} THEN 0 ELSE GREATEST({centered},0) END'
        return f'SQRT(({residual}) / (CASE WHEN {count}>1 THEN {count}-1 END))'
    partial_filter='AND NOT (eligible_0 AND eligible_1)' if use_pooled else ''
    pooling=''
    if use_pooled:
        expressions=', '.join(f'{"FSUM" if field.endswith(("sum","sumsq")) else "SUM"}(c.{field}) AS {field}' for field in MOMENT_FIELDS)
        combined=', '.join(f'{"FSUM" if field.endswith(("sum","sumsq")) else "SUM"}({field}) AS {field}' for field in MOMENT_FIELDS)
        pooling=f''', pooled AS (
          SELECT c.card_id,{expressions} FROM cards_pair_pooled_fact_{suffix}_narrow c
          JOIN sides s USING(table_key) WHERE s.eligible_0 AND s.eligible_1
          GROUP BY c.card_id
        ), moments AS (
          SELECT card_id,{combined} FROM (
            SELECT * FROM partial_moments UNION ALL SELECT * FROM pooled
          ) GROUP BY card_id
        )'''
    moment_name='partial_moments' if use_pooled else 'moments'
    return f'''WITH sides AS MATERIALIZED (SELECT * FROM (
      SELECT s.table_key, {side_values},
        COALESCE(({predicates[0]}), FALSE) AS eligible_0,
        COALESCE(({predicates[1]}), FALSE) AS eligible_1
      FROM cards_pair_scope_{suffix}_narrow s
      ) eligible_sides WHERE eligible_0 OR eligible_1
    ), selected AS (
      SELECT * FROM sides WHERE (eligible_0 OR eligible_1) {partial_filter}
    ), weighted AS (
      SELECT c.card_id, s.* EXCLUDE(table_key), {weights},
        ((s.eligible_0 AND c.seen_0>0) OR (s.eligible_1 AND c.seen_1>0)) AS seen
      FROM cards_pair_fact_{suffix}_narrow c JOIN selected s USING(table_key)
      {played_where}
    ), {moment_name} AS (
      SELECT card_id, {aggregates},
        SUM(CAST(p0>0 OR p1>0 AS BIGINT)) AS n_played,
        SUM(CAST(seen AS BIGINT)) AS n_seen
      FROM weighted GROUP BY card_id
    ){pooling} SELECT k.card_name, k.card_type,
      ROUND(played_sum / played_n, 3) AS delta_played,
      {"ROUND(hand_sum / NULLIF(hand_n,0), 3)" if show_context else "CAST(NULL AS DOUBLE)"} AS delta_in_hand,
      played_sum / played_n AS delta_played_ci_mean,
      {sample_sd('played')} AS delta_played_ci_sd,
      played_n AS delta_played_ci_n,
      {"hand_sum / NULLIF(hand_n,0)" if show_context else "CAST(NULL AS DOUBLE)"} AS delta_in_hand_ci_mean,
      {sample_sd('hand') if show_context else "CAST(NULL AS DOUBLE)"} AS delta_in_hand_ci_sd,
      {"hand_n" if show_context else "CAST(0 AS BIGINT)"} AS delta_in_hand_ci_n,
      ROUND(pre_match_sum / NULLIF(pre_match_n,0),0) AS avg_elo, n_played,
      {"n_seen" if show_context else "CAST(NULL AS BIGINT)"} AS n_seen,
      {"ROUND(100.0 * n_played / NULLIF(n_seen,0),2)" if show_context else "CAST(NULL AS DOUBLE)"} AS playrate_pct,
      CAST(NULL AS DOUBLE) AS avg_cp
      FROM moments m JOIN card_catalog_narrow k USING(card_id)
      WHERE played_n>0 AND NOT (k.card_type='project' AND LOWER(k.card_name) IN ({excluded}))
      ORDER BY card_type, playrate_pct DESC NULLS LAST, n_played DESC, card_name
      LIMIT ? OFFSET ?''', parameters
