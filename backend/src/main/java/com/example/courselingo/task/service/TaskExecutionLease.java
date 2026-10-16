package com.example.courselingo.task.service;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.mq.AnalysisTaskMessage;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** Legacy tasks fail on crash; checkpointed tasks acquire a new fenced execution epoch. */
@Service
public class TaskExecutionLease {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate transaction;
    private record Active(String event,int protocol,long epoch) {}
    private final ConcurrentHashMap<String, Active> active = new ConcurrentHashMap<>();
    private PipelineResumeService recovery;
    @org.springframework.beans.factory.annotation.Autowired(required=false)
    public void configureRecovery(PipelineResumeService recovery){this.recovery=recovery;}

    public TaskExecutionLease(JdbcTemplate jdbc, PlatformTransactionManager manager) {
        this.jdbc = jdbc;
        transaction = new TransactionTemplate(manager);
    }

    public void open(AnalysisTaskMessage message) {
        transaction.executeWithoutResult(status -> {
            var rows = jdbc.queryForList("""
                SELECT status FROM analysis_task WHERE id=? AND user_id=? AND deleted_at IS NULL FOR UPDATE
                """, message.taskId(), message.userId());
            if (rows.isEmpty() || !"QUEUED".equals(rows.getFirst().get("status"))) throw rejected();
            if(message.protocol()==2 && recovery==null)throw rejected();
            if(recovery!=null && recovery.checkpointed(message.taskId(),message.userId())!=(message.protocol()==2))throw rejected();
            if(message.protocol()==2) {
                if(jdbc.queryForList("SELECT task_id FROM pipeline_policy_snapshot WHERE task_id=? AND user_id=? AND deadline>CURRENT_TIMESTAMP(3)",message.taskId(),message.userId()).isEmpty())throw rejected();
                var previous=jdbc.queryForList("SELECT * FROM task_execution WHERE task_id=? FOR UPDATE",message.taskId());
                if(previous.isEmpty()) {
                    if(message.epoch()!=1)throw rejected();
                    jdbc.update("INSERT INTO task_execution(task_id,event_id,lease_until,protocol_version,execution_epoch) VALUES(?,?,?,2,?)",
                        message.taskId(),message.requestId(),Timestamp.from(Instant.now().plusSeconds(90)),message.epoch());
                } else {
                    var old=previous.getFirst();
                    if(((Number)old.get("protocol_version")).intValue()!=2 || ((Number)old.get("execution_epoch")).longValue()!=message.epoch()
                        || old.get("completed_at")==null)throw rejected();
                    jdbc.update("UPDATE task_execution SET event_id=?,lease_until=?,completed_at=NULL WHERE task_id=? AND execution_epoch=?",
                        message.requestId(),Timestamp.from(Instant.now().plusSeconds(90)),message.taskId(),message.epoch());
                }
                return;
            }
            if (!jdbc.queryForList("SELECT task_id FROM task_execution WHERE task_id=?", message.taskId()).isEmpty()) {
                throw rejected();
            }
            jdbc.update("INSERT INTO task_execution(task_id,event_id,lease_until) VALUES (?,?,?)",
                message.taskId(), message.requestId(), Timestamp.from(Instant.now().plusSeconds(90)));
        });
        active.put(message.taskId(), new Active(message.requestId(),message.protocol(),message.epoch()));
    }

    /** Serialize final success with recovery and logical deletion, and reject expired workers immediately. */
    public void publishSuccess(AnalysisTaskMessage message, Runnable publish) {
        transaction.executeWithoutResult(status -> {
            if (jdbc.queryForList("SELECT id FROM analysis_task WHERE id=? AND user_id=? AND deleted_at IS NULL FOR UPDATE",
                message.taskId(), message.userId()).isEmpty()) throw rejected();
            if (jdbc.queryForList("""
                SELECT task_id FROM task_execution WHERE task_id=? AND event_id=? AND completed_at IS NULL
                AND lease_until>=CURRENT_TIMESTAMP FOR UPDATE
                """, message.taskId(), message.requestId()).isEmpty()) throw rejected();
            if(message.protocol()==2 && jdbc.queryForList("SELECT task_id FROM task_execution WHERE task_id=? AND protocol_version=2 AND execution_epoch=?",message.taskId(),message.epoch()).isEmpty())throw rejected();
            if(message.protocol()==2 && jdbc.queryForList("SELECT task_id FROM pipeline_policy_snapshot WHERE task_id=? AND user_id=? AND deadline>CURRENT_TIMESTAMP(3)",message.taskId(),message.userId()).isEmpty())throw rejected();
            if(message.protocol()==2 && jdbc.queryForObject("SELECT COUNT(*) FROM model_call_attempt WHERE task_id=? AND status='STARTED'",Integer.class,message.taskId())>0)
                throw com.example.courselingo.ai.llm.TranslationFailure.of(com.example.courselingo.ai.llm.TranslationFailure.Reason.ACCOUNTING_INCOMPLETE);
            publish.run();
        });
    }

