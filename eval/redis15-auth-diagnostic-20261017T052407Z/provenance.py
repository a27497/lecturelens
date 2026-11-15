#!/usr/bin/env python3
"""Offline archived-task metadata projection; no Redis/configuration access."""
import ast
import collections
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SPEC = importlib.util.spec_from_file_location('metadata_diagnose', HERE / 'diagnose.py')
d = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(d)

# Reuse the tested streaming reader without decoding the surrounding task record.
project = next(x for x in ast.parse((HERE / 'diagnose.py').read_text()).body
               if isinstance(x, ast.FunctionDef) and x.name == 'project_json')
reader = next(x for x in project.body if isinstance(x, ast.ClassDef))
scope = {'json': json, 'require': d.require}
exec(compile(ast.Module(body=[reader], type_ignores=[]), str(HERE / 'diagnose.py'), 'exec'), scope)
Reader = scope['Reader']


def task_fields(path):
    fields = {'id', 'task_id', 'taskId', 'status', 'created_at', 'createdAt', 'updated_at', 'updatedAt'}
    selected = {}

    def object_members(r, nested=False):
        ch = r.nonspace()
        if ch == '}': return
        while True:
            d.require(ch == '"', 'ARCHIVE_KEY_SHAPE')
            key = r.value(ch, True)
            d.require(r.nonspace() == ':', 'ARCHIVE_SHAPE')
            ch = r.nonspace()
            if not nested and key == 'task':
                # Archived SQL fetchall results wrap the one task row in an array.
                if ch == '[':
                    ch = r.nonspace()
                    if ch != ']':
                        d.require(ch == '{', 'ARCHIVE_TASK_SHAPE')
                        object_members(r, nested=True)
                        d.require(r.nonspace() == ']', 'ARCHIVE_TASK_COUNT')
                elif ch == '{':
                    object_members(r, nested=True)
                else:
                    r.value(ch, False)
            else:
                keep = nested and key in fields
                value = r.value(ch, keep)
                if keep: selected[key] = value
            ch = r.nonspace()
            if ch == '}': return
            d.require(ch == ',', 'ARCHIVE_SHAPE')
            ch = r.nonspace()

    with path.open() as f:
        r = Reader(f)
        d.require(r.nonspace() == '{', 'ARCHIVE_SHAPE')
        object_members(r)
    return selected


def main():
    metadata = json.loads((HERE / 'redis-metadata.json').read_text())
    indexed = {}
    for task_id, paths in d.task_index().items():
        for path in paths:
            digest = hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()
            meta = task_fields(path)
            matches = any(isinstance(meta.get(k), str) and meta[k].encode() == task_id
                          for k in ('id', 'task_id', 'taskId'))
            status = meta.get('status')
            indexed[digest] = dict(group=path.parent.parent.name, internal_task_identifier_match=matches,
                archived_status=status if status in {'PENDING', 'QUEUED', 'RUNNING', 'PROCESSING', 'SUCCEEDED',
                    'SUCCESS', 'COMPLETED', 'FAILED', 'CANCELLED', 'CANCELED'} else 'UNCLASSIFIED',
                metadata_field_names=sorted(meta))
    entries = []
    for item in metadata['scans'][0]['keys']:
        proofs = []
        for evidence in item['evidence']:
            digest = evidence['record_sha256']
            if digest in indexed:
                proofs.append(dict(record_sha256=digest, **indexed[digest]))
        confirmed = any(p['internal_task_identifier_match'] for p in proofs)
        entries.append(dict(id=item['id'], authorized_history_match=item['authorized_history_match'],
            ownership='ARCHIVED_ISOLATED_TASK_IDENTIFIER_CONFIRMED' if confirmed else 'UNKNOWN', evidence=proofs))
    output = dict(redis_access=False, configuration_access=False,
                  limit='Identifier provenance only; Redis values, writer process and account ownership not inspected',
                  ownership_counts=dict(collections.Counter(e['ownership'] for e in entries)), entries=entries)
    with (HERE / 'provenance.json').open('x') as f:
        json.dump(output, f, indent=2)
        f.write('\n')
    print(json.dumps(output['ownership_counts']))


if __name__ == '__main__':
    main()
