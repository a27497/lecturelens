package com.example.courselingo.subtitle.pipeline;

import com.example.courselingo.ai.asr.TranscriptTimingSource;
import com.example.courselingo.ai.llm.*;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.task.service.*;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import java.sql.Timestamp;
import java.time.*;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Supplier;

/** Task/source/epoch authority and attempt accounting commit before or after, never across model I/O. */
@Service
public class TranslationCheckpointStore {
    public record Input(int index,long start,long end,String text,String language,String timingSource,String timingReason) {}
    public record Item(int index,String text) {}
    public record Node(int number,int depth,String status,List<SubtitleSegment> source,List<TranslationBatchCoordinator.Translated> result) {}
    public record Attempt(String id,int number,long reserved) {}
    private final JdbcTemplate jdbc;
    private final TransactionTemplate transaction;
    private final PipelineExecutionGuard guard;
    private final PipelineSourceCheckpointStore sources;
    private final ObjectMapper json=new ObjectMapper();

    public TranslationCheckpointStore(JdbcTemplate jdbc,PlatformTransactionManager manager,PipelineExecutionGuard guard,PipelineSourceCheckpointStore sources) {
        this.jdbc=jdbc;transaction=new TransactionTemplate(manager);this.guard=guard;this.sources=sources;
    }
    public Session open(PipelinePolicyService.Frozen frozen,String event,List<SubtitleSegment> original,String language,String model,String provider) {
        if(frozen.policy().recovery()==null)return null;
        var identity=tx(()->guard.lock(frozen.execution().taskId(),frozen.execution().userId(),event,null));
        return new Session(frozen,identity,TranscriptParagraphService.fingerprintSource(original),language,model,provider);
    }
    public final class Session {
        private final PipelinePolicyService.Frozen frozen;
        private final PipelineExecutionGuard.Identity execution;
        private final String sourceHash,language,model,provider;
        private final ConcurrentHashMap<Integer,String> claims=new ConcurrentHashMap<>();
        private Session(PipelinePolicyService.Frozen frozen,PipelineExecutionGuard.Identity execution,String sourceHash,String language,String model,String provider) {
            this.frozen=frozen;this.execution=execution;this.sourceHash=sourceHash;this.language=language;this.model=model;this.provider=provider;
        }
        private String task(){return execution.taskId();}
        private long user(){return execution.userId();}
        private long version(){return frozen.execution().configVersion();}
        private void active(boolean checkPlanDeadline) {
            guard.lock(task(),user(),execution.eventId(),execution.epoch());
            if(!frozen.deadline().isAfter(now()))throw failure(TranslationFailure.Reason.DEADLINE_EXCEEDED);
            if(!sourceHash.equals(TranscriptParagraphService.fingerprint(sources.source(task(),user()))))throw failure(TranslationFailure.Reason.SOURCE_CHANGED);
            if(checkPlanDeadline) {
                var plan=plan();
                if(!instant(plan.get("translation_deadline")).isAfter(now()))throw failure(TranslationFailure.Reason.DEADLINE_EXCEEDED);
                if(!Objects.equals(plan.get("source_fingerprint"),sourceHash) || !Objects.equals(plan.get("policy_hash"),frozen.hash())
                    || ((Number)plan.get("config_version")).longValue()!=version())throw failure(TranslationFailure.Reason.SNAPSHOT_INVALID);
            }
        }
        public Instant initialize(List<List<SubtitleSegment>> roots,TranslationBatchCoordinator.Codec codec) {
            return tx(()->{
                active(false);
                String rootHash=PipelinePolicyService.hash(encode(roots.stream().map(TranslationCheckpointStore::input).toList()));
                var old=jdbc.queryForList("SELECT * FROM translation_plan WHERE task_id=? FOR UPDATE",task());
                if(old.isEmpty()) {
                    Instant started=now(),deadline=started.plusMillis(frozen.policy().totalTimeoutMillis());
                    if(frozen.deadline().isBefore(deadline))deadline=frozen.deadline();
                    jdbc.update("""
                        INSERT INTO translation_plan(task_id,user_id,snapshot_id,config_version,policy_hash,source_fingerprint,target_language,
                        root_plan_hash,next_batch_no,translation_started_at,translation_deadline) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                        """,task(),user(),frozen.execution().snapshotId(),version(),frozen.hash(),sourceHash,language,rootHash,roots.size()+1,
                        Timestamp.from(started),Timestamp.from(deadline));
                    for(int i=0;i<roots.size();i++)insert(i+1,null,null,0,roots.get(i),codec);
                } else {
                    var row=old.getFirst();
                    if(!rootHash.equals(row.get("root_plan_hash")) || !sourceHash.equals(row.get("source_fingerprint"))
                        || !language.equals(row.get("target_language")) || !frozen.execution().snapshotId().equals(row.get("snapshot_id")))
                        throw failure(TranslationFailure.Reason.SOURCE_CHANGED);
                    jdbc.update("""
                        UPDATE translation_attempt SET status='UNKNOWN_OUTCOME',error_category='UNKNOWN_OUTCOME'
                        WHERE task_id=? AND config_version=? AND status='STARTED' AND execution_epoch<?
                        """,task(),version(),execution.epoch());
                }
                active(true);
                return instant(plan().get("translation_deadline"));
            });
        }
        private Map<String,Object> plan(){return jdbc.queryForMap("SELECT * FROM translation_plan WHERE task_id=? AND user_id=? FOR UPDATE",task(),user());}
        private void insert(int number,Integer parent,Integer ordinal,int depth,List<SubtitleSegment> source,TranslationBatchCoordinator.Codec codec) {
            String payload=encode(input(source));String request=encode(codec.planningRequest(source).messages());
            jdbc.update("""
                INSERT INTO translation_batch(task_id,batch_no,config_version,parent_batch_no,child_ordinal,depth,source_json,source_hash,request_hash)
                VALUES(?,?,?,?,?,?,?,?,?)
                """,task(),number,version(),parent,ordinal,depth,payload,PipelinePolicyService.hash(payload),PipelinePolicyService.hash(request));
        }
        public Node claim(int number) {
            return tx(()->{
                active(true);var row=batch(number);
                String status=(String)row.get("status");
                if(!"SUCCEEDED".equals(status)) {
                    String own=claims.get(number);
                    long owner=row.get("claim_epoch")==null?0:((Number)row.get("claim_epoch")).longValue();
                    if(owner==execution.epoch() && row.get("claim_token")!=null && !Objects.equals(row.get("claim_token"),own)
                        && row.get("claim_until")!=null && instant(row.get("claim_until")).isAfter(now()))throw failure(TranslationFailure.Reason.CANCELED);
                    String token=own==null?UUID.randomUUID().toString():own;claims.put(number,token);
                    jdbc.update("""
                        UPDATE translation_batch SET claim_epoch=?,claim_token=?,claim_until=DATE_ADD(CURRENT_TIMESTAMP(3),INTERVAL 90 SECOND),
                        status=CASE WHEN status='SPLIT' THEN 'SPLIT' ELSE 'RUNNING' END WHERE task_id=? AND batch_no=? AND config_version=?
                        """,execution.epoch(),token,task(),number,version());
                }
                return node(row);
            });
        }
        private Map<String,Object> batch(int number) {
            return jdbc.queryForMap("SELECT * FROM translation_batch WHERE task_id=? AND batch_no=? AND config_version=? FOR UPDATE",task(),number,version());
        }
        private void own(int number) {
            var row=batch(number);
            if(!Objects.equals(row.get("claim_token"),claims.get(number)) || row.get("claim_epoch")==null
                || ((Number)row.get("claim_epoch")).longValue()!=execution.epoch())throw failure(TranslationFailure.Reason.CANCELED);
        }
        private Node node(Map<String,Object> row) {
            try {
                var inputs=json.readValue((String)row.get("source_json"),new TypeReference<List<Input>>(){});
                if(!PipelinePolicyService.hash(encode(inputs)).equals(row.get("source_hash")))throw failure(TranslationFailure.Reason.SOURCE_CHANGED);
                var source=inputs.stream().map(i->toSource(i,task(),user())).toList();
                List<TranslationBatchCoordinator.Translated> result=List.of();
                if("SUCCEEDED".equals(row.get("status"))) {
                    var items=json.readValue((String)row.get("result_json"),new TypeReference<List<Item>>(){});
                    if(!PipelinePolicyService.hash(encode(items)).equals(row.get("result_hash")))throw failure(TranslationFailure.Reason.SOURCE_CHANGED);
                    result=items.stream().map(i->new TranslationBatchCoordinator.Translated(source.stream().filter(s->s.getSegmentIndex()==i.index()).findFirst().orElseThrow(),i.text())).toList();
                    validateResult(source,result);
                }
                return new Node(((Number)row.get("batch_no")).intValue(),((Number)row.get("depth")).intValue(),(String)row.get("status"),source,result);
            } catch(TranslationFailure safe){throw safe;}
            catch(Exception ignored){throw failure(TranslationFailure.Reason.SOURCE_CHANGED);}
        }
        public LlmResult cached(Node node) {
            return new LlmResult(provider,model,encode(items(node.result())),"stop",null,Duration.ZERO,Map.of("checkpointReused",true));
        }
        public Attempt begin(int number,int input,int output) {
            return tx(()->{
                active(true);own(number);var row=batch(number);var plan=plan();
                int next=((Number)row.get("attempt_count")).intValue()+1;
                if(next>frozen.policy().maxAttempts())throw failure(TranslationFailure.Reason.CALL_BUDGET_EXHAUSTED);
                if(((Number)plan.get("physical_calls")).intValue()>=frozen.policy().maxCalls())throw failure(TranslationFailure.Reason.CALL_BUDGET_EXHAUSTED);
                long reserve=(long)input+output;
                if(((Number)plan.get("accounted_tokens")).longValue()+reserve>frozen.policy().tokenBudget())throw failure(TranslationFailure.Reason.TOKEN_BUDGET_EXHAUSTED);
                String id=UUID.randomUUID().toString();
                jdbc.update("UPDATE translation_plan SET physical_calls=physical_calls+1,accounted_tokens=accounted_tokens+? WHERE task_id=?",reserve,task());
                jdbc.update("UPDATE translation_batch SET attempt_count=? WHERE task_id=? AND batch_no=? AND config_version=?",next,task(),number,version());
                jdbc.update("""
                    INSERT INTO translation_attempt(id,task_id,batch_no,config_version,attempt_no,execution_epoch,status,output_limit,
                    estimated_input_tokens,reserved_tokens,accounted_tokens) VALUES(?,?,?,?,?,?,'STARTED',?,?,?,?)
                    """,id,task(),number,version(),next,execution.epoch(),output,input,reserve,reserve);
                return new Attempt(id,next,reserve);
            });
        }
        public void succeeded(int number,Attempt attempt,List<TranslationBatchCoordinator.Translated> result,LlmResult response,long millis) {
            try {
                tx(()->{active(true);own(number);account(attempt,response.usage(),response.finishReason(),null,millis,"SUCCEEDED");complete(number,result);return null;});
            } catch(TranslationFailure failure) {
                lateUsage(attempt,response.usage(),response.finishReason(),null,millis);throw failure;
            }
        }
        public void failed(int number,Attempt attempt,TranslationFailure failure,long millis) {
            tx(()->{
                // Physical usage is a fact even if the originating worker has lost its lease.
                if(jdbc.queryForList("SELECT id FROM analysis_task WHERE id=? AND user_id=? AND deleted_at IS NULL FOR UPDATE",task(),user()).isEmpty())return null;
                account(attempt,failure.usage(),failure.finishReason(),failure.reason().name(),millis,"FAILED");
                if(attempt!=null) {
                    jdbc.update("UPDATE translation_attempt SET validation_check=? WHERE id=? AND task_id=?",failure.check()==null?null:failure.check().name(),attempt.id(),task());
                    jdbc.update("UPDATE model_call_attempt SET error_category=?,validation_check=? WHERE translation_attempt_id=? AND task_id=?",
                        failure.reason().name(),failure.check()==null?null:failure.check().name(),attempt.id(),task());
                }
                jdbc.update("""
                    UPDATE translation_batch b JOIN task_execution e ON e.task_id=b.task_id SET b.last_error_category=?
                    WHERE b.task_id=? AND b.batch_no=? AND b.config_version=? AND b.claim_epoch=? AND b.claim_token=?
                    AND b.status<>'SUCCEEDED' AND e.execution_epoch=? AND e.event_id=? AND e.completed_at IS NULL
                    AND e.lease_until>=CURRENT_TIMESTAMP
                    """,failure.reason().name(),task(),number,version(),execution.epoch(),claims.get(number),execution.epoch(),execution.eventId());
                return null;
            });
        }
        private void lateUsage(Attempt attempt,LlmUsage usage,String finish,String error,long millis) {
            tx(()->{
                if(jdbc.queryForList("SELECT id FROM analysis_task WHERE id=? AND user_id=? AND deleted_at IS NULL FOR UPDATE",task(),user()).isEmpty())return null;
                account(attempt,usage,finish,"STALE_EXECUTION",millis,"STALE_FINISHED");return null;
            });
        }
        private void account(Attempt attempt,LlmUsage usage,String finish,String error,long millis,String status) {
            if(attempt==null)return;
            var rows=jdbc.queryForList("SELECT * FROM translation_attempt WHERE id=? AND task_id=? AND config_version=? AND execution_epoch=? FOR UPDATE",
                attempt.id(),task(),version(),execution.epoch());
            if(rows.isEmpty())return;
            var old=rows.getFirst();
            if(old.get("completed_at")!=null)return;
            var safe=usage==null?new LlmUsage(null,null,null):usage;
            var receipts=jdbc.queryForList("SELECT prompt_tokens,completion_tokens,total_tokens,reasoning_tokens,cache_hit_tokens,cache_miss_tokens FROM model_call_attempt WHERE translation_attempt_id=? AND task_id=?",attempt.id(),task());
            if(!receipts.isEmpty()) {
                var receipt=receipts.getFirst();
                safe=new LlmUsage(known(safe.promptTokens(),receipt.get("prompt_tokens")),known(safe.completionTokens(),receipt.get("completion_tokens")),
                    known(safe.totalTokens(),receipt.get("total_tokens")),known(safe.reasoningTokens(),receipt.get("reasoning_tokens")),
                    known(safe.cacheHitTokens(),receipt.get("cache_hit_tokens")),known(safe.cacheMissTokens(),receipt.get("cache_miss_tokens")));
            }
            long actual=safe.totalTokens()==null?attempt.reserved():safe.totalTokens();
            if(safe.promptTokens()!=null && safe.completionTokens()!=null)actual=Math.max(safe.totalTokens()==null?0:actual,(long)safe.promptTokens()+safe.completionTokens());
            jdbc.update("UPDATE translation_plan SET accounted_tokens=accounted_tokens+? WHERE task_id=?",actual-((Number)old.get("accounted_tokens")).longValue(),task());
            jdbc.update("""
                UPDATE translation_attempt SET status=?,prompt_tokens=?,completion_tokens=?,total_tokens=?,finish_reason=?,error_category=?,
                duration_millis=?,accounted_tokens=?,reasoning_tokens=?,cache_hit_tokens=?,cache_miss_tokens=?,usage_status=?,completed_at=CURRENT_TIMESTAMP(3) WHERE id=?
                """,status,safe.promptTokens(),safe.completionTokens(),safe.totalTokens(),safeFinish(finish),error,Math.max(0,millis),actual,
                safe.reasoningTokens(),safe.cacheHitTokens(),safe.cacheMissTokens(),com.example.courselingo.task.usage.PipelineUsageLedger.usageStatus(safe,null),attempt.id());
        }
        public List<Node> children(int parent) {
            return tx(()->{active(true);own(parent);return jdbc.queryForList("SELECT * FROM translation_batch WHERE task_id=? AND config_version=? AND parent_batch_no=? ORDER BY child_ordinal",task(),version(),parent)
                .stream().map(this::node).toList();});
        }
        public List<Node> split(int parent,List<List<SubtitleSegment>> parts,int depth,TranslationBatchCoordinator.Codec codec) {
            return tx(()->{
                active(true);own(parent);var existing=children(parent);
                if(!existing.isEmpty())return existing;
                if(depth>frozen.policy().maxDepth() || parts.size()!=2)throw failure(TranslationFailure.Reason.SPLIT_DEPTH_EXHAUSTED);
                var plan=plan();int next=((Number)plan.get("next_batch_no")).intValue();
                for(int i=0;i<parts.size();i++)insert(next+i,parent,i,depth,parts.get(i),codec);
                jdbc.update("UPDATE translation_plan SET next_batch_no=? WHERE task_id=?",next+parts.size(),task());
                jdbc.update("UPDATE translation_batch SET status='SPLIT' WHERE task_id=? AND batch_no=? AND config_version=?",task(),parent,version());
                return children(parent);
            });
        }
        public void merged(int number,List<TranslationBatchCoordinator.Translated> result) {
            tx(()->{
                active(true);own(number);var child=children(number);
                if(child.size()!=2 || child.stream().anyMatch(c->!c.status().equals("SUCCEEDED")))throw failure(TranslationFailure.Reason.SOURCE_CHANGED);
                complete(number,result);return null;
            });
        }
        private void complete(int number,List<TranslationBatchCoordinator.Translated> result) {
            var row=batch(number);validateResult(node(row).source(),result);
            String encoded=encode(items(result));
            jdbc.update("UPDATE translation_batch SET status='SUCCEEDED',result_json=?,result_hash=?,claim_until=NULL WHERE task_id=? AND batch_no=? AND config_version=? AND claim_epoch=? AND claim_token=?",
                encoded,PipelinePolicyService.hash(encoded),task(),number,version(),execution.epoch(),claims.get(number));
        }
        public void failNode(int number,TranslationFailure failure) {
            tx(()->{
                // A stale callback is not allowed to downgrade a completed node or a new worker's claim.
                if(jdbc.queryForList("""
                    SELECT t.id FROM analysis_task t JOIN task_execution e ON e.task_id=t.id WHERE t.id=? AND t.user_id=?
                    AND t.deleted_at IS NULL AND t.status='RUNNING' AND e.execution_epoch=? AND e.event_id=?
                    AND e.completed_at IS NULL AND e.lease_until>=CURRENT_TIMESTAMP FOR UPDATE
                    """,task(),user(),execution.epoch(),execution.eventId()).isEmpty())return null;
                jdbc.update("""
                    UPDATE translation_batch b JOIN task_execution e ON e.task_id=b.task_id
                    SET b.status='FAILED',b.last_error_category=? WHERE b.task_id=? AND b.batch_no=? AND b.config_version=?
                    AND b.claim_epoch=? AND b.claim_token=? AND b.status NOT IN ('SUCCEEDED','SPLIT')
                    AND e.execution_epoch=? AND e.event_id=? AND e.completed_at IS NULL
                    """,failure.reason().name(),task(),number,version(),execution.epoch(),claims.get(number),execution.epoch(),execution.eventId());
                return null;
            });
        }
        public void publish(Runnable persist) {
            tx(()->{
                active(true);
                if(jdbc.queryForObject("SELECT COUNT(*) FROM translation_batch WHERE task_id=? AND config_version=? AND status<>'SUCCEEDED'",Integer.class,task(),version())!=0)
                    throw failure(TranslationFailure.Reason.SOURCE_CHANGED);
                persist.run();jdbc.update("UPDATE translation_plan SET status='PUBLISHED' WHERE task_id=?",task());return null;
            });
        }
    }
    private static List<Input> input(List<SubtitleSegment> source) {
        return source.stream().map(s->new Input(s.getSegmentIndex(),s.getStartMillis(),s.getEndMillis(),s.getText(),s.getLanguage(),s.getTimingSource(),s.getTimingReason())).toList();
    }
    private static SubtitleSegment toSource(Input i,String task,long user) {
        var s=new SubtitleSegment();s.setTaskId(task);s.setUserId(user);s.setSegmentIndex(i.index());s.setStartMillis(i.start());s.setEndMillis(i.end());
        s.setText(i.text());s.setLanguage(i.language());s.setTimingSource(TranscriptTimingSource.valueOf(i.timingSource()).name());s.setTimingReason(i.timingReason());s.setProvider("checkpoint");return s;
    }
    private static List<Item> items(List<TranslationBatchCoordinator.Translated> result){return result.stream().map(t->new Item(t.source().getSegmentIndex(),t.text())).toList();}
    private static void validateResult(List<SubtitleSegment> source,List<TranslationBatchCoordinator.Translated> result) {
        if(result.size()!=source.size() || result.stream().anyMatch(t->t.text()==null || t.text().isBlank())
            || !source.stream().map(SubtitleSegment::getSegmentIndex).toList().equals(result.stream().map(t->t.source().getSegmentIndex()).toList()))
            throw failure(TranslationFailure.Reason.SOURCE_CHANGED);
    }
    private String encode(Object value){try{return json.writeValueAsString(value);}catch(Exception ignored){throw failure(TranslationFailure.Reason.SOURCE_CHANGED);}}
    private Instant now(){return jdbc.queryForObject("SELECT CURRENT_TIMESTAMP(3)",Timestamp.class).toInstant();}
    private static Instant instant(Object value){return value instanceof Timestamp t?t.toInstant():((java.time.LocalDateTime)value).toInstant(ZoneOffset.UTC);}
    private static String safeFinish(String value){return value!=null && Set.of("stop","length","content_filter","tool_calls","aborted","insufficient_system_resource").contains(value)?value:null;}
    private static Integer known(Integer supplied,Object observed){return supplied!=null?supplied:observed instanceof Number number?number.intValue():null;}
    private <T> T tx(Supplier<T> action) {
        try{return transaction.execute(status->action.get());}
        catch(TranslationFailure safe){throw safe;}
        catch(RuntimeException ignored){throw failure(TranslationFailure.Reason.ACCOUNTING_INCOMPLETE);}
    }
    private static TranslationFailure failure(TranslationFailure.Reason reason){return TranslationFailure.of(reason);}
}
