"""Compare private rebuilt artifacts without retaining both Arena bundles.

Only generated/execution metadata is ignored. Counts, ordering, labels, values,
nulls and all ordinary confidence-interval fields remain comparison inputs.
Float tolerance covers accumulation noise, not displayed-unit differences.
"""
import argparse
import json
import math
from itertools import groupby
from pathlib import Path

VOLATILE = {'generated_at', 'cache_status', 'query_seconds', 'build_seconds',
            'execution_seconds', 'release_version'}
RELATIVE_TOLERANCE = 2e-12
AUTHORIZED_GENERATION_CHANGE = None


class JSONReader:
    """Standard-library incremental values; Arena season is the bounded grain."""
    def __init__(self, handle):
        self.handle, self.buffer, self.position, self.eof = handle, '', 0, False
        self.decoder = json.JSONDecoder()

    def fill(self):
        self.buffer = self.buffer[self.position:]
        self.position = 0
        chunk = self.handle.read(1024*1024)
        self.buffer += chunk
        self.eof = not chunk

    def char(self):
        while True:
            while self.position < len(self.buffer) and self.buffer[self.position].isspace():
                self.position += 1
            if self.position < len(self.buffer):
                return self.buffer[self.position]
            if self.eof:
                return ''
            self.fill()

    def expect(self, expected):
        if self.char() != expected:
            raise ValueError('malformed JSON separator')
        self.position += 1

    def value(self):
        self.char()
        while True:
            try:
                value, end = self.decoder.raw_decode(self.buffer, self.position)
                # A numeric token may continue in the next input chunk.
                if end == len(self.buffer) and not self.eof:
                    self.fill()
                    continue
                self.position = end
                return value
            except json.JSONDecodeError:
                if self.eof:
                    raise
                self.fill()

    def entries(self, nested_data=False):
        self.expect('{')
        first = True
        while self.char() != '}':
            if not first:
                self.expect(',')
            first = False
            key = self.value()
            if not isinstance(key, str):
                raise ValueError('JSON object key is not a string')
            self.expect(':')
            if nested_data and key == 'data':
                for season, value in self.entries():
                    yield 'data/'+season, value
            else:
                yield key, self.value()
        self.expect('}')


def read_home_bootstrap(path):
    """Parse the fixed two-assignment wrapper without executing JavaScript."""
    source = path.read_text(encoding='utf-8')
    decoder = json.JSONDecoder()
    first = 'window.__ARK_NOVA_DATA_VERSION__='
    second = ';window.__ARK_NOVA_HOME_DEFAULTS__='
    if not source.startswith(first):
        raise ValueError('unknown Home bootstrap wrapper')
    version, position = decoder.raw_decode(source, len(first))
    if not source.startswith(second, position):
        raise ValueError('unknown Home bootstrap assignment')
    defaults, position = decoder.raw_decode(source, position + len(second))
    if source[position:] != ';':
        raise ValueError('unexpected Home bootstrap suffix')
    return {'data_version': version, 'defaults': defaults}


def _actual_rounding_tie(left, right):
    before, after = left.get('delta_actual'), right.get('delta_actual')
    raw_before, raw_after = left.get('delta_actual_ci_mean'), right.get('delta_actual_ci_mean')
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool)
               for value in (before, after, raw_before, raw_after)):
        return False
    if left.get('delta_actual_ci_n') != right.get('delta_actual_ci_n'):
        return False
    raw = (raw_before+raw_after)/2
    return (math.isclose(raw_before, raw_after, rel_tol=1e-12, abs_tol=1e-12)
            and math.isclose(abs(before-after), .001, rel_tol=0, abs_tol=1e-12)
            and math.isclose(abs(raw-before), .0005, rel_tol=0, abs_tol=1e-12)
            and math.isclose(abs(raw-after), .0005, rel_tol=0, abs_tol=1e-12))


