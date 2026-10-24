"""Candidate derivative tools must never mutate serving/rollback databases."""
import json
import shutil
import uuid
from pathlib import Path
import unittest
from phase5_rebuild_filter_relations import candidate_paths


class CandidateRebuildSafety(unittest.TestCase):
    def setUp(self):
        self.root=Path(__file__).resolve().parents[1] / '.test-temp' / ('candidate-safety-'+uuid.uuid4().hex)
        self.root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_only_existing_unprotected_generation_is_writable(self):
        with self.subTest('candidate boundary'):
            root=self.root
            generations=root / 'phase2_private_data' / 'generations'; generations.mkdir(parents=True)
            serving=root / 'phase3_private_serving'; serving.mkdir()
            (serving / 'current.json').write_text(json.dumps({'generation':'active','previous_generation':'rollback'}),encoding='utf-8')
            for generation in ('active','rollback','candidate'):
                (generations / (generation+'.duckdb')).write_bytes(b'fixture')
                (generations / (generation+'.manifest.json')).write_text('{}',encoding='utf-8')
            for generation in ('active','rollback'):
                with self.assertRaises(RuntimeError):
                    candidate_paths(root,generation)
            with self.assertRaises(ValueError):
                candidate_paths(root,'../../active')
            with self.assertRaises(FileNotFoundError):
                candidate_paths(root,'missing')
            self.assertEqual(candidate_paths(root,'candidate')[0],generations / 'candidate.duckdb')
