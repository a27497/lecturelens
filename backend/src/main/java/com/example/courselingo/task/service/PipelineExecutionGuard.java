package com.example.courselingo.task.service;

import com.example.courselingo.ai.llm.TranslationFailure;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class PipelineExecutionGuard {
    public record Identity(String taskId,long userId,String eventId,long epoch) {}
    private final JdbcTemplate jdbc;
    public PipelineExecutionGuard(JdbcTemplate jdbc){this.jdbc=jdbc;}
    /** Must be called inside the short transaction that writes the corresponding result. */
    public Identity lock(String task,long user,String event,Long expectedEpoch) {
        if(event==null)throw stale();
        var rows=jdbc.queryForList("""
            SELECT e.execution_epoch,p.deadline>=CURRENT_TIMESTAMP(3) AS within_deadline FROM analysis_task t JOIN task_execution e ON e.task_id=t.id
            JOIN pipeline_policy_snapshot p ON p.task_id=t.id AND p.user_id=t.user_id
            WHERE t.id=? AND t.user_id=? AND t.deleted_at IS NULL AND t.status='RUNNING'
            AND e.protocol_version=2 AND e.event_id=? AND e.completed_at IS NULL AND e.lease_until>=CURRENT_TIMESTAMP
            FOR UPDATE
            """,task,user,event);
        if(rows.size()!=1)throw stale();
        if(((Number)rows.getFirst().get("within_deadline")).intValue()!=1)
            throw TranslationFailure.of(TranslationFailure.Reason.DEADLINE_EXCEEDED);
        long epoch=((Number)rows.getFirst().get("execution_epoch")).longValue();
        if(expectedEpoch!=null && epoch!=expectedEpoch)throw stale();
        return new Identity(task,user,event,epoch);
    }
    public static TranslationFailure stale(){return TranslationFailure.of(TranslationFailure.Reason.CANCELED);}
}