def compare(left, right, path, differences, rounding_ties=None, rounding_proofs=None):
    if (AUTHORIZED_GENERATION_CHANGE is not None
        and path.split('/')[-1] == 'generation'
        and (left, right) == AUTHORIZED_GENERATION_CHANGE):
        return
    if isinstance(left, dict) and isinstance(right, dict):
        keys = (set(left) | set(right))-VOLATILE
        for key in sorted(keys):
            if key not in left or key not in right:
                differences.append(path+'/'+key+': missing field')
            else:
                mean_key = 'delta_actual' if key == 'delta_actual' else 'delta_round' if key == 'delta_round' else None
                tie_left = (left if mean_key != 'delta_round' else {
                    'delta_actual': left.get('delta_round'), 'delta_actual_ci_mean': left.get('delta_round_ci_mean'),
                    'delta_actual_ci_n': left.get('delta_round_ci_n')})
                tie_right = (right if mean_key != 'delta_round' else {
                    'delta_actual': right.get('delta_round'), 'delta_actual_ci_mean': right.get('delta_round_ci_mean'),
                    'delta_actual_ci_n': right.get('delta_round_ci_n')})
                if (mean_key and left[key] != right[key] and rounding_ties is not None
                        and _actual_rounding_tie(tie_left, tie_right)):
                    rounding_ties.append({'path': path+'/'+key, 'before': left[key], 'after': right[key],
                        'raw_before': tie_left['delta_actual_ci_mean'], 'raw_after': tie_right['delta_actual_ci_mean'],
                        'count': tie_left['delta_actual_ci_n']})
                    continue
                full_path = path+'/'+key
                proof = (rounding_proofs or {}).get(full_path)
                if (proof and proof.get('verified') is True and rounding_ties is not None
                        and left[key] == proof.get('before') and right[key] == proof.get('after')):
                    rounding_ties.append(proof)
                    continue
                compare(left[key], right[key], full_path, differences, rounding_ties, rounding_proofs)
    elif isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            differences.append(path+': list length differs')
        for index, (old, new) in enumerate(zip(left, right)):
            compare(old, new, path+'/'+str(index), differences, rounding_ties, rounding_proofs)
    elif type(left) is bool or type(right) is bool:
        if type(left) is not type(right) or left != right:
            differences.append(path+': boolean differs')
    elif isinstance(left, (int, float)) and isinstance(right, (int, float)):
        if not math.isclose(left, right, rel_tol=RELATIVE_TOLERANCE, abs_tol=1e-12):
            differences.append(path+f': number differs ({left!r} != {right!r})')
    elif left != right:
        differences.append(path+': value differs')
    if len(differences) > 20:
        raise ValueError('more than twenty artifact differences')


def compare_arena(old, new, differences, rounding_ties=None, rounding_proofs=None):
    with old.open(encoding='utf-8') as left, new.open(encoding='utf-8') as right:
        old_entries = JSONReader(left).entries(nested_data=True)
        new_entries = JSONReader(right).entries(nested_data=True)
        sentinel = object()
        while True:
            old_item, new_item = next(old_entries, sentinel), next(new_entries, sentinel)
            if old_item is sentinel or new_item is sentinel:
                if old_item is not new_item:
                    differences.append('Arena: missing top-level member')
                break
            if old_item[0] != new_item[0]:
                differences.append('Arena: member order/key differs')
            elif old_item[0] not in VOLATILE:
                compare(old_item[1], new_item[1], old_item[0], differences, rounding_ties, rounding_proofs)


def normalize_record_ties(before, after):
    """Exact row multisets only within the existing four-column ORDER BY ties."""
    key = lambda row: tuple(row.get(name) for name in ('n', 'turns', 'player', 'table_id'))
    # groupby iterators must be consumed before advancing to the next group.
    def groups(rows):
        return [(identity, list(group)) for identity, group in groupby(rows, key)]
    old_groups, new_groups = groups(before), groups(after)
    if len(old_groups) != len(new_groups):
        return before, after, []
    normalized_old, normalized_new, changes = [], [], []
    ordering = lambda row: json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    for (old_key, old_rows), (new_key, new_rows) in zip(old_groups, new_groups):
        if old_key != new_key or len(old_rows) != len(new_rows):
            return before, after, []
        if old_rows != new_rows:
            sorted_old, sorted_new = sorted(old_rows, key=ordering), sorted(new_rows, key=ordering)
            if sorted_old != sorted_new:
                return before, after, []
            old_rows, new_rows = sorted_old, sorted_new
            changes.append({'order_key': old_key, 'rows': len(old_rows)})
        normalized_old.extend(old_rows)
        normalized_new.extend(new_rows)
    return normalized_old, normalized_new, changes


