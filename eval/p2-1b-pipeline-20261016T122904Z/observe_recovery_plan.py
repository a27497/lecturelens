"""Read-only supplemental deadline/budget observations around the authorized recovery."""
import time
from runtime_support import *


def main():
    conn=db(deployment(),SCHEMA)
    until=time.monotonic()+1800
    recorded=False
    while time.monotonic()<until:
        guard()
        rows=[]
        for line in (PUBLIC/'trials.jsonl').read_text().splitlines():
            try:rows.append(json.loads(line))
            except json.JSONDecodeError:pass
        recovery=[r for r in rows if r['kind']=='RECOVERY' and r['phase']=='submitted']
        if recovery:
            task=recovery[0]['task_id']
            plan=query(conn,"""SELECT p.task_id,p.root_plan_hash,p.source_fingerprint,p.policy_hash,p.config_version,
                p.translation_started_at,p.translation_deadline,p.physical_calls,p.accounted_tokens,p.status,
                e.execution_epoch,e.resume_count,t.status task_status FROM translation_plan p
                JOIN task_execution e ON e.task_id=p.task_id JOIN analysis_task t ON t.id=p.task_id
                WHERE p.task_id=%s AND p.user_id=9 AND t.user_id=9""",(task,))
            barrier=PRIVATE/'recovery-barrier-reached'
            if plan and barrier.exists() and not recorded and plan[0]['execution_epoch']==1:
                save(PUBLIC/'recovery-plan-before-resume.json',dict(observed_at_utc=utc(),phase='barrier_reached_before_lease_recovery',plan=plan[0]))
                recorded=True
                print('RECOVERY_PLAN_BEFORE_RESUME_CAPTURED',flush=True)
            terminal=[r for r in rows if r['kind']=='RECOVERY' and r['phase']=='terminal']
            if terminal:
                assert plan and recorded,'Recovery plan must have a pre-resume observation'
                save(PUBLIC/'recovery-plan-after.json',dict(observed_at_utc=utc(),plan=plan[0]))
                print('RECOVERY_PLAN_AFTER_CAPTURED',flush=True)
                return
        time.sleep(1)
    raise RuntimeError('RECOVERY_PLAN_OBSERVER_TIMEOUT')


if __name__=='__main__':main()
