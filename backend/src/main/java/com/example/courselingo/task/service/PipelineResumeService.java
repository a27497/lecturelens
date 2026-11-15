package com.example.courselingo.task.service;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.mq.*;
import com.example.courselingo.subtitle.pipeline.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import java.sql.Timestamp;
import java.time.*;
import java.util.*;

@Service
public class PipelineResumeService {
    public record Result(String taskId,String status,long executionEpoch,long configVersion,long completedBatches,long remainingBatches) {}
    private final JdbcTemplate jdbc;
    private final PipelinePolicyService policies;
    private final PipelineSourceCheckpointStore sources;
    private final DurableTaskOutbox outbox;
    private final TransactionTemplate transaction;
    private final ObjectMapper json=new ObjectMapper();
    private com.example.courselingo.dispatch.BoundedTaskExecutor executor;
    private com.example.courselingo.task.claim.TaskClaimService claims;
    @org.springframework.beans.factory.annotation.Autowired(required=false)
    public void configureExecution(com.example.courselingo.dispatch.BoundedTaskExecutor executor,com.example.courselingo.task.claim.TaskClaimService claims){this.executor=executor;this.claims=claims;}

    public PipelineResumeService(JdbcTemplate jdbc,PipelinePolicyService policies,PipelineSourceCheckpointStore sources,
            DurableTaskOutbox outbox,PlatformTransactionManager manager) {
        this.jdbc=jdbc;this.policies=policies;this.sources=sources;this.outbox=outbox;transaction=new TransactionTemplate(manager);
    }
    public boolean checkpointed(String task,long user){return policies.find(task,user).map(p->p.policy().recovery()!=null).orElse(false);}

    public Result resume(String task,long user,long expectedEpoch) {
        return transaction.execute(status->{
            var owned=jdbc.queryForList("SELECT * FROM analysis_task WHERE id=? AND user_id=? AND deleted_at IS NULL FOR UPDATE",task,user);
            if(owned.isEmpty())throw new BusinessException(ErrorCode.TASK_NOT_FOUND);
            var row=owned.getFirst();
            var frozen=policies.find(task,user).orElseThrow(PipelineResumeService::conflict);
            var execution=jdbc.queryForList("SELECT * FROM task_execution WHERE task_id=? FOR UPDATE",task);
            if(!"FAILED".equals(row.get("status")) || execution.size()!=1 || ((Number)execution.getFirst().get("execution_epoch")).longValue()!=expectedEpoch
                || !eligible(frozen,execution.getFirst()))throw conflict();
            return queue(row,frozen,execution.getFirst());
        });
    }