def main():
    global AUTHORIZED_GENERATION_CHANGE
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--object-key')
    parser.add_argument('--rounding-proof', type=Path)
    parser.add_argument('--allow-generation-change', action='store_true',
                        help='Reconcile generation identities from both complete release manifests')
    args = parser.parse_args()
    if args.allow_generation_change:
        identities = [json.loads((folder/'release-manifest.json').read_text())
                      for folder in (args.baseline,args.candidate)]
        if identities[0]['data_version'] != identities[1]['data_version']:
            raise ValueError('numerical comparison requires the same data version')
        AUTHORIZED_GENERATION_CHANGE = tuple(item['generation'] for item in identities)
    if args.object_key:
        key = Path(args.object_key)
        if key.is_absolute() or '..' in key.parts:
            raise ValueError('invalid object key')
        old = {args.object_key: args.baseline/key}
        new = {args.object_key: args.candidate/key}
    else:
        baseline = json.loads((args.baseline/'release-manifest.json').read_text())
        candidate = json.loads((args.candidate/'release-manifest.json').read_text())
        old = {item['object_key']: Path(item['path']) for item in baseline['artifacts']}
        new = {item['object_key']: Path(item['path']) for item in candidate['artifacts']}
    if set(old) != set(new):
        raise ValueError('artifact inventories differ')
    checks = []
    proofs = {}
    if args.rounding_proof:
        supplied = json.loads(args.rounding_proof.read_text())
        if supplied.get('status') != 'ok' or not all(item.get('verified') for item in supplied['proofs']):
            raise ValueError('rounding proof is not verified')
        proofs = {item['path']: item for item in supplied['proofs']}
    for key in sorted(old):
        if key.endswith('default-pack.json'):
            # Separately validated inventory/hash/schema; every member below is
            # compared directly. Avoid decoding two entire duplicated packs.
            continue
        differences = []
        rounding_ties = []
        tied_order_changes = []
        try:
            if key.endswith('arena-top-100/all-seasons.json'):
                compare_arena(old[key], new[key], differences, rounding_ties, proofs)
            elif key.endswith('.json'):
                with old[key].open(encoding='utf-8') as source:
                    before = json.load(source)
                with new[key].open(encoding='utf-8') as source:
                    after = json.load(source)
                if '/records/most-icons/' in key:
                    before['data'], after['data'], tied_order_changes = normalize_record_ties(before['data'], after['data'])
                compare(before, after, key, differences, rounding_ties, proofs)
                del before, after
            elif key == 'card-stats/home/defaults.js':
                compare(read_home_bootstrap(old[key]), read_home_bootstrap(new[key]),
                        key, differences, rounding_ties, proofs)
            elif old[key].read_bytes() != new[key].read_bytes():
                differences.append('non-JSON artifact bytes differ')
        except Exception as error:
            differences.append(type(error).__name__+': '+str(error))
        checks.append({'object_key': key, 'status': 'ok' if not differences else 'failed',
                       'differences': differences, 'classified_half_rounding_ties': rounding_ties,
                       'classified_tied_order_changes': tied_order_changes})
        args.report.write_text(json.dumps({'status': 'running', 'checks': checks}, indent=2)+'\n')
    result = {'status': 'ok' if all(item['status'] == 'ok' for item in checks) else 'failed',
              'partial': bool(args.object_key),
              'authorized_generation_change': AUTHORIZED_GENERATION_CHANGE,
              'classified_half_rounding_tie_count': sum(len(item['classified_half_rounding_ties']) for item in checks),
              'classified_tied_order_groups': sum(len(item['classified_tied_order_changes']) for item in checks),
              'checked_artifacts': len(checks), 'float_relative_tolerance': RELATIVE_TOLERANCE,
              'float_absolute_tolerance': 1e-12, 'checks': checks}
    args.report.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'checks'}))
    if result['status'] != 'ok':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
