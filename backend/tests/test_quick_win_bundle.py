"""Byte-preserving Arena assembly and qualified builder inventory."""
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import phase2_local_vertical_slice as builder
from phase5_snapshot_builder import _write_json, _write_json_file_members, _copy_private_json_object
from phase5_refresh_workflow import EXPECTED_RELATIONS
from phase5_refresh_dependencies import LOG_RELATIONS
from phase2_population_contract_gate import REQUIRED_EVENT_RELATIONS
import phase2_population_contract_gate as population_gate


class ArenaByteAssemblyTests(unittest.TestCase):
    def test_exact_bytes_unicode_floats_empty_and_large_members_without_parse(self):
        values = {'S1': {'name': 'é🐬\n"quoted"', 'values': [None, -0.0, 1e-30, 1.2345678901234567]},
                  'S2': {}, 'S3': {'history': ['é🐬']*180000}}
        header = {'status': 'ok', 'data_version': 'same', 'data': {}, 'count': 3}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            members = {}
            for key, value in values.items():
                path = root/(key+'.json')
                _write_json(path, value)
                members[key] = path
            expected = {**header, 'data': values}
            output = root/'assembled.json'
            with mock.patch('phase5_snapshot_builder.json.load', side_effect=AssertionError('must not parse a spool')):
                _write_json_file_members(output, header, 'data', members)
            self.assertEqual(output.read_bytes(),
                (json.dumps(expected, ensure_ascii=False, separators=(',', ':'))+os.linesep).encode('utf-8'))

    def test_private_spools_accept_writer_line_endings_and_reject_incomplete_files(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'member.json'
            for ending in (b'\n', b'\r\n'):
                path.write_bytes(b'{"x":1}'+ending)
                output = io.BytesIO()
                _copy_private_json_object(path, output)
                self.assertEqual(output.getvalue(), b'{"x":1}')
            for data in (b'', b'{', b'{"x":1}', b'[1]\n', b'{"x":'):
                path.write_bytes(data)
                with self.assertRaises(ValueError):
                    _copy_private_json_object(path, io.BytesIO())


class QuickWinInventoryTests(unittest.TestCase):
    def test_population_gate_accepts_later_cache_versions_without_losing_minimum(self):
        builder_text = ' '.join(REQUIRED_EVENT_RELATIONS | {
            'opponent_pre_match_elo','is_corrupted_game','is_completed_game',
            'starting_position','player_identity','arena_season','is_tournament'})
        workflow_text = 'materialize_metadata_tables(connection\n builder.run\n'+builder_text
        for version, invalid in ((8,False),(17,False),(18,False),(7,True)):
            root = mock.MagicMock()
            texts = {
                'phase2_local_vertical_slice.py':builder_text,
                'phase4_local_routes.py':'prepared_full_sample_narrow',
                'phase5_refresh_workflow.py':workflow_text,
                'phase3_duckdb_service.py':f'RESPONSE_CACHE_SCHEMA_VERSION = {version}\nrequest.get("players_history") is True',
            }
            root.__truediv__.side_effect = lambda name:mock.Mock(read_text=lambda **_:texts[name])
            with mock.patch.object(population_gate,'ROOT',root):
                self.assertEqual('response-cache schema was not invalidated' in population_gate._static_failures(),invalid)

    def test_removed_event_copies_do_not_displace_required_serving_or_validation_facts(self):
        retired = set(builder.RETIRED_EVENT_RELATIONS)
        self.assertTrue(retired.isdisjoint(EXPECTED_RELATIONS))
        self.assertTrue(retired.isdisjoint(LOG_RELATIONS))
        self.assertTrue(retired.isdisjoint(REQUIRED_EVENT_RELATIONS))
        self.assertIn('card_play_event_narrow', LOG_RELATIONS)
        self.assertTrue(set(builder.VALIDATION_ONLY_RELATIONS).isdisjoint(LOG_RELATIONS))
        self.assertTrue(set(builder.VALIDATION_ONLY_RELATIONS).isdisjoint(EXPECTED_RELATIONS))


if __name__ == '__main__':
    unittest.main()
