"""One explicitly authorized v10 trial; refusal to replay and no provider credential access."""
import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import time

from support import ROOT, PUBLIC, PRIVATE, admin, disk, redact, sql, utc

OUT = PUBLIC / 'p13d'
RAW = PRIVATE / 'p13d'


def save(name, value, private=False):
    path = (RAW if private else OUT) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(redact(value), ensure_ascii=False, indent=2) + '\n')
    if private:
        path.chmod(0o600)


def append(name, value):
    OUT.mkdir(exist_ok=True)
    with (OUT / name).open('a') as f:
        f.write(json.dumps(redact(value), ensure_ascii=False) + '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-authorized-one-task', action='store_true')
    args = parser.parse_args()
    if not args.run_authorized_one_task:
        parser.error('This creates one billable task; explicit flag required')
    assert not (OUT / 'submission-intent.json').exists(), 'Never replay an uncertain submission'
    assert disk()['percent'] <= 85, 'Disk guard'
    bridge = admin()
    catalog = bridge.safe(bridge.api('/admin/system-models/catalog'))
    route = catalog['effective']['TRANSLATION_FULL_TEXT']
    assert catalog['version'] == 10 and route['source'] == 'DATABASE' and route['model'] == 'deepseek-flash'
    assert not sql("SELECT JSON_OBJECT('id',id) FROM courselingo.analysis_task WHERE status IN ('CREATED','QUEUED','RUNNING','RETRYING')")
    trial = next(json.loads(line) for line in (PUBLIC / 'trials.jsonl').read_text().splitlines()
                 if json.loads(line)['trial_id'] == 'deepseek-economics-1')
    source = next(x for x in json.loads((ROOT / 'eval/baseline-asr-20261015/assets.lock.json').read_text())['sources'] if x['id'] == 'economics')
    with (ROOT / source['evaluation_video_file']).open('rb') as f:
        assert hashlib.file_digest(f, 'sha256').hexdigest() == source['evaluation_video_sha256']
    save('catalog-before.json', catalog)
    # Reuse the already authorized, completed upload; only the new analysis task is created.
    intent = {'utc': utc(), 'source_id': 'economics', 'source_sha256': source['evaluation_video_sha256'],
              'reuse_upload_id': trial['upload_id'], 'new_tasks': 1, 'expected_config_version': 10,
              'code_commit': 'bc2e6cc', 'task_limit_seconds': 1800, 'timeouts_or_concurrency_changed': False}
    save('submission-intent.json', intent)
    started = time.monotonic()
    created = bridge.api('/tasks', data={'uploadId': trial['upload_id'], 'sourceLanguage': 'en', 'targetLanguage': 'zh-CN'})
    task_id = created['taskId']
    assert re.fullmatch(r'task_[0-9a-f]{32}', task_id)
    save('submission.json', {'utc': utc(), 'response': created})
    print(json.dumps({'submitted': task_id}), flush=True)
    snapshots = bridge.safe(bridge.api('/admin/system-models/executions?taskId=' + task_id))
    save('snapshots.json', snapshots)
    assert snapshots and all(s['configVersion'] == 10 and s['routes']['TRANSLATION_FULL_TEXT']['source'] == 'DATABASE'
                            and s['routes']['TRANSLATION_FULL_TEXT']['model'] == 'deepseek-flash' for s in snapshots)
    previous = None
    while True:
        guard = disk()
        append('disk.jsonl', guard)
        task = bridge.api('/tasks/' + task_id)
        stage = (task['status'], task.get('currentStage'))
        if stage != previous:
            append('progress.jsonl', {'utc': utc(), 'task': task})
            print(json.dumps({'task_id': task_id, 'status': stage[0], 'stage': stage[1]}), flush=True)
            previous = stage
        if guard['percent'] > 85 or time.monotonic() - started >= 1800:
            if task['status'] not in {'SUCCEEDED', 'FAILED', 'CANCELED'}:
                bridge.api('/tasks/' + task_id + '/cancel', method='POST')
            save('STOP.json', {'reason': 'DISK_ABOVE_85' if guard['percent'] > 85 else 'TASK_30_MIN_LIMIT', 'disk': guard})
            return
        if task['status'] in {'SUCCEEDED', 'FAILED', 'CANCELED'}:
            break
        time.sleep(2)
    save('terminal.json', {'utc': utc(), 'elapsed_ms': round((time.monotonic()-started)*1000,3), 'task': task})
    result = bridge.api('/tasks/' + task_id + '/results')
    save('task-results.json', result, private=True)
    query = """SELECT JSON_OBJECT('id',id,'snapshot_id',snapshot_id,'task_id',task_id,'config_version',config_version,
        'feature',feature,'model',model,'provider_attempt',provider_attempt,'segment_count',segment_count,
        'input_chars',input_chars,'batch_indexes',batch_indexes,'http_status',http_status,'finish_reason',finish_reason,
        'provider_reason',provider_reason,'validation_category',validation_category,'validation_reason',validation_reason,
        'final_validation_reason',final_validation_reason,'prompt_tokens',prompt_tokens,'completion_tokens',completion_tokens,
        'total_tokens',total_tokens,'duration_millis',duration_millis,'response_chars',response_chars,
        'response_truncated',response_truncated,'response_excerpt',response_excerpt,'created_at',created_at)
        FROM courselingo.translation_call_diagnostic WHERE task_id='""" + task_id + "' AND user_id=9 ORDER BY created_at,id"
    rows = sql(query)
    assert rows, 'No diagnostics: do not submit another task'
    save('diagnostics-with-excerpts.json', rows, private=True)
    public_rows = [{k: v for k, v in row.items() if k != 'response_excerpt'} for row in rows]
    for row, original in zip(public_rows, rows, strict=True):
        excerpt = original['response_excerpt']
        row['excerpt_sha256'] = hashlib.sha256(excerpt.encode()).hexdigest() if excerpt is not None else None
    save('diagnostics.json', public_rows)
    journal = subprocess.run(['journalctl','-u','lecturelens-live-backend','--since',intent['utc'],
                              '--no-pager','-o','cat'],capture_output=True,text=True,check=True,timeout=30)
    lines = [redact(line) for line in journal.stdout.splitlines() if task_id in line]
    save('task-log.json', lines, private=True)
    save('catalog-after.json', bridge.safe(bridge.api('/admin/system-models/catalog')))
    save('COMPLETE.json', {'utc': utc(), 'task_id': task_id, 'status': task['status'], 'diagnostic_rows': len(rows),
                           'disk': disk(), 'new_tasks': 1})
    print(json.dumps({'finished': task_id, 'status': task['status'], 'diagnostic_rows': len(rows)}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        save('DRIVER_STOP.json', {'utc': utc(), 'error_type': type(error).__name__})
        print('DRIVER_STOPPED', type(error).__name__, flush=True)
        raise SystemExit(1)