    /** Invoked inside lease recovery's transaction; legacy policy versions retain their old behavior. */
    public boolean recoverExpired(String task) {
        var tasks=jdbc.queryForList("SELECT * FROM analysis_task WHERE id=? AND deleted_at IS NULL FOR UPDATE",task);
        if(tasks.isEmpty())return false;
        var row=tasks.getFirst();long user=((Number)row.get("user_id")).longValue();
        var frozen=policies.find(task,user);
        if(frozen.isEmpty() || frozen.get().policy().recovery()==null)return false;
        var e=jdbc.queryForMap("SELECT * FROM task_execution WHERE task_id=? FOR UPDATE",task);
        if(eligible(frozen.get(),e))queue(row,frozen.get(),e);
        else {
            jdbc.update("UPDATE analysis_task SET status='FAILED',error_code='PIPELINE_RECOVERY_EXHAUSTED',error_message='Frozen recovery budget unavailable',finished_at=CURRENT_TIMESTAMP WHERE id=?",task);
            jdbc.update("UPDATE task_execution SET completed_at=CURRENT_TIMESTAMP,lease_until=CURRENT_TIMESTAMP WHERE task_id=?",task);
        }
        return true;
    }
    private boolean eligible(PipelinePolicyService.Frozen frozen,Map<String,Object> e) {
        if(frozen.policy().recovery()==null || ((Number)e.get("protocol_version")).intValue()!=2
            || ((Number)e.get("resume_count")).intValue()>=frozen.policy().recovery().maxRecoveries() || !frozen.deadline().isAfter(now()))return false;
        String task=frozen.execution().taskId();long user=frozen.execution().userId();
        var media=jdbc.queryForMap("""
            SELECT u.file_md5,u.size_bytes,u.object_key,p.media_identity_hash FROM analysis_task t
            JOIN upload_session u ON u.id=t.upload_id AND u.user_id=t.user_id JOIN pipeline_policy_snapshot p ON p.task_id=t.id
            WHERE t.id=? AND t.user_id=? AND t.deleted_at IS NULL
            """,task,user);
        try {
            if(!PipelinePolicyService.hash(json.writeValueAsString(Arrays.asList(media.get("file_md5"),media.get("size_bytes"),media.get("object_key")))).equals(media.get("media_identity_hash")))return false;
        }catch(Exception ignored){return false;}
        var plans=jdbc.queryForList("SELECT * FROM translation_plan WHERE task_id=? AND user_id=?",task,user);
        if(plans.isEmpty())return true;
        var plan=plans.getFirst();
        if(!((Timestamp)jdbc.queryForObject("SELECT translation_deadline FROM translation_plan WHERE task_id=?",Timestamp.class,task)).toInstant().isAfter(now())
            || !TranscriptParagraphService.fingerprint(sources.source(task,user)).equals(plan.get("source_fingerprint")))return false;
        int remaining=jdbc.queryForObject("SELECT COUNT(*) FROM translation_batch WHERE task_id=? AND status<>'SUCCEEDED'",Integer.class,task);
        if(remaining>0 && (((Number)plan.get("physical_calls")).intValue()>=frozen.policy().maxCalls()
            || ((Number)plan.get("accounted_tokens")).longValue()>=frozen.policy().tokenBudget()))return false;
        return jdbc.queryForObject("""
            SELECT COUNT(*) FROM translation_batch WHERE task_id=? AND status NOT IN ('SUCCEEDED','SPLIT')
            AND (attempt_count>=? OR last_error_category IN ('AUTHENTICATION','MODEL_NOT_FOUND','INVALID_REQUEST',
              'SOURCE_CHANGED','SNAPSHOT_INVALID','SPLIT_DEPTH_EXHAUSTED','OUTPUT_BUDGET_TOO_SMALL','TOKEN_BUDGET_EXHAUSTED','CALL_BUDGET_EXHAUSTED'))
            """,Integer.class,task,frozen.policy().maxAttempts())==0;
    }
    private Result queue(Map<String,Object> task,PipelinePolicyService.Frozen frozen,Map<String,Object> e) {
        String id=(String)task.get("id");long user=((Number)task.get("user_id")).longValue();
        long epoch=((Number)e.get("execution_epoch")).longValue()+1;
        jdbc.update("UPDATE model_call_attempt SET status='UNKNOWN_OUTCOME',error_category='UNKNOWN_OUTCOME',usage_status='PROCESS_INTERRUPTED' WHERE task_id=? AND status='STARTED' AND execution_epoch<?",id,epoch);
        jdbc.update("""
            UPDATE task_execution SET execution_epoch=?,resume_count=resume_count+1,completed_at=CURRENT_TIMESTAMP,
            lease_until=CURRENT_TIMESTAMP WHERE task_id=?
            """,epoch,id);
        jdbc.update("""
            UPDATE analysis_task SET status='RETRYING',error_code=NULL,error_message=NULL,finished_at=NULL,updated_at=CURRENT_TIMESTAMP
            WHERE id=? AND user_id=?
            """,id,user);
        var message=new AnalysisTaskMessage(id,(String)task.get("upload_id"),user,(String)task.get("source_language"),(String)task.get("target_language"),
            UUID.randomUUID().toString(),"resume-"+UUID.randomUUID(),now(),2,epoch);
        outbox.send(AnalysisTaskMessageTag.ANALYSIS_RETRY,message);
        jdbc.update("INSERT INTO task_log(task_id,user_id,level,stage,message) VALUES(?,?,'INFO','TRANSLATE',?)",id,user,"Resume queued with frozen config, epoch="+epoch);
        long complete=jdbc.queryForObject("SELECT COUNT(*) FROM translation_batch WHERE task_id=? AND status='SUCCEEDED'",Long.class,id);
        long remaining=jdbc.queryForObject("SELECT COUNT(*) FROM translation_batch WHERE task_id=? AND status<>'SUCCEEDED'",Long.class,id);
        return new Result(id,"RETRYING",epoch,frozen.execution().configVersion(),complete,remaining);
    }

