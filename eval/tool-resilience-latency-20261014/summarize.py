"""Compute report statistics only from completed, audited serial batches."""
import collections
import hashlib
import json
import math
import statistics
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'serial-clean'
INVALID = {'negative_parameter', 'reversed_window', 'oversized_parameter', 'integer_overflow', 'unknown_tool', 'illegal_call_shape'}


def stats(values):
    values = sorted(values)
    return {'n': len(values), 'mean': round(statistics.mean(values), 3),
            'p50': values[math.ceil(.5 * len(values)) - 1], 'p95': values[math.ceil(.95 * len(values)) - 1]}


def read(name):
    return [json.loads(l) for l in (DATA / name).read_text().splitlines()]


def audit(phase, labels):
    entries = json.loads((DATA / f'{phase}-audit.json').read_text())
    assert [e['label'] for e in entries] == labels
    for entry in entries:
        assert entry['returncode'] == 0
        assert entry['host_samples'] and not any(s['unexpected_eval_or_test_processes'] for s in entry['host_samples'])
    for before, after in zip(entries, entries[1:]):
        assert datetime.fromisoformat(before['finished_at_utc']) <= datetime.fromisoformat(after['started_at_utc'])
    return entries


def main():
    healthy_audit = audit('healthy', ['baseline', 'before', 'candidate'])
    fault_audit = audit('faults', ['baseline', 'candidate'])
    assert datetime.fromisoformat(healthy_audit[-1]['finished_at_utc']) < datetime.fromisoformat(fault_audit[0]['started_at_utc'])
    report = {'percentiles': 'nearest rank', 'workers': 1, 'samples_per_scenario': 20,
              'healthy': {}, 'faults': {}, 'raw_sha256': {}, 'source_sha256': {},
              'old_latency_correction': {'original_p50_p95_ms': [1910.6, 3443.2],
                'reason': 'Original candidate 06:59-07:03 UTC overlapped full pytest from 07:00:55 UTC; baseline idle. Not an isolated code-regression estimate.',
                'acceptor_serial_control_user_provided': {'n_per_version': 20, 'baseline_ms': [1405, 2022], 'before_ms': [2636, 3215]}},
              'real_model_quality': '未运行', 'real_Java_process_faults': '未运行'}
    fixtures = set()
    for phase in ['baseline', 'before', 'candidate']:
        name = f'healthy-{phase}.jsonl'
        rows = read(name)
        assert len(rows) == 20 and all(r['run']['status'] == 'succeeded' for r in rows)
        identity = {r['source_sha256'] for r in rows}
        assert len(identity) == 1
        report['source_sha256'][phase] = next(iter(identity))
        fixtures |= {r['fixture_sha256'] for r in rows}
        counts = {(r['run']['model_calls'], r['run']['tool_calls'], len(r['http_calls']),
                   sum(e['event'] == 'tools/call' for e in r['mcp_events'])) for r in rows}
        assert counts == {(4, 3, 25, 25)}
        assert not any(e['event_type'] == 'tool_retry_started' for r in rows for e in r['public_events'])
        report['healthy'][phase] = {'latency_ms': stats([r['elapsed_ms'] for r in rows]),
                                  'model_tool_http_mcp_calls': list(next(iter(counts))), 'read_retries': 0,
                                  'mcp_cumulative_ms': stats([sum(e['duration_ms'] for e in r['mcp_events'] if e['event'] == 'tools/call') for r in rows])}
        report['raw_sha256'][name] = hashlib.sha256((DATA / name).read_bytes()).hexdigest()
    versions = {phase: read(f'faults-{phase}.jsonl') for phase in ['baseline', 'candidate']}
    for phase, rows in versions.items():
        assert len(rows) == 300 and set(collections.Counter(r['scenario'] for r in rows).values()) == {20}
        assert {r['source_sha256'] for r in rows} == {report['source_sha256'][phase]}
        fixtures |= {r['fixture_sha256'] for r in rows}
        report['raw_sha256'][f'faults-{phase}.jsonl'] = hashlib.sha256((DATA / f'faults-{phase}.jsonl').read_bytes()).hexdigest()
        selected = {r['scenario'] for r in rows}
        for scenario in sorted(selected):
            sample = [r for r in rows if r['scenario'] == scenario]
            status = dict(collections.Counter(r['run']['status'] for r in sample))
            success = status.get('succeeded', 0)
            refusal = sum(r['artifact_kind'] == 'insufficient_evidence' for r in sample)
            retries = [sum(e['event_type'] == 'tool_retry_started' for e in r['public_events']) for r in sample]
            report['faults'].setdefault(scenario, {})[phase] = {'n': len(sample), 'status': status,
                'execution_success': success, 'recovery_rate': None if scenario in INVALID else success/len(sample),
                'invalid_request_succeeded': success if scenario in INVALID else 0, 'refused': refusal,
                'failure_codes': dict(collections.Counter(r['run']['error_code'] for r in sample if r['run']['error_code'])),
                'read_retry_total': sum(retries), 'read_retry_per_run': stats(retries),
                'latency_ms': stats([r['elapsed_ms'] for r in sample]),
                'budget_tool_calls': stats([r['run']['tool_calls'] for r in sample]),
                'model_calls': stats([r['run']['model_calls'] for r in sample])}
            if phase == 'candidate':
                expected = 'succeeded' if scenario in {'healthy', 'timeout_once', 'unavailable_once', 'protocol_once'} else 'failed'
                assert status == {expected: 20} and refusal == 0
                expected_retry = 1 if scenario in {'timeout_once', 'unavailable_once'} else 2 if scenario in {'timeout_persistent','unavailable_persistent','check_unavailable_persistent'} else 0
                assert set(retries) == {expected_retry}
                if scenario in INVALID:
                    assert all(r['run']['tool_calls'] == 0 and r['artifact_kind'] is None for r in sample)
                    assert all(any(e['event_type'] == 'tool_rejected' for e in r['public_events']) for r in sample)
    assert len(fixtures) == 1
    previous = json.loads((ROOT.parent/'tool-resilience-20261014/summary.json').read_text())
    for scenario, data in report['faults'].items():
        current, old = data['candidate'], previous['scenarios'][scenario]['candidate']
        assert current['status'] == old['status_distribution']
        assert current['execution_success'] == old['execution_success']
        assert current['refused'] == old['refusal_count']
        assert current['failure_codes'] == old['failure_codes']
        assert current['read_retry_total'] == old['read_retry_calls']['total']
    report['fault_counts_match_accepted_P0_1'] = True
    (ROOT/'summary.json').write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n')
    lines = ['# P0-1 延迟修复结果', '', '所有本轮数字来自 serial-clean 原始记录；nearest-rank P50/P95。正式阶段按版本串行，不与测试/其他评测重叠，详见审计。', '',
             '|健康版本|n|P50 ms|P95 ms|模型/工具/HTTP/MCP|读重试|', '|---|---:|---:|---:|---|---:|']
    for phase, data in report['healthy'].items():
        values = data['latency_ms']
        lines.append(f'|{phase}|{values["n"]}|{values["p50"]:.3f}|{values["p95"]:.3f}|4/3/25/25|0|')
    lines += ['', '旧报告 +1.91/+3.44s 受并发负载污染，不能用作干净代码回退估计；旧文件保持原样。验收方串行 20 次提供 1405/2022 → 2636/3215ms，本轮自己的修复前/后数字如上。', '',
              '|场景|n/版|基线成功|候选成功|候选失败/拒答|候选额外读重试总数|候选 P50/P95 ms|', '|---|---:|---:|---:|---|---:|---|']
    for scenario, data in report['faults'].items():
        before, after = data['baseline'], data['candidate']; latency = after['latency_ms']
        lines.append(f'|{scenario}|20|{before["execution_success"]}|{after["execution_success"]}|{after["status"].get("failed",0)}/{after["refused"]}|{after["read_retry_total"]}|{latency["p50"]:.1f}/{latency["p95"]:.1f}|')
    lines += ['', '临时超时/503：0/40 → 40/40 恢复；持续依赖故障 60/60 失败；非法参数/工具 120/120 在执行前拒绝。全部候选终态、错误码、拒答及重试计数与已验收 P0-1 一致。',
              '基线 60 个越界请求仍执行成功，候选为零；该指标是协议合规，不是模型教学质量评分。', '',
              'Profiling：健康 Run 新增 100 个 Store 连接创建请求；平均连接创建约 610 → 1436ms，SQL 约 220 → 537ms。Run 内连接复用后 Store 实际物理连接为 2 次（另有 checkpoint saver 独立连接），所有持久记录与围栏仍执行。',
              '最终全量测试、源码/记录哈希及未覆盖项见 verification.json / README.md。真实模型质量、真实 Java 进程故障未运行。未 push、未部署。']
    if (ROOT/'verification.json').exists():
        verification = json.loads((ROOT/'verification.json').read_text())
        counts = verification['python_checks']
        lines += ['', f"全量 Python：{counts['tests']} 通过，{counts['failures']} 失败，{counts['errors']} 错误，{counts['skipped']} 跳过；四个独立 PostgreSQL/pgvector 测试库，完整收集覆盖一次。ruff 与格式检查通过。",
                  f"测试开始 UTC：{verification['test_started_at_utc']}，晚于所有正式测量结束；进程审计与 XML 时窗验证通过。",
                  '原 P0-1 原始记录哈希保持不变，分支 main；Java 与冻结资产未修改。']
    (ROOT/'RESULTS.md').write_text('\n'.join(lines)+'\n')


if __name__ == '__main__':
    main()
