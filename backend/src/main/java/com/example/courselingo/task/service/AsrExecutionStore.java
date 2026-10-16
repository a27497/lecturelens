package com.example.courselingo.task.service;

import com.example.courselingo.ai.asr.*;

import com.example.courselingo.ai.llm.TranslationFailure;
import com.example.courselingo.media.SilenceAudioChunkPlanner;
import com.example.courselingo.subtitle.pipeline.PipelinePolicyService;
import com.example.courselingo.task.service.PipelineExecutionGuard;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.sql.Timestamp;
import java.time.*;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** Short, fenced transactions around model I/O; physical attempt reservations survive process death. */
@Service
public class AsrExecutionStore {
    private final JdbcTemplate jdbc;
    private final PipelineExecutionGuard guard;
    private final TransactionTemplate transactions;
    private final ObjectMapper json = new ObjectMapper();

    public AsrExecutionStore(JdbcTemplate jdbc, PipelineExecutionGuard guard, PlatformTransactionManager manager) {
        this.jdbc=jdbc;this.guard=guard;transactions=new TransactionTemplate(manager);
    }
    public record Permit(int chunk, int attempt) {}
    public record Stored(String provider,String language,String text,List<TranscribedSegment> segments,long audioMillis,String timing) {
        public static Stored from(SpeechToTextResult result) {
            if (result == null || result.fullText().isBlank() && result.segments().isEmpty()
                || result != null && result.segments().stream().anyMatch(s -> s.text()==null || s.text().isBlank()
                    || s.startMillis()<0 || s.endMillis()<s.startMillis()))
                throw new AsrCallFailure(AsrCallFailure.Category.OUTPUT_INVALID,false,null);
            return new Stored(result.provider(),result.language(),result.fullText(),result.segments(),result.audioDurationMillis(),
                result.metadata().get("segmentTimingSource") instanceof String text ? text : null);
        }
        SpeechToTextResult result() {
            return new SpeechToTextResult(provider,language,text,segments,Duration.ZERO,audioMillis,
                timing==null?Map.of():Map.of("segmentTimingSource",timing));
        }
    }

    public Session open(PipelinePolicyService.Frozen frozen,String event,long epoch,SilenceAudioChunkPlanner.Plan plan,String audioHash) {
        if(frozen.policy().asr()==null)throw new IllegalArgumentException("Missing frozen ASR policy");
        var session=new Session(frozen,event,epoch,plan.chunks().size());
        transactions.executeWithoutResult(status->{
            session.authority();
            var rows=jdbc.queryForList("SELECT * FROM asr_scheduler_state WHERE task_id=? FOR UPDATE",session.task());
            if(rows.isEmpty()) {
                jdbc.update("""
                    INSERT INTO asr_scheduler_state(task_id,user_id,policy_hash,plan_hash,audio_hash,config_identity,execution_epoch,window_size)
                    VALUES(?,?,?,?,?,?,?,?)
                    """,session.task(),session.user(),frozen.hash(),plan.hash(),audioHash,session.policy.configIdentity(),epoch,session.policy.initial());
                for(var chunk:plan.chunks())jdbc.update("""
                    INSERT INTO asr_chunk_checkpoint(task_id,chunk_no,start_millis,end_millis,sources_json) VALUES(?,?,?,?,?)
                    """,session.task(),chunk.index(),chunk.offsetMillis(),chunk.endMillis(),encode(plan.sources().get(chunk.index())));
                session.event(null,null,"OPEN");
            } else {
                var row=rows.getFirst();
                if(!Objects.equals(row.get("policy_hash"),frozen.hash()) || !Objects.equals(row.get("plan_hash"),plan.hash())
                    || !Objects.equals(row.get("audio_hash"),audioHash) || !Objects.equals(row.get("config_identity"),session.policy.configIdentity()))throw changed();
                if(number(row,"execution_epoch")!=epoch) {
                    if(number(row,"execution_epoch")>epoch)throw changed();
                    jdbc.update("UPDATE asr_scheduler_state SET execution_epoch=?,in_flight=0 WHERE task_id=?",epoch,session.task());
                    jdbc.update("UPDATE asr_chunk_checkpoint SET status='NETWORK_OUTCOME_UNKNOWN' WHERE task_id=? AND status='RUNNING'",session.task());
                    session.event(null,null,"RESUME");
                }
            }
        });
        return session;
    }

