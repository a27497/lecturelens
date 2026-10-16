package com.example.courselingo.subtitle.pipeline;

import com.example.courselingo.ai.llm.TranslationFailure;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import java.sql.Timestamp;
import java.util.function.Consumer;

@Service
public class TranslationSchedulerEvents {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate transaction;
    public TranslationSchedulerEvents(JdbcTemplate jdbc,PlatformTransactionManager manager){this.jdbc=jdbc;transaction=new TransactionTemplate(manager);}
    public Consumer<AdaptiveTranslationController.Event> observer(PipelinePolicyService.Frozen frozen) {
        return event->append(frozen,event);
    }
    private void append(PipelinePolicyService.Frozen frozen,AdaptiveTranslationController.Event e) {
        try {
            transaction.executeWithoutResult(status->{
                var ref=frozen.execution();
                if(jdbc.queryForList("SELECT id FROM analysis_task WHERE id=? AND user_id=? AND deleted_at IS NULL FOR UPDATE",ref.taskId(),ref.userId()).size()!=1)
                    throw TranslationFailure.of(TranslationFailure.Reason.CANCELED);
                var state=jdbc.queryForList("SELECT last_event_seq FROM translation_scheduler_state WHERE task_id=? AND user_id=? FOR UPDATE",ref.taskId(),ref.userId());
                long seq=state.isEmpty()?1:((Number)state.getFirst().get("last_event_seq")).longValue()+1;
                String reason="START".equals(e.reason()) && !state.isEmpty()?"RECOVERY_RESET":e.reason();
                if(state.isEmpty()) jdbc.update("""
                    INSERT INTO translation_scheduler_state(task_id,user_id,config_version,policy_hash,window_epoch,window_size,
                    success_streak,cooldown_until_millis,last_event_seq,revision) VALUES(?,?,?,?,?,?,?,?,?,0)
                    """,ref.taskId(),ref.userId(),ref.configVersion(),frozen.hash(),e.windowEpoch(),e.window(),e.streak(),e.cooldownUntilMillis(),seq);
                else if(jdbc.update("""
                    UPDATE translation_scheduler_state SET window_epoch=?,window_size=?,success_streak=?,cooldown_until_millis=?,
                    last_event_seq=?,revision=revision+1 WHERE task_id=? AND user_id=? AND policy_hash=? AND config_version=?
                    """,e.windowEpoch(),e.window(),e.streak(),e.cooldownUntilMillis(),seq,ref.taskId(),ref.userId(),frozen.hash(),ref.configVersion())!=1)
                    throw TranslationFailure.of(TranslationFailure.Reason.SNAPSHOT_INVALID);
                jdbc.update("""
                    INSERT INTO translation_scheduler_event(task_id,event_seq,user_id,config_version,policy_hash,event_time,old_window,
                    new_window,inflight,window_epoch,success_streak,reason,batch_no,attempt_no,cooldown_until_millis)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,ref.taskId(),seq,ref.userId(),ref.configVersion(),frozen.hash(),Timestamp.from(e.time()),e.oldWindow(),e.window(),
                    e.inflight(),e.windowEpoch(),e.streak(),reason,e.batchNo(),e.attemptNo(),e.cooldownUntilMillis());
            });
        } catch(TranslationFailure safe){throw safe;}
        catch(RuntimeException ignored){throw TranslationFailure.of(TranslationFailure.Reason.ACCOUNTING_INCOMPLETE);}
    }
}
