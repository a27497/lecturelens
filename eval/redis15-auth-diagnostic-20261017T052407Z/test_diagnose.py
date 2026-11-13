"""Synthetic checks; no real runtime configuration, Redis, or credentials."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('redis_metadata_diagnose', Path(__file__).with_name('diagnose.py'))
d = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(d)


def resp(value):
    if isinstance(value, int): return b':' + str(value).encode() + b'\r\n'
    if isinstance(value, list): return b'*' + str(len(value)).encode() + b'\r\n' + b''.join(map(resp, value))
    return b'$' + str(len(value)).encode() + b'\r\n' + value + b'\r\n'


class Tests(unittest.TestCase):
    def test_projection_does_not_decode_unselected_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'synthetic.json'
            p.write_text(json.dumps({'unused': {'nested': ['DO_NOT_DECODE', {'x': '\\"}[]'}]},
                                     'REDIS_HOST': 'localhost', 'other': 123, 'REDIS_PORT': '16379',
                                     'REDIS_PASSWORD': 'synthetic-only', 'tail': None}))
            original = json.loads

            def checked(value, *args, **kwargs):
                self.assertNotIn('DO_NOT_DECODE', value)
                return original(value, *args, **kwargs)

            with patch.object(d.json, 'loads', checked):
                selected = d.project_json(p, {'REDIS_HOST', 'REDIS_PORT', 'REDIS_PASSWORD'})
            self.assertEqual(selected, {'REDIS_HOST': 'localhost', 'REDIS_PORT': '16379', 'REDIS_PASSWORD': 'synthetic-only'})

    def test_duplicate_selected_field_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'duplicate.json'
            p.write_text('{"REDIS_PORT":"16379","REDIS_PORT":"1"}')
            with self.assertRaises(d.Gate): d.project_json(p, {'REDIS_PORT'})

    def run_fake(self, replies, port='16379'):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root / '.data/live-access/runtime.json'
            runtime.parent.mkdir(parents=True)
            runtime.write_text(json.dumps({'REDIS_HOST': 'localhost', 'REDIS_PORT': port, 'REDIS_PASSWORD': 'synthetic-only'}))
            authorization = root / 'eval/p2-1b-pipeline-20261016T122904Z/redis-reuse-authorization.json'
            authorization.parent.mkdir(parents=True)
            authorization.write_text(json.dumps({'database': 15, 'allowed_existing_key': 'synthetic-authorized'}))
            calls = []

            class FakeSocket:
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def getpeername(self): return ('127.0.0.1', 16379)
                def makefile(self, *args): return io.BytesIO(replies)
                def sendall(self, payload): calls.append(payload.split(b'\r\n')[2].decode())

            with patch.object(d, 'ROOT', root), patch.object(d, 'HERE', root), \
                 patch.object(d.socket, 'create_connection', return_value=FakeSocket()) as connection, \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                status = d.diagnose()
            result = json.loads((root / 'redis-metadata.json').read_text())
            self.assertNotIn('synthetic-only', output.getvalue())
            self.assertNotIn('synthetic-authorized', (root / 'redis-metadata.json').read_text())
            return status, result, calls, connection.call_count

    def test_three_complete_scans_deduplicate_and_compare(self):
        replies = b'+OK\r\n+OK\r\n'
        for _ in range(3):
            replies += resp(2) + resp([b'9', [b'synthetic-authorized', b'other']]) + resp([b'0', [b'other']])
            replies += resp(b'string') + resp(-1) + resp(b'string') + resp(120) + resp(2)
        status, result, calls, connections = self.run_fake(replies)
        self.assertEqual(status, 0)
        self.assertEqual(connections, 1)
        self.assertEqual(calls.count('SCAN'), 6)
        for scan in result['scans']:
            self.assertTrue(scan['complete'])
            self.assertEqual((scan['unique_count'], scan['duplicates'], scan['pages']), (2, 1, 2))
            self.assertEqual(scan['unexpected_unique_count'], 1)
        self.assertTrue(result['scans'][1]['matches_previous_key_set'])

    def test_auth_failure_does_not_select_or_retry(self):
        status, result, calls, connections = self.run_fake(b'-WRONGPASS synthetic-error\r\n')
        self.assertEqual(status, 2)
        self.assertEqual(result['code'], 'REDIS_AUTH_FAILED')
        self.assertEqual(calls, ['AUTH'])
        self.assertEqual(connections, 1)

    def test_target_mismatch_never_connects(self):
        status, result, calls, connections = self.run_fake(b'', port='1')
        self.assertEqual(status, 2)
        self.assertEqual(result['code'], 'TARGET_MISMATCH')
        self.assertEqual((calls, connections), ([], 0))

    def test_permission_failure_stops_before_scan(self):
        status, result, calls, _ = self.run_fake(b'+OK\r\n+OK\r\n-NOPERM synthetic-error\r\n')
        self.assertEqual(status, 2)
        self.assertEqual(result['code'], 'REDIS_NOPERM')
        self.assertEqual(calls, ['AUTH', 'SELECT', 'DBSIZE'])

    def test_archived_task_projection_handles_sql_array_and_object(self):
        spec = importlib.util.spec_from_file_location('provenance_check', Path(__file__).with_name('provenance.py'))
        provenance = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(provenance)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'archived.json'
            task = {'id': 'synthetic-task', 'status': 'FAILED', 'unselected': 'DO_NOT_DECODE'}
            for value in ([task], task, []):
                with self.subTest(array=isinstance(value, list), empty=value == []):
                    p.write_text(json.dumps({'task': value, 'calls': [{'body': 'DO_NOT_DECODE'}]}))
                    original = json.loads

                    def checked(raw, *args, **kwargs):
                        self.assertNotIn('DO_NOT_DECODE', raw)
                        return original(raw, *args, **kwargs)

                    with patch.object(provenance.json, 'loads', checked):
                        meta = provenance.task_fields(p)
                    self.assertEqual(meta, {} if value == [] else {'id': 'synthetic-task', 'status': 'FAILED'})


if __name__ == '__main__':
    unittest.main()