    public final class Session {
        private final PipelinePolicyService.Frozen frozen;
        private final AsrPipelinePolicy policy;
        private final String event;
        private final long epoch;
        private final int count;
        private Session(PipelinePolicyService.Frozen frozen,String event,long epoch,int count) {
            this.frozen=frozen;this.policy=frozen.policy().asr();this.event=event;this.epoch=epoch;this.count=count;
        }
        public AsrPipelinePolicy policy(){return policy;}
        public Instant deadline(){return frozen.deadline();}
        public String task(){return frozen.execution().taskId();}
        private long user(){return frozen.execution().userId();}
        private void authority(){guard.lock(task(),user(),event,epoch);}
        private Map<String,Object> state(){return jdbc.queryForMap("SELECT *,CURRENT_TIMESTAMP(3) AS now_value FROM asr_scheduler_state WHERE task_id=? FOR UPDATE",task());}
        private Map<String,Object> chunk(int index){return jdbc.queryForMap("SELECT * FROM asr_chunk_checkpoint WHERE task_id=? AND chunk_no=? FOR UPDATE",task(),index);}
        private void event(Integer index,Integer attempt,String category) {
            var row=state();
            jdbc.update("INSERT INTO asr_scheduler_event(task_id,user_id,execution_epoch,chunk_no,attempt_no,category,window_size,in_flight) VALUES(?,?,?,?,?,?,?,?)",
                task(),user(),epoch,index,attempt,category,number(row,"window_size"),number(row,"in_flight"));
        }
        public Optional<SpeechToTextResult> reusable(int index,String audioHash) {
            return transactions.execute(status->{
                authority();var clip=chunk(index);
                if(clip.get("audio_hash")!=null && !audioHash.equals(clip.get("audio_hash")))throw changed();
                if(clip.get("audio_hash")==null)jdbc.update("UPDATE asr_chunk_checkpoint SET audio_hash=? WHERE task_id=? AND chunk_no=?",audioHash,task(),index);
                if("SUCCEEDED".equals(clip.get("status"))) {
                    var result=decode((String)clip.get("result_json"),(String)clip.get("result_hash"));
                    jdbc.update("UPDATE asr_scheduler_state SET checkpoint_hits=checkpoint_hits+1 WHERE task_id=?",task());
                    event(index,null,"CHECKPOINT_HIT");return Optional.of(result.result());
                }
                if(!policy.cacheEnabled())return Optional.empty();
                var rows=jdbc.queryForList("""
                    SELECT c.result_json,c.result_hash FROM asr_result_cache c JOIN analysis_task t ON t.id=c.source_task_id AND t.user_id=c.user_id
                    WHERE c.user_id=? AND c.audio_hash=? AND c.config_identity=? AND c.expires_at>CURRENT_TIMESTAMP(3) AND t.deleted_at IS NULL FOR UPDATE
                    """,user(),audioHash,policy.configIdentity());
                if(rows.isEmpty()){event(index,null,"CACHE_MISS");return Optional.empty();}
                Stored stored;
                try {stored=decode((String)rows.getFirst().get("result_json"),(String)rows.getFirst().get("result_hash"));}
                catch(RuntimeException corrupt) {
                    jdbc.update("DELETE FROM asr_result_cache WHERE user_id=? AND audio_hash=? AND config_identity=?",user(),audioHash,policy.configIdentity());
                    event(index,null,"CACHE_CORRUPT_MISS");return Optional.empty();
                }
                commitResult(index,stored);
                jdbc.update("UPDATE asr_scheduler_state SET cache_hits=cache_hits+1 WHERE task_id=?",task());
                event(index,null,"CACHE_HIT");return Optional.of(stored.result());
            });
        }
        public Permit tryAcquire(int index) {
            return transactions.execute(status->{
                authority();var row=state();var now=instant(row.get("now_value"));
                if(number(row,"in_flight")>=number(row,"window_size") || later(row.get("cooldown_until"),now)
                    || later(row.get("next_dispatch_at"),now))return null;
                var clip=chunk(index);int attempts=(int)number(clip,"attempt_count");
                if(clip.get("audio_hash")==null)throw changed();
                if("SUCCEEDED".equals(clip.get("status")))throw changed();
                if(attempts>=frozen.policy().silence().asrMaxAttempts()
                    || number(row,"physical_calls")>=(long)count*frozen.policy().silence().asrMaxAttempts())
                    throw TranslationFailure.of(TranslationFailure.Reason.CALL_BUDGET_EXHAUSTED);
                jdbc.update("""
                    UPDATE asr_scheduler_state SET in_flight=in_flight+1,peak_in_flight=GREATEST(peak_in_flight,in_flight),
                        physical_calls=physical_calls+1,next_dispatch_at=? WHERE task_id=?
                    """,Timestamp.from(now.plusMillis((1000+policy.requestsPerSecond()-1)/policy.requestsPerSecond())),task());
                jdbc.update("UPDATE asr_chunk_checkpoint SET attempt_count=attempt_count+1,status='RUNNING',last_epoch=? WHERE task_id=? AND chunk_no=?",epoch,task(),index);
                event(index,attempts+1,"DISPATCH");return new Permit(index,attempts+1);
            });
        }
        public void succeeded(Permit permit,SpeechToTextResult result) {
            var stored=Stored.from(result);
            transactions.executeWithoutResult(status->{
                authority();var row=state();owned(permit);
                int streak=(int)number(row,"success_streak")+1,window=(int)number(row,"window_size");
                if(streak>=policy.successStreak()){window=Math.min(policy.maximum(),window+1);streak=0;}
                jdbc.update("UPDATE asr_scheduler_state SET in_flight=in_flight-1,window_size=?,success_streak=? WHERE task_id=?",window,streak,task());
                commitResult(permit.chunk(),stored);event(permit.chunk(),permit.attempt(),"SUCCEEDED");
                if(policy.cacheEnabled())cache(permit.chunk(),stored);
            });
        }
        public void failed(Permit permit,AsrProviderException failure) {
            transactions.executeWithoutResult(status->{
                authority();var row=state();owned(permit);
                int window=(int)number(row,"window_size");boolean limited=failure.statusCode().orElse(0)==429;
                int next=limited?Math.max(1,window/2):window;
                if(limited)jdbc.update("""
                    UPDATE asr_scheduler_state SET in_flight=in_flight-1,window_size=?,success_streak=0,
                        rate_limits=rate_limits+1,decreases=decreases+?,cooldown_until=? WHERE task_id=?
                    """,next,next<window?1:0,Timestamp.from(instant(row.get("now_value")).plusMillis(Math.max(policy.cooldownMillis(),failure.retryAfterMillis()))),task());
                else jdbc.update("UPDATE asr_scheduler_state SET in_flight=in_flight-1,success_streak=0 WHERE task_id=?",task());
                jdbc.update("UPDATE asr_chunk_checkpoint SET status='FAILED' WHERE task_id=? AND chunk_no=?",task(),permit.chunk());
                event(permit.chunk(),permit.attempt(),limited?"RATE_LIMIT":AsrCallFailure.provider(failure).category().name());
            });
        }
        private void owned(Permit permit) {
            var row=chunk(permit.chunk());
            if(!"RUNNING".equals(row.get("status")) || number(row,"last_epoch")!=epoch || number(row,"attempt_count")!=permit.attempt())throw changed();
        }
        private void commitResult(int index,Stored stored) {
            String payload=encode(stored);
            jdbc.update("UPDATE asr_chunk_checkpoint SET status='SUCCEEDED',result_json=?,result_hash=?,last_epoch=? WHERE task_id=? AND chunk_no=?",
                payload,PipelinePolicyService.hash(payload),epoch,task(),index);
        }
        private void cache(int index,Stored stored) {
            // Serialize owner capacity checks; OFF never enters this path or queries cache rows.
            jdbc.queryForList("SELECT id FROM user_account WHERE id=? FOR UPDATE",user());
            jdbc.update("DELETE FROM asr_result_cache WHERE user_id=? AND expires_at<=CURRENT_TIMESTAMP(3)",user());
            int entries=jdbc.queryForObject("SELECT COUNT(*) FROM asr_result_cache WHERE user_id=?",Integer.class,user());
            if(entries>=policy.cacheMaxEntries()){event(index,null,"CACHE_CAPACITY_SKIP");return;}
            String payload=encode(stored);
            jdbc.update("""
                INSERT IGNORE INTO asr_result_cache(user_id,audio_hash,config_identity,source_task_id,result_json,result_hash,expires_at)
                VALUES(?,?,?,?,?,?,DATE_ADD(CURRENT_TIMESTAMP(3),INTERVAL ? SECOND))
                """,user(),chunk(index).get("audio_hash"),policy.configIdentity(),task(),payload,PipelinePolicyService.hash(payload),policy.cacheTtlSeconds());
        }
    }
    private String encode(Object value) {
        try {String payload=json.writeValueAsString(value);if(payload.length()>2_000_000)throw changed();return payload;}
        catch(TranslationFailure safe){throw safe;}catch(Exception ignored){throw changed();}
    }
    private Stored decode(String payload,String hash) {
        if(payload==null)throw changed();
        // MySQL JSON normalizes whitespace/key order; verify canonical typed content, not returned wire formatting.
        try {var stored=json.readValue(payload,Stored.class);
            if(!PipelinePolicyService.hash(encode(stored)).equals(hash))throw changed();
            Stored.from(stored.result());return stored;}
        catch(Exception ignored){throw changed();}
    }
    private static long number(Map<String,Object> row,String key){return ((Number)row.get(key)).longValue();}
    private static Instant instant(Object value){return value instanceof Timestamp timestamp?timestamp.toInstant():((LocalDateTime)value).toInstant(ZoneOffset.UTC);}
    private static boolean later(Object value,Instant now){return value!=null && instant(value).isAfter(now);}
    private static TranslationFailure changed(){return TranslationFailure.of(TranslationFailure.Reason.SOURCE_CHANGED);}
}
