import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import phase5_refresh_workflow as workflow


class RefreshMemoryBudgetTests(unittest.TestCase):
    def invoke_until_source(self, *, isolate, incremental=False, source_budget=None):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            source=root/'source'
            source.mkdir()
            (source/'manifest.json').write_text(json.dumps({'generation':'source-new'}))
            previous=SimpleNamespace(generation_id='old',manifest={'refresh_fingerprint':'old'},
                database_path=root/'old.duckdb',data_version='v-old')
            manager=mock.Mock()
            manager.current.return_value=previous
            with mock.patch.object(workflow,'GenerationManager',return_value=manager), \
                 mock.patch.object(workflow,'refresh_inputs',return_value={'fingerprint':'new'}), \
                 mock.patch.object(workflow,'validate_reusable_candidate',return_value=None), \
                 mock.patch.object(workflow,'prune_local_releases',return_value={}), \
                 mock.patch.object(workflow,'prune_source_exports',return_value={}), \
                 mock.patch.object(workflow,'ensure_refresh_headroom',return_value={}), \
                 mock.patch.object(workflow,'invoke_offline_stage',side_effect=RuntimeError('source test stop')) as child, \
                 mock.patch.object(workflow,'materialize_source',side_effect=RuntimeError('source test stop')) as full, \
                 mock.patch.object(workflow,'reconcile_source',side_effect=RuntimeError('source test stop')) as delta:
                with self.assertRaises(RuntimeError):
                    workflow.refresh(root=root,source_root=source,generation_id='new',
                        builder_path=root/'app/builder.py',arena_settings=root/'arena.csv',
                        moving_source_dir=root/'moving',memory_limit='800MB',
                        source_memory_limit=source_budget,isolate_stages=isolate,
                        incremental_source=incremental,activate_release=False)
                if isolate:
                    config=child.call_args.args[1]
                    self.assertEqual(config['incremental_source'],incremental)
                    return config['memory_limit']
                return (delta if incremental else full).call_args.kwargs['memory_limit']

    def test_source_budget_is_independent_in_every_import_mode(self):
        for isolate,incremental in ((True,False),(True,True),(False,False),(False,True)):
            with self.subTest(isolate=isolate,incremental=incremental):
                self.assertEqual(self.invoke_until_source(isolate=isolate,
                    incremental=incremental,source_budget='600MB'),'600MB')

    def test_unspecified_source_budget_keeps_builder_budget_default(self):
        self.assertEqual(self.invoke_until_source(isolate=True),'800MB')


if __name__=='__main__':
    unittest.main()
