"""Report blocked acceptance separately from unit/integration and reused-evidence real-model observations."""
from pathlib import Path
import json
import re
import statistics
from collections import Counter

ROOT=Path('/home/dev/projects/lecturelens');PUBLIC=Path(__file__).resolve().parent;PRIVATE=ROOT/'.data'/PUBLIC.name


def main():
    candidate=json.loads((PUBLIC/'candidate-artifact.json').read_text())
    tests=json.loads((PUBLIC/'tests.json').read_text())
    supplement=json.loads((PUBLIC/'materials-supplement.json').read_text())
    log=(PRIVATE/'materials-supplement.log').read_text()
    starts=[dict(phase=m[1],request=int(m[2]),estimated_input_tokens=int(m[3]),input_limit=int(m[4]),output_limit=int(m[5]))
        for m in re.finditer(r'phase=(\S+) request=(\d+) estimatedInputTokens=(\d+) inputLimit=(\d+) outputLimit=(\d+)',log)]
    times=[call['duration_millis']/1000 for call in supplement['calls']]
    failure_reason='TIMEOUT_OR_DEADLINE' if re.search(r'HttpTimeoutException|request timed out|category=TIMEOUT|deadline exhausted',log) else None
    stats=dict(n=len(times),mean_seconds=statistics.mean(times) if times else None,
        sample_stddev_seconds=statistics.stdev(times) if len(times)>1 else None)
    summary=dict(candidate='P2-1c',jar_sha256=candidate['jar_sha256'],test_total=tests['total'],
        normal=dict(planned=10,submitted=0,successes=0,success_rate=None,stage_means=None,lesson_fees=None),
        recovery=dict(planned=1,submitted=0,sigkill_count=0,status='NOT_DEMONSTRATED_ASR_ACCESS_DENIED'),
        status='BLOCKED_ASR_ACCESS_DENIED_UNPURCHASED',
        diagnostics=dict(asr_physical_requests=2,http403=2,provider_error_code='AccessDenied.Unpurchased',usage=None,cost=None),
        supplemental=dict(kind=supplement['kind'],formal_trial=False,exit_code=supplement['exit_code'],
            structured_valid=supplement.get('structured_valid'),long_course_quality_valid=supplement.get('long_course_quality_valid'),
            exception_class=supplement.get('exception_class'),failure_reason=failure_reason,
            successful_phase_counts=dict(Counter(c['phase'] for c in supplement['calls'])),
            final_generation_reached=any(c['phase']=='FINAL' for c in starts),
            preflight_dispatches=starts,successful_calls=len(supplement['calls']),
            incomplete_or_unknown_dispatches=len(starts)-len(supplement['calls']),successful_call_timing=stats),
        historical_comparison=dict(P1_3=dict(full_chain_successes=0,submitted=10),P1_3b=dict(full_chain_successes=0,submitted=10),P2_1b=dict(full_chain_successes=0,submitted=10)),
        push=False,deploy=False)
    (PUBLIC/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    complete=summary['supplemental']
    text=f'''# P2-1c：上下文修复已冻结，正式10+1受ASR权限阻碍

已获用户确认方案a和Redis15的12个已知key原样保留。实现分块map-reduce、完整消息token保守预检、输入≤70%且预留输出、共享调用/归并/时间预算、每次请求前的generation/执行围栏检查，并保留DeepSeek绑定入口。没有修改ASR或在线模型绑定。

候选JAR SHA256：`{candidate['jar_sha256']}`，源码与补丁身份见candidate-artifact.json。测试共{tests['total']['tests']}项通过，失败/错误/跳过均0，其中14项新增上下文测试，21项独立MySQL模型运行时测试；离线package成功。第一次MySQL命令因提权后的Maven空缓存未执行测试，以dev用户重跑通过，失败日志保留。测试机制不等同真实模型质量。

## 正式验收状态

| 项目 | 计划 | 已提交 | 结果 |
| --- | --- | --- | --- |
| 新候选完整链路 | 10 | 0 | BLOCKED，成功率NA，不能写0%或100% |
| 独立翻译中断恢复 | 1 | 0 | 未演示，SIGKILL 0次 |

冻结后ASR预检仍HTTP403 **AccessDenied.Unpurchased**，模型使用资格/服务开通权限拒绝。两次独立短音频诊断各1次，无重试，均178字符403。它们不计入正式10+1；供应商用量/费用未返回，保留未知。没有替换凭据、模型、端点，未开通服务、充值或改权限。旧第70片确切错误码仍因正文缺失无法证明，第71片是中断而非已确认403，见ASR_DIAGNOSIS.md及postfreeze-asr-preflight。

当前ASR无法从头执行全链路，因此没有启动隔离worker、没有提交正式试次，也没有用旧转写冒充新ASR。正式各阶段均值±标准差、单节ASR/翻译费用、拆批/并发数据均NA。历史P1-3、P1-3b、P2-1b完整链路均0/10，详见上一轮SUMMARY；本轮0次提交不能与它们计算成功率或加速比。

## 独立资料阶段补充验证

使用冻结候选，仅读取上轮normal-algorithms-1已有原文/译文，调用真实本地lecturelens-local-qwen。无服务栈、ASR/翻译调用、数据库写入或发布，没有服务鉴权/围栏集成，不计入正式10+1。完整输入和输出仅保留本地，公开证据只含哈希、调用计数和用量。

- 子进程exit={complete['exit_code']}，失败原因分类={failure_reason}。14个map和2个reduce成功返回，第3个reduce在900秒总期限附近超时，最终资料生成未到达，结构及LONG质量检验未执行。原始structured_valid=false表示未获得成功结果，不表示最终JSON解析失败。
- 上下文预检派发{len(starts)}次，成功返回{complete['successful_calls']}次，未成功或结果未知{complete['incomplete_or_unknown_dispatches']}次；未成功调用不补造token/费用。
- 成功调用耗时：n={stats['n']}，均值±样本标准差 {stats['mean_seconds']:.3f} ± {stats['sample_stddev_seconds']:.3f}秒。这是同一份旧证据内部调用统计，不能当成10次整课统计。
- 每次预检估算均不超过输入上限；成功返回的实际prompt token均检查≤该上限，且input+output+256≤8192。该观察不能证明未完成/未知请求的供应商侧结果。

原始观测见materials-supplement.json和summary.json。私有驱动日志末行PHYSICAL_LLM_CALLS=16实际只统计成功返回记录；以17次预检派发、16次已知成功和1次未成功/未知为准，不能漏算最后一次请求。没有将结构成功或token预算满足等同完整资料质量成功，也没有为失败自动追加试次。

## 约束与下一步

Redis15门禁通过，12个已知key均未读值/删除/换库；模型配置仍v10且哈希未变。磁盘全程未超过85%，最终监测见execution-closeout.json。原P2-1的34份和P2-1b的33份私有原始记录哈希已验证一致。所有本轮子进程结束后确认18091空闲；不push、不部署、不对受保护容器执行生命周期操作。

完整链路和真实恢复仍未完成；需要账户侧恢复当前ASR模型的调用资格后，按RUNTIME_PLAN.md执行新的独立10+1。证据完整性校验通过不代表验收通过。
'''
    (PUBLIC/'SUMMARY.md').write_text(text)
    (PUBLIC/'VERIFY.md').write_text(f'''# P2-1c 验证状态

**修复与候选冻结完成；正式10+1 BLOCKED_ASR_ACCESS_DENIED_UNPURCHASED；真实恢复未演示。**

- 方案a及Redis15保留12个已知key复用已由用户明确确认，见authorization.json、runtime-gates.json。未读取Redis值或清空/换库。
- {tests['total']['tests']}项Java测试通过，0失败/错误/跳过；其中14项上下文测试、21项独立MySQL运行时测试，报告摘要/哈希见tests.json，原始报告本地保存。H2事务测试验证模型I/O在事务外、发布原子性；生成守卫单测验证每次调用的授权检查、取消、预算及冻结引用传递。第一次MySQL启动未执行测试，重跑通过，不计入通过数。
- 离线package成功。冻结JAR SHA256 `{candidate['jar_sha256']}`。源码文件、candidate.patch及冻结JAR哈希均校验；运行时109个依赖与冻结JAR一致。未部署。
- 真实本地模型补充验证exit={complete['exit_code']}：14个map、2个reduce成功，第3个reduce在900秒期限附近超时，未到最终资料生成/质量校验，详见SUMMARY.md。成功调用实际prompt最多1400 token，均未超预算；这不代表整课资料生成通过。它复用旧证据、没有完整链路/发布或服务鉴权集成，不计入10+1。
- 新候选完整链路0/10已提交；独立恢复0/1已提交；worker启动0次，SIGKILL0次。没有已完成批次零重跑的真实证明。
- ASR诊断2次物理请求，均403 AccessDenied.Unpurchased，0重试；无ASR配置修复，费用/用量未知。旧第70片仅能推断同类故障，不能复原其供应商确切错误码。
- 运行前df余量约36GiB；全过程磁盘监测≤85%，见execution-closeout.json。原候选私有原始记录全部通过原SHA清单校验。
- validate_evidence.py只验证身份、计数、scope和预算证据，输出不将受阻验收标为通过。公开SHA256SUMS与私有RAW_SHA256SUMS分别验证；凭据、原始媒体、全文和供应商正文不入Git。
- 无push、无部署、无受保护容器生命周期操作；本轮进程已结束，18091空闲。其他未提交DIAGNOSIS.md保留。
''')
    print('P21C_SUMMARY_RECORDED_WITH_BLOCKED_ACCEPTANCE')


if __name__=='__main__':main()
