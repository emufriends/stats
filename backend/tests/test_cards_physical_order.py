"""Storage ordering must not change observations or touch serving generations."""
import json
from pathlib import Path
import shutil
import unittest
import uuid
from phase3_duckdb_service import _load_duckdb
from phase5_order_cards_facts import order


class CardsPhysicalOrderTests(unittest.TestCase):
    def test_order_preserves_exact_duplicates_and_invalidates_candidate_release(self):
        root = Path(__file__).resolve().parents[1] / '.test-temp' / ('order-' + uuid.uuid4().hex)
        private = root / 'phase2_private_data'
        generations = private / 'generations'; generations.mkdir(parents=True)
        (private / 'staging').mkdir()
        serving = root / 'phase3_private_serving'; serving.mkdir()
        (serving / 'current.json').write_text('{"generation":"active","previous_generation":"previous"}')
        names = [f'{prefix}_{dataset}_narrow' for dataset in ('mw', 'base')
                 for prefix in ('cards_pair_fact', 'cards_pair_pooled_fact')]
        manifest = {'generation': 'candidate', 'builder': {'relations': {name: {} for name in names}},
                    'release': {'status': 'validated'}}
        manifest_path = generations / 'candidate.manifest.json'
        manifest_path.write_text(json.dumps(manifest))
        try:
            connection = _load_duckdb().connect(str(generations / 'candidate.duckdb'))
            for name in names:
                connection.execute(f'CREATE TABLE {name} AS SELECT * FROM '
                    '(VALUES (2,3,0.25),(1,1,NULL),(2,3,0.25)) t(table_key,card_id,value)')
            connection.close()
            result = order(root, 'candidate')
            self.assertEqual(result['status'], 'ok')
            self.assertTrue(all(row['rows'] == 3 and row['exact_multiset_differences'] == 0
                                for row in result['relations']))
            self.assertEqual(json.loads(manifest_path.read_text())['release']['status'],
                             'candidate_requires_revalidation')
            self.assertEqual(json.loads((serving / 'current.json').read_text())['generation'], 'active')
        finally:
            shutil.rmtree(root)


if __name__ == '__main__':
    unittest.main()
