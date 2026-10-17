"""Recompute benchmark tables from immutable terminal rows and safe DB projections."""
import collections
import json
import statistics
from datetime import datetime
from pathlib import Path

PUBLIC=Path(__file__).resolve().parent
ROOT=PUBLIC.parents[1]


def stats(values):
    values=[float(v) for v in values if v is not None]
    return dict(n=len(values),mean=statistics.mean(values) if values else None,
                sample_sd=statistics.stdev(values) if len(values)>1 else None)


def display(s,digits=3):
    if not s['n']:return 'NA (n=0)'
    return f"{s['mean']:.{digits}f} ± {s['sample_sd']:.{digits}f} (n={s['n']})" if s['sample_sd'] is not None else f"{s['mean']:.{digits}f} ± NA (n={s['n']})"


def peak(calls):
    changes=[]
    for c in calls:
        if c['created_at'] and c['completed_at']:
            changes.extend([(datetime.fromisoformat(c['created_at']),1),(datetime.fromisoformat(c['completed_at']),-1)])
    active=maximum=0
    for _,delta in sorted(changes):active+=delta;maximum=max(maximum,active)
    return maximum


def cost(calls,currency):
    return dict(currency=currency,physical_calls=len(calls),
                known_lower=sum(float(c['cost_lower']) for c in calls if c['cost_lower'] is not None),
                known_upper=sum(float(c['cost_upper']) for c in calls if c['cost_upper'] is not None),
                unknown_cost_calls=sum(c['cost_lower'] is None or c['cost_upper'] is None for c in calls),
                unknown_usage_calls=sum(c['prompt_tokens'] is None or c['completion_tokens'] is None for c in calls),
                known_prompt_tokens=sum(c['prompt_tokens'] or 0 for c in calls),
                known_completion_tokens=sum(c['completion_tokens'] or 0 for c in calls),
                statuses=dict(collections.Counter(c['status'] for c in calls)),
                error_categories=dict(collections.Counter(c['error_category'] for c in calls if c['error_category'])),
                asr_catalog_reference_cny=sum((c['prompt_tokens']*.8+c['completion_tokens']*2.7)/1_000_000 for c in calls if c['feature']=='ASR_TRANSCRIPTION' and c['model']=='qwen-audio-3.1-asr-flash' and c['prompt_tokens'] is not None and c['completion_tokens'] is not None) if currency=='CNY' else None,
                catalog_reference_is_account_bill=False)


def cost_text(c):
    suffix=f" + {c['unknown_cost_calls']} 次未知" if c['unknown_cost_calls'] else ''
    lo,hi=c['known_lower'],c['known_upper']
    reference=c.get('asr_catalog_reference_cny')
    if c['currency']=='CNY' and c['unknown_cost_calls']:
        return f"UNPRICED；目录价参考 {reference:.6f}"+ (f" + {c['unknown_usage_calls']} 次未知用量" if c['unknown_usage_calls'] else '')
    return (f'{lo:.6f}' if lo==hi else f'{lo:.6f}–{hi:.6f}')+suffix


def enrich(row):
    data=json.loads((PUBLIC/'runtime-evidence'/f"{row['task_id']}.json").read_text())
    asr=[c for c in data['calls'] if c['feature']=='ASR_TRANSCRIPTION']
    translation=[c for c in data['calls'] if c['feature']=='TRANSLATION_FULL_TEXT']
    row=dict(row)
    row.update(asr_cost=cost(asr,'CNY'),translation_cost=cost(translation,'USD'),
               other_physical_calls=sum(c['feature'] not in ['ASR_TRANSCRIPTION','TRANSLATION_FULL_TEXT'] for c in data['calls']),
               initial_batches=sum(b['parent_batch_no'] is None for b in data['batches']),
               split_nodes=len({b['parent_batch_no'] for b in data['batches'] if b['parent_batch_no'] is not None}),
               child_batches=sum(b['parent_batch_no'] is not None for b in data['batches']),
               checkpoint_attempts=len(data['attempts']),
               translation_retry_reservations=sum(max(0,b['attempt_count']-1) for b in data['batches']),
               max_window=max((e['new_window'] for e in data['scheduler']),default=None),
               max_translation_inflight=max((e['inflight'] for e in data['scheduler']),default=None),
               max_asr_http_intervals=peak(asr),
               backpressure_events=dict(collections.Counter(e['reason'] for e in data['scheduler'] if e['reason'] in ['RATE_LIMITED','TIMEOUT'])),
               timing=data['timing'],coverage=data['coverage'],
               translation_published=bool(data['publication']),
               stage_seconds={e['step']:e['durationMillis']/1000 for e in row['stage_events'] if 'durationMillis' in e})
    return row