    public void close(AnalysisTaskMessage message) {
        active.remove(message.taskId(), new Active(message.requestId(),message.protocol(),message.epoch()));
        if(message.protocol()==2) {
            jdbc.update("""
                UPDATE task_execution SET lease_until=CURRENT_TIMESTAMP,
                completed_at=CASE WHEN EXISTS(SELECT 1 FROM analysis_task WHERE id=? AND status IN ('SUCCEEDED','FAILED','CANCELED'))
                THEN CURRENT_TIMESTAMP ELSE NULL END WHERE task_id=? AND event_id=? AND protocol_version=2 AND execution_epoch=?
                """,message.taskId(),message.taskId(),message.requestId(),message.epoch());
            return;
        }
        jdbc.update("""
            UPDATE task_execution SET lease_until=CURRENT_TIMESTAMP,
            completed_at=CASE WHEN EXISTS(SELECT 1 FROM analysis_task WHERE id=? AND status IN ('SUCCEEDED','FAILED','CANCELED'))
            THEN CURRENT_TIMESTAMP ELSE NULL END WHERE task_id=? AND event_id=?
            """, message.taskId(),
            message.taskId(), message.requestId());
    }

    @Scheduled(fixedDelayString = "${courselingo.task.lease.heartbeat-millis:15000}")
    public void heartbeat() {
        active.forEach((taskId, entry) -> {
            if(entry.protocol()==2) {
                jdbc.update("UPDATE task_execution SET lease_until=? WHERE task_id=? AND event_id=? AND execution_epoch=? AND completed_at IS NULL AND lease_until>=CURRENT_TIMESTAMP",
                    Timestamp.from(Instant.now().plusSeconds(90)),taskId,entry.event(),entry.epoch());
                jdbc.update("""
                    UPDATE translation_batch b JOIN task_execution e ON e.task_id=b.task_id
                    SET b.claim_until=DATE_ADD(CURRENT_TIMESTAMP(3),INTERVAL 90 SECOND)
                    WHERE b.task_id=? AND b.claim_epoch=? AND e.execution_epoch=? AND e.event_id=? AND e.completed_at IS NULL
                    AND e.lease_until>=CURRENT_TIMESTAMP AND b.status IN ('RUNNING','SPLIT')
                    """,taskId,entry.epoch(),entry.epoch(),entry.event());
                return;
            }
            jdbc.update("""
            UPDATE task_execution SET lease_until=? WHERE task_id=? AND event_id=?
            AND completed_at IS NULL AND lease_until>=CURRENT_TIMESTAMP
            """, Timestamp.from(Instant.now().plusSeconds(90)), taskId, entry.event());
        });
    }

    @Scheduled(fixedDelayString = "${courselingo.task.lease.recovery-millis:30000}")
    public void recoverExpired() {
        transaction.executeWithoutResult(status -> {
            var rows = jdbc.queryForList("""
                SELECT t.id FROM analysis_task t JOIN task_execution e ON t.id=e.task_id
                WHERE e.lease_until<CURRENT_TIMESTAMP AND e.completed_at IS NULL
                  AND t.status IN ('QUEUED','RUNNING') AND t.deleted_at IS NULL
                ORDER BY t.id LIMIT 100 FOR UPDATE SKIP LOCKED
                """);
            for (var row : rows) {
                String taskId = (String) row.get("id");
                if(recovery!=null && recovery.recoverExpired(taskId))continue;
                jdbc.update("""
                    UPDATE analysis_task SET status='FAILED',content_revision=content_revision+1,
                    error_code='TASK_EXECUTION_INTERRUPTED',error_message='Worker lease expired; create a retry task',
                    finished_at=CURRENT_TIMESTAMP WHERE id=?
                    """, taskId);
                jdbc.update("UPDATE task_execution SET completed_at=CURRENT_TIMESTAMP WHERE task_id=?", taskId);
            }
        });
    }

    public String previousClaim(AnalysisTaskMessage message) {
        if(message.protocol()!=2)return null;
        return transaction.execute(status->{
            if(recovery==null || !recovery.checkpointed(message.taskId(),message.userId()))throw rejected();
            var task=jdbc.queryForList("SELECT status FROM analysis_task WHERE id=? AND user_id=? AND deleted_at IS NULL FOR UPDATE",message.taskId(),message.userId());
            if(task.isEmpty() || !java.util.List.of("QUEUED","RETRYING").contains(task.getFirst().get("status")))throw rejected();
            var rows=jdbc.queryForList("SELECT * FROM task_execution WHERE task_id=? FOR UPDATE",message.taskId());
            if(rows.isEmpty()){if(message.epoch()!=1)throw rejected();return null;}
            var e=rows.getFirst();
            if(((Number)e.get("protocol_version")).intValue()!=2 || ((Number)e.get("execution_epoch")).longValue()!=message.epoch())throw rejected();
            return e.get("completed_at")==null?null:(String)e.get("event_id");
        });
    }
    public void publishQueued(AnalysisTaskMessage message,Runnable publish) {
        transaction.executeWithoutResult(status->{previousClaim(message);publish.run();});
    }
    public boolean publishFailure(AnalysisTaskMessage message,Runnable publish) {
        if(message.protocol()!=2){publish.run();return true;}
        return Boolean.TRUE.equals(transaction.execute(status->{
            var owned=jdbc.queryForList("""
                SELECT t.id FROM analysis_task t JOIN task_execution e ON e.task_id=t.id WHERE t.id=? AND t.user_id=? AND t.deleted_at IS NULL
                AND t.status='RUNNING' AND e.event_id=? AND e.execution_epoch=? AND e.protocol_version=2
                AND e.completed_at IS NULL AND e.lease_until>=CURRENT_TIMESTAMP FOR UPDATE
                """,message.taskId(),message.userId(),message.requestId(),message.epoch());
            if(owned.isEmpty())return false;publish.run();return true;
        }));
    }

    private static BusinessException rejected() { return new BusinessException(ErrorCode.TASK_INVALID_STATUS); }
}