    @Scheduled(fixedDelayString="${courselingo.task.pipeline-deadline-poll-millis:10000}")
    public void expire() {
        var ids=jdbc.queryForList("""
            SELECT p.task_id FROM pipeline_policy_snapshot p JOIN analysis_task t ON t.id=p.task_id
            WHERE p.deadline<CURRENT_TIMESTAMP AND t.deleted_at IS NULL AND t.status<>'SUCCEEDED'
            AND JSON_CONTAINS_PATH(p.policy_json,'one','$.recovery')=1
            AND NOT EXISTS(SELECT 1 FROM pipeline_step_checkpoint c WHERE c.task_id=p.task_id AND c.step_name='EXPIRY_CLEANUP') LIMIT 100
            """,String.class);
        for(String id:ids) {
            String[] old=new String[1];
            transaction.executeWithoutResult(status->{
                var owned=jdbc.queryForList("SELECT * FROM analysis_task WHERE id=? AND deleted_at IS NULL FOR UPDATE",id);
                if(owned.isEmpty())return;var task=owned.getFirst();
                long user=((Number)task.get("user_id")).longValue();var frozen=policies.find(id,user);
                if(frozen.isEmpty() || frozen.get().policy().recovery()==null || frozen.get().deadline().isAfter(now()) || "SUCCEEDED".equals(task.get("status")))return;
                if(jdbc.queryForObject("SELECT COUNT(*) FROM pipeline_step_checkpoint WHERE task_id=? AND step_name='EXPIRY_CLEANUP'",Integer.class,id)>0)return;
                var executions=jdbc.queryForList("SELECT * FROM task_execution WHERE task_id=? FOR UPDATE",id);
                long epoch=executions.isEmpty()?0:((Number)executions.getFirst().get("execution_epoch")).longValue();
                if(!executions.isEmpty())old[0]=(String)executions.getFirst().get("event_id");
                jdbc.update("""
                    UPDATE analysis_task SET error_code=CASE WHEN status='CANCELED' THEN error_code ELSE 'PIPELINE_DEADLINE_EXCEEDED' END,
                    error_message=CASE WHEN status='CANCELED' THEN error_message ELSE 'Original task deadline exceeded' END,
                    finished_at=CASE WHEN status='CANCELED' THEN finished_at ELSE CURRENT_TIMESTAMP END,
                    status=CASE WHEN status='CANCELED' THEN status ELSE 'FAILED' END WHERE id=?
                    """,id);
                jdbc.update("UPDATE task_execution SET completed_at=CURRENT_TIMESTAMP,lease_until=CURRENT_TIMESTAMP WHERE task_id=?",id);
                jdbc.update("INSERT INTO pipeline_step_checkpoint(task_id,step_name,user_id,source_fingerprint,result_hash,payload_json,execution_epoch) VALUES(?,'EXPIRY_CLEANUP',?,REPEAT('0',64),REPEAT('0',64),'{}',?)",id,user,epoch);
                outbox.enqueueCleanup(id,user);
            });
            if(old[0]!=null) {if(executor!=null)executor.cancel(id);if(claims!=null)claims.release(id,old[0]);}
        }
    }
    private Instant now(){return jdbc.queryForObject("SELECT CURRENT_TIMESTAMP(3)",Timestamp.class).toInstant();}
    private static BusinessException conflict(){return new BusinessException(ErrorCode.TASK_RESUME_CONFLICT);}
}