def old_comparisons():
    paths={'P1-3':ROOT/'eval/baseline-asr-20261015/summary.json',
           'P1-3b':ROOT/'eval/baseline-deepseek-20261015T185735Z/summary.json'}
    out={}
    for label,path in paths.items():
        s=json.loads(path.read_text())
        old_stages=s.get('stage_ms',s.get('overall',{}).get('stage_seconds',{}))
        factor=.001 if 'stage_ms' in s else 1
        stage_stats={k:dict(n=v['n'],mean=v['mean']*factor if v['mean'] is not None else None,sample_sd=v['sample_sd']*factor if v['sample_sd'] is not None else None) for k,v in old_stages.items()}
        separate={}
        for stage in old_stages:
            separate[stage]={}
            for outcome in ['completed','failed']:
                if label=='P1-3':
                    values=[t['stage_ms'][stage]/1000 for t in s['trials'] if t.get('stage_outcomes',{}).get(stage)==outcome and stage in t.get('stage_ms',{})]
                else:
                    values=[t['stages'][stage]['seconds'] for t in s['trials'] if t.get('stages',{}).get(stage,{}).get('event')==outcome]
                separate[stage][outcome]=stats(values)
        out[label]=dict(source=str(path.relative_to(ROOT)),n=10,full_chain_successes=0,
                        terminal_seconds=stats([t.get('task_terminal_seconds',t.get('task_terminal_ms',0)/1000) for t in s['trials']]),
                        observed_stage_seconds=stage_stats,
                        separate_stage_seconds=separate,
                        translation_successes=sum(t['translation_status']=='SUCCEEDED' for t in s['trials']),
                        stage_outcomes_mixed=True,
                        trials=[{k:t.get(k) for k in ['trial_id','source_id','asr_http_calls','asr_failed_calls','asr_usage_missing_calls','asr_chunk_retries','asr_list_price_cny','asr_fee','deepseek_list_price_usd']} for t in s['trials']])
    return out


def recovery_proof():
    before=json.loads((PUBLIC/'recovery-before.json').read_text())
    after=json.loads((PUBLIC/'recovery-after.json').read_text())
    completed={b['batch_no']:b for b in before['batches'] if b['status']=='SUCCEEDED'}
    final={b['batch_no']:b for b in after['batches']}
    rows=[]
    for number,b in completed.items():
        a=final[number]
        old_attempts=[v['id'] for v in before['attempts'] if v['batch_no']==number]
        new_attempts=[v['id'] for v in after['attempts'] if v['batch_no']==number]
        rows.append(dict(batch_no=number,result_hash_unchanged=b['result_hash']==a['result_hash'],
                         attempt_count_before=b['attempt_count'],attempt_count_after=a['attempt_count'],
                         attempt_ids_unchanged=old_attempts==new_attempts))
    asr_before=[c['id'] for c in before['calls'] if c['feature']=='ASR_TRANSCRIPTION']
    asr_after=[c['id'] for c in after['calls'] if c['feature']=='ASR_TRANSCRIPTION']
    plan_before=json.loads((PUBLIC/'recovery-plan-before-resume.json').read_text())['plan']
    plan_after=json.loads((PUBLIC/'recovery-plan-after.json').read_text())['plan']
    return dict(completed_batches_before=len(completed),completed_batch_comparisons=rows,
                completed_batches_not_rerun=bool(rows) and all(r['result_hash_unchanged'] and r['attempt_ids_unchanged'] and r['attempt_count_before']==r['attempt_count_after'] for r in rows),
                asr_calls_before=len(asr_before),asr_calls_after=len(asr_after),asr_not_rerun=asr_before==asr_after,
                epoch_before=before['execution'][0]['execution_epoch'],epoch_after=after['execution'][0]['execution_epoch'],
                policy_unchanged=before['policy']==after['policy'],routes_unchanged=before['routes']==after['routes'],
                unknown_physical_outcomes=[c['id'] for c in after['calls'] if c['status']=='UNKNOWN_OUTCOME'],
                unsent_checkpoint_reservations=[a['id'] for a in before['attempts'] if a['status']=='STARTED' and not any(c['translation_attempt_id']==a['id'] for c in before['calls'])],
                final_translation_published=bool(after['publication']),final_task_status=after['task'][0]['status'],
                translation_started_at_before=plan_before['translation_started_at'],translation_started_at_after=plan_after['translation_started_at'],
                translation_deadline_before=plan_before['translation_deadline'],translation_deadline_after=plan_after['translation_deadline'],
                translation_deadline_unchanged=plan_before['translation_started_at']==plan_after['translation_started_at'] and plan_before['translation_deadline']==plan_after['translation_deadline'],
                checkpoint_physical_reservations_before=plan_before['physical_calls'],checkpoint_physical_reservations_after=plan_after['physical_calls'],
                accounted_tokens_before=plan_before['accounted_tokens'],accounted_tokens_after=plan_after['accounted_tokens'])


