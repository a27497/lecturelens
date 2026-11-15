"""Offline reproduction summary. Never creates tasks, changes bindings or calls providers."""
import argparse
import collections
import hashlib
import json
import re
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(__file__).resolve().parent / 'p13d'
RAW = ROOT / '.data/baseline-deepseek-20261015T185735Z/p13d'


def load(name, private=False):
    return json.loads(((RAW if private else OUT) / name).read_text())


def summarize():
    complete = load('COMPLETE.json')
    rows = load('diagnostics.json')
    originals = {r['id']: r for r in load('diagnostics-with-excerpts.json', True)}
    snapshots = load('snapshots.json')
    assert complete['new_tasks'] == 1
    assert all(s['configVersion'] == 10 and s['routes']['TRANSLATION_FULL_TEXT']['source'] == 'DATABASE'
               and s['routes']['TRANSLATION_FULL_TEXT']['model'] == 'deepseek-flash' for s in snapshots)
    assert load('catalog-before.json') == load('catalog-after.json'), 'Configuration changed'
    disks = [json.loads(l) for l in (OUT / 'disk.jsonl').read_text().splitlines()]
    assert max(x['percent'] for x in disks) <= 85
    counts = collections.Counter()
    samples = []
    for row in rows:
        assert row['config_version'] == 10 and row['task_id'] == complete['task_id']
        label = row['provider_reason'] if row['provider_reason'] != 'PASSED' else row['validation_reason'] or 'VALIDATION_NOT_REACHED'
        counts[label] += 1
        raw = originals[row['id']]['response_excerpt']
        assert raw is None or (len(raw) <= 4000 and hashlib.sha256(raw.encode()).hexdigest() == row['excerpt_sha256'])
        assert raw is None or not re.search(r'\bsk-[A-Za-z0-9_-]{12,}|Bearer\s+[A-Za-z0-9._~-]{12,}', raw)
        if row['provider_reason'] != 'PASSED' or row['validation_reason'] != 'PASSED':
            content = re.search(r'"content"\s*:\s*(null|"(?:\\.|[^"\\])*")', raw or '')
            content = json.loads(content[1]) if content else None
            samples.append({'id': row['id'], 'provider_reason': row['provider_reason'],
                            'finish_reason': row['finish_reason'], 'http_status': row['http_status'],
                            'content_type_from_excerpt': type(content).__name__,
                            'reasoning_content_nonempty_in_excerpt': bool(re.search(r'"reasoning_content"\s*:\s*"[^"]', raw or '')),
                            'content_chars_from_excerpt': len(content) if isinstance(content, str) else None,
                            'completion_tokens': row['completion_tokens'], 'total_tokens': row['total_tokens']})
    stage_ms, request_parameters = {}, {}
    for line in load('task-log.json', True):
        event = re.search(r'event=pipeline_step_(?:completed|failed).*stepName=(\S+).*durationMillis=(\d+)', line)
        if event:
            stage_ms[event[1]] = int(event[2])
        if 'event=llm_aligned_batch_translation_started ' in line:
            request_parameters = {k: int(v) for k, v in re.findall(r'([A-Za-z]+)=(\d+)', line)
                                  if k in {'segmentCount', 'inputCharCount', 'requestTimeoutMillis', 'maxTokens', 'maxAttempts', 'promptChars'}}
    old_check = load('old-freeze-check.json')
    manifest = OUT / 'P13B_SHA256SUMS.before'
    assert hashlib.sha256(manifest.read_bytes()).hexdigest() == old_check['old_manifest_sha256']
    for line in manifest.read_text().splitlines():
        digest, name = line.split('  ', 1)
        path = ROOT / name
        if path == OUT.parent / 'VERIFY.md':
            path = OUT / 'P13B_VERIFY.before.md'
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, name
    known = {k: sum(r[k] for r in rows if r[k] is not None)
             for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')}
    return {'task_id': complete['task_id'], 'status': complete['status'], 'new_tasks': 1,
            'configuration_version': 10, 'counts_by_reason': dict(counts), 'physical_calls': len(rows),
            'successful_batches': sum(r['provider_reason'] == 'PASSED' and r['validation_reason'] == 'PASSED' for r in rows),
            'failed_calls': sum(r['provider_reason'] != 'PASSED' or r['validation_reason'] not in (None, 'PASSED') for r in rows),
            'known_usage': known, 'unknown_total_usage_calls': sum(r['total_tokens'] is None for r in rows),
            'samples': samples, 'disk_max_percent': max(x['percent'] for x in disks),
            'configuration_unchanged': True, 'pipeline_stage_ms': stage_ms,
            'translation_request_parameters': request_parameters, 'task_observation_ms': load('terminal.json')['elapsed_ms']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--record', action='store_true')
    args = parser.parse_args()
    summary = summarize()
    if args.record:
        (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    else:
        assert summary == load('summary.json')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