def main():
    journal=[json.loads(line) for line in (PUBLIC/'trials.jsonl').read_text().splitlines()]
    final=[enrich(row) for row in journal if row['phase']=='terminal']
    normal=[r for r in final if r['kind']=='NORMAL'];recovery=[r for r in final if r['kind']=='RECOVERY']
    assert len(normal)==10 and len(recovery)==1,'Never report a partial suite as 10+1'
    assert len({r['task_id'] for r in final})==11
    stages=sorted({e['step'] for r in normal for e in r['stage_events']})
    stage_stats={s:{kind:stats(e['durationMillis']/1000 for r in normal for e in r['stage_events'] if e['step']==s and e['event']==kind and 'durationMillis' in e) for kind in ['completed','failed']} for s in stages}
    old=old_comparisons()
    if (PUBLIC/'recovery-before.json').exists():
        proof=recovery_proof()
    else:
        calls=json.loads((PUBLIC/'recovery-after.json').read_text())['calls']
        proof=dict(fault_injected=False,recovery_demonstration_completed=False,reason='ASR_AUTHENTICATION_403_BEFORE_TRANSLATION_BARRIER',
                   asr_physical_calls=sum(c['feature']=='ASR_TRANSCRIPTION' for c in calls),
                   asr_http_200=sum(c['feature']=='ASR_TRANSCRIPTION' and c['http_status']==200 for c in calls),
                   asr_http_403=sum(c['feature']=='ASR_TRANSCRIPTION' and c['http_status']==403 for c in calls),
                   network_outcome_unknown=sum(c['usage_status']=='NETWORK_OUTCOME_UNKNOWN' for c in calls),
                   translation_calls=sum(c['feature']=='TRANSLATION_FULL_TEXT' for c in calls),
                   completed_asr_checkpoint=False,authentication_retry_performed=False)
    report=dict(candidate='P2-1b',normal_denominator=10,normal_completed=10,
                full_chain_successes=sum(r['full_chain_success'] for r in normal),
                translation_published=sum(r['translation_published'] for r in normal),
                terminal_statuses=dict(collections.Counter(r['status'] for r in normal)),
                terminal_seconds=stats(r['elapsed_seconds'] for r in normal),
                stage_seconds=stage_stats,trials=normal,recovery=dict(trial=recovery[0],proof=proof),baselines=old)
    reviews=json.loads((PUBLIC/'quality-reviews.json').read_text())
    report['quality_sample_review']=dict(reviewed_trials=len(reviews),reviewed_pairs=sum(r['sample_count'] for r in reviews),
        observed_meaning_errors=sum(r['observed_meaning_errors'] for r in reviews),
        terminology_style_issues=sum(r.get('observed_terminology_style_issues',0) for r in reviews),assessor='Codex, not expert/human reference grading')
    report['normal_totals']=dict(asr_physical_calls=sum(r['asr_cost']['physical_calls'] for r in normal),
        translation_physical_calls=sum(r['translation_cost']['physical_calls'] for r in normal),
        split_nodes=sum(r['split_nodes'] for r in normal),child_batches=sum(r['child_batches'] for r in normal),
        translation_retry_reservations=sum(r['translation_retry_reservations'] for r in normal),
        asr_catalog_reference_cny=sum(r['asr_cost']['asr_catalog_reference_cny'] for r in normal),
        translation_known_lower_usd=sum(r['translation_cost']['known_lower'] for r in normal),
        translation_known_upper_usd=sum(r['translation_cost']['known_upper'] for r in normal),
        max_asr_http_intervals=max(r['max_asr_http_intervals'] for r in normal),
        max_translation_window=max(r['max_window'] for r in normal),max_translation_inflight=max(r['max_translation_inflight'] for r in normal))
    errors=json.loads((PUBLIC/'materials-errors.json').read_text())
    normal_errors=[e for e in errors if e['task_id'] in {r['task_id'] for r in normal}]
    report['normal_materials_failures']=normal_errors
    per_course={}
    for source in dict.fromkeys(r['source_id'] for r in normal):
        rows=[r for r in normal if r['source_id']==source]
        old_rows=[r for r in old['P1-3']['trials'] if r['source_id']==source]
        old_calls=[r['asr_http_calls'] for r in old_rows if r['asr_http_calls'] is not None]
        new_calls=[r['asr_cost']['physical_calls'] for r in rows]
        per_course[source]=dict(asr_calls_mean=statistics.mean(new_calls),
                                old_180s_asr_calls_mean=statistics.mean(old_calls) if old_calls else None,
                                physical_call_delta=statistics.mean(new_calls)-statistics.mean(old_calls) if old_calls else None,
                                asr_cost_lower_mean=statistics.mean(r['asr_cost']['known_lower'] for r in rows),
                                asr_catalog_reference_mean_cny=statistics.mean(r['asr_cost']['asr_catalog_reference_cny'] for r in rows),
                                old_asr_known_prices=[r['asr_list_price_cny'] for r in old_rows],
                                old_asr_unknown_usage_calls=sum(r['asr_usage_missing_calls'] or 0 for r in old_rows),
                                new_asr_unknown_cost_calls=sum(r['asr_cost']['unknown_cost_calls'] for r in rows))
    report['silence_comparison']=per_course
    report['per_course']={source:dict(n=2,translation_seconds=stats(r['stage_seconds'].get('TRANSLATE_SUBTITLES') for r in normal if r['source_id']==source),
                                     asr_catalog_reference_cny=stats(r['asr_cost']['asr_catalog_reference_cny'] for r in normal if r['source_id']==source),
                                     translation_known_lower_usd=stats(r['translation_cost']['known_lower'] for r in normal if r['source_id']==source),
                                     translation_known_upper_usd=stats(r['translation_cost']['known_upper'] for r in normal if r['source_id']==source),
                                     translation_unknown_cost_calls=sum(r['translation_cost']['unknown_cost_calls'] for r in normal if r['source_id']==source)) for source in per_course}
    (PUBLIC/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    lines=['# P2-1b 独立真实验收', '',
           f"正常完整链路 **{report['full_chain_successes']}/10**；翻译发布 {report['translation_published']}/10。独立恢复任务另列，不计入正常均值。正常端到端耗时 **{display(report['terminal_seconds'])} 秒**。",'',
           '原候选 P2-1 的 1 次 MQ 协议失败保留在独立目录，不并入此候选。P2-1b 仅修复 transport payload 的 v2/epoch 字段；系统 v10 与策略 v2.5 保持原路由和预算。', '',
           ('**恢复演示未完成**：第11个任务在 ASR 第70/71片收到403/AUTHENTICATION，另一在途请求网络结果未知；未进入翻译、SIGKILL为0次。没有将失败改成恢复成功，没有追加试次或供应商探测。403仅保存响应长度178，正文未采集，不能判断密钥、权限或余额等具体原因。' if not recovery[0]['fault_injected'] else '恢复故障注入与终态单独见下方。'),'',
           '耗时为秒，均值±样本标准差（ddof=1）；未到达阶段为 NA，成功与失败阶段分开。失败终态耗时不等价于成功完成速度。', '',
           '| 阶段 | 完成样本 | 失败样本 |','| --- | --- | --- |']
    for stage,value in stage_stats.items():lines.append(f"| {stage} | {display(value['completed'])} | {display(value['failed'])} |")
    lines+=['',f"正常试次调用与调度汇总：{report['normal_totals']['asr_physical_calls']} 次 ASR，{report['normal_totals']['translation_physical_calls']} 次翻译；{report['normal_totals']['split_nodes']} 个出网前拆分父节点（父批 attempt_count=0），{report['normal_totals']['child_batches']} 个子批，{report['normal_totals']['translation_retry_reservations']} 次物理重试。ASR HTTP 账本区间并发峰值 {report['normal_totals']['max_asr_http_intervals']}；翻译窗口/在途峰值 {report['normal_totals']['max_translation_window']}/{report['normal_totals']['max_translation_inflight']}，原始有序曲线在各 task 的 scheduler 记录。",'']
    lines+=['','| 课程/次 | 终态 | 翻译秒 | ASR CNY | 翻译 USD | ASR/翻译物理调用 | 初始批/拆分节点/重试预留 | 窗口/在途峰值 |','| --- | --- | --- | --- | --- | --- | --- | --- |']
    for r in normal:
        lines.append(f"| {r['source_id']}/{r['repeat']} | {r['status']} | {r['stage_seconds'].get('TRANSLATE_SUBTITLES','NA')} | {cost_text(r['asr_cost'])} | {cost_text(r['translation_cost'])} | {r['asr_cost']['physical_calls']}/{r['translation_cost']['physical_calls']} | {r['initial_batches']}/{r['split_nodes']}/{r['translation_retry_reservations']} | {r['max_window']}/{r['max_translation_inflight']} |")
    lines+=['','| 每课两次汇总 | 翻译秒 | ASR 目录价参考 CNY | 翻译已知下界 USD | 翻译已知上界 USD |','| --- | --- | --- | --- | --- |']
    for source,v in report['per_course'].items():lines.append(f"| {source} | {display(v['translation_seconds'])} | {display(v['asr_catalog_reference_cny'],6)} | {display(v['translation_known_lower_usd'],6)} | {display(v['translation_known_upper_usd'],6)} |")
    lines+=['', '费用唯一来自 model_call_attempt，包含失败、截断父批、拆分子批及重试。已知费用为目录价估算；未知调用另列，不把缺失 usage 当零，也不合并 CNY/USD。资料/本地模型等其他调用不冒充 ASR 或翻译费用。', '',
            '本次 ASR 使用北京工作空间 maas.aliyuncs.com 地址，冻结运行时只为精确 dashscope.aliyuncs.com 主机匹配价卡，因此原账本保持 UNPRICED。ASR 列另给实际账本 usage × [百炼北京同名模型公开价](https://help.aliyun.com/zh/model-studio/model-pricing)（输入0.8/输出2.7 CNY每百万token）的参考估算，不回填运行时账本、不声称该 workspace 的最终账单；缺 usage 的调用另列。翻译按冻结 [DeepSeek 目录](https://api-docs.deepseek.com/quick_start/pricing/) 计费。', '',
            '| 课程 | 新 ASR 调用均值 | 旧 180s 调用均值 | 调用差分 | 新 ASR 目录价参考均值 CNY |','| --- | --- | --- | --- | --- |']
    for source,v in per_course.items():lines.append(f"| {source} | {v['asr_calls_mean']} | {v['old_180s_asr_calls_mean']} | {v['physical_call_delta']} | {v['asr_catalog_reference_mean_cny']:.6f} |")
    lines+=['','静音切分的全部调用/费用已包含于 ASR 总额，不重复相加。差分还受识别输出、输入、失败重试及旧试次未进入阶段影响，不全部归因于切分策略；旧缺失用量仍未知。', '',
            '| 候选 | 完整链路 | 观察终态秒 |','| --- | --- | --- |']
    for label,b in old.items():lines.append(f"| {label} | 0/10 | {display(b['terminal_seconds'])} |")
    lines.append(f"| P2-1b | {report['full_chain_successes']}/10 | {display(report['terminal_seconds'])} |")
    lines+=['','| 阶段/结果 | P1-3 秒 | P1-3b 秒 | P2-1b 秒 |','| --- | --- | --- | --- |']
    for stage in ['EXTRACT_AUDIO','TRANSCRIBE','TRANSLATE_SUBTITLES','GENERATE_LEARNING_PACKAGE']:
        for outcome in ['completed','failed']:
            values=[old[label]['separate_stage_seconds'].get(stage,{}).get(outcome,stats([])) for label in ['P1-3','P1-3b']]+[stage_stats.get(stage,{}).get(outcome,stats([]))]
            lines.append(f"| {stage}/{outcome} | "+' | '.join(display(v) for v in values)+' |')
    lines+=['','P1-3：8 翻译超时、1 资料 HTTP400、1 MQ 耗尽；P1-3b：10 次翻译失败。历史阶段观察与缺失 token 不补造；详细各阶段比较和费用缺失在 summary.json.baselines。输入切分、模型与功能完成范围不同，不给虚假同口径加速比。','',
            '## 独立恢复', '',f"任务 `{recovery[0]['task_id']}`，终态 {recovery[0]['status']}，端到端 {recovery[0]['elapsed_seconds']:.3f} 秒；故障注入={recovery[0]['fault_injected']}。",
            f"ASR：{cost_text(recovery[0]['asr_cost'])} CNY；翻译：{cost_text(recovery[0]['translation_cost'])} USD。",'',
            (f"中断前已完成 {proof['completed_batches_before']} 批，恢复后这些批次的 hash、attempt_count 与 attempt ID 集合保持不变：{proof['completed_batches_not_rerun']}。ASR 调用 {proof['asr_calls_before']}→{proof['asr_calls_after']}，无重跑：{proof['asr_not_rerun']}；epoch {proof['epoch_before']}→{proof['epoch_after']}。快照/策略不变：{proof['routes_unchanged']}/{proof['policy_unchanged']}；最终翻译已发布：{proof['final_translation_published']}。未知物理结果 {len(proof['unknown_physical_outcomes'])}，barrier 前已预留未出网 {len(proof['unsent_checkpoint_reservations'])}。逐批比对见 recovery-proof.json、recovery-before.json、recovery-after.json。" if 'completed_batches_before' in proof else f"恢复未注入：{proof['reason']}。"),'',
            (f"翻译 deadline 保持 {proof['translation_deadline_before']}：{proof['translation_deadline_unchanged']}；checkpoint 物理预留计数 {proof['checkpoint_physical_reservations_before']}→{proof['checkpoint_physical_reservations_after']}，accounted_tokens {proof['accounted_tokens_before']}→{proof['accounted_tokens_after']}（预留结算后可下降，不应误当单调累计 token）。" if 'translation_deadline_unchanged' in proof else ''),'',
            ('恢复 barrier 位于 provider 之前；可能已登记尚未出网的 checkpoint 预留，和真实物理调用分别列出。中断期间未知网络结果明确保留 UNKNOWN_OUTCOME。' if recovery[0]['fault_injected'] else '本次未进入 barrier，没有中断前/后的批次比对。ASR 403 后取消的在途请求保留 NETWORK_OUTCOME_UNKNOWN；不能据此声称已完成批次或 ASR 在重启后零重跑。'),'',
            f"30 对首/中/末源文与译文由 Codex 检查：明显含义冲突 {report['quality_sample_review']['observed_meaning_errors']}，术语/表达问题 {report['quality_sample_review']['terminology_style_issues']}（概率课两次将 collectively exhaustive 生硬译作“集体穷尽”）。这不是专家评分或整课教学质量验收，原抽样记录/问题保留在 quality-reviews.json。",'',
            '候选、原始事件、用量与恢复失败判断均可由本目录文件复算。未 push、未部署；进程关闭、生产配置与保护服务比对见 VERIFY.md。']
    (PUBLIC/'SUMMARY.md').write_text('\n'.join(lines)+'\n')
    (PUBLIC/'recovery-proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
