package com.example.courselingo.task.service;

import com.example.courselingo.ai.asr.*;
import com.example.courselingo.ai.llm.TranslationFailure;
import com.example.courselingo.subtitle.pipeline.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import java.time.Duration;
import java.util.*;

@Service
public class PipelineSourceCheckpointStore {
    public record SourceMetadata(String provider,String language,long providerMillis,long audioMillis,Map<String,Object> metadata) {}
    private final JdbcTemplate jdbc;
    private final PipelinePolicyService policies;
    private final PipelineExecutionGuard guard;
    private final TransactionTemplate transaction;
    private final ObjectMapper json=new ObjectMapper().enable(com.fasterxml.jackson.databind.SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);
    private final GenerationFence fence;
    public PipelineSourceCheckpointStore(JdbcTemplate jdbc,PipelinePolicyService policies,PipelineExecutionGuard guard,GenerationFence fence,PlatformTransactionManager manager) {
        this.jdbc=jdbc;this.policies=policies;this.guard=guard;this.fence=fence;transaction=new TransactionTemplate(manager);
    }
    public boolean enabled(String task,long user) {return policies.find(task,user).map(p->p.policy().recovery()!=null).orElse(false);}
    public void checkWriter(String task,long user,String event) {if(enabled(task,user))guard.lock(task,user,event,null);}
    public void checkActive(String task,long user,String event,long epoch) {
        transaction.executeWithoutResult(status->guard.lock(task,user,event,epoch));
    }

    /** Source rows, paragraph mapping and this marker commit in the source writer's transaction. */
    public void record(String task,long user,String event,SpeechToTextResult result) {
        if(!enabled(task,user))return;
        var identity=guard.lock(task,user,event,null);
        String source=TranscriptParagraphService.fingerprint(result.segments());
        var safeMetadata=new LinkedHashMap<String,Object>();
        for(String key:List.of("systemModelSnapshotId","systemModelConfigVersion","systemModelSource","segmentationMode","silencePlanHash",
            "asrPhysicalAttempts","silenceClipCount","detectedSilenceMillis"))if(result.metadata().containsKey(key))safeMetadata.put(key,result.metadata().get(key));
        String payload=encode(new SourceMetadata(result.provider(),result.language(),result.duration().toMillis(),result.audioDurationMillis(),safeMetadata));
        jdbc.update("""
            INSERT INTO pipeline_step_checkpoint(task_id,step_name,user_id,source_fingerprint,result_hash,payload_json,execution_epoch)
            VALUES(?,'PERSIST_SUBTITLES',?,?,?,?,?)
            """,task,user,source,PipelinePolicyService.hash(payload),payload,identity.epoch());
    }
    public Optional<SpeechToTextResult> restore(String task,long user,String event,long epoch) {
        if(!enabled(task,user))return Optional.empty();
        return transaction.execute(status->{
            guard.lock(task,user,event,epoch);
            var rows=jdbc.queryForList("SELECT * FROM pipeline_step_checkpoint WHERE task_id=? AND user_id=? AND step_name='PERSIST_SUBTITLES'",task,user);
            if(rows.isEmpty())return Optional.empty();
            try {
                var row=rows.getFirst();var metadata=json.readValue((String)row.get("payload_json"),SourceMetadata.class);
                if(!PipelinePolicyService.hash(encode(metadata)).equals(row.get("result_hash")))throw changed();
                var source=source(task,user);
                if(!TranscriptParagraphService.fingerprint(source).equals(row.get("source_fingerprint")))throw changed();
                return Optional.of(new SpeechToTextResult(metadata.provider(),metadata.language(),source.stream().map(TranscribedSegment::text)
                    .collect(java.util.stream.Collectors.joining("\n")),source,Duration.ofMillis(metadata.providerMillis()),metadata.audioMillis(),metadata.metadata()));
            } catch(TranslationFailure safe){throw safe;}
            catch(Exception ignored){throw changed();}
        });
    }
    public List<TranscribedSegment> source(String task,long user) {
        return jdbc.query("""
            SELECT segment_index,start_millis,end_millis,text,timing_source,timing_reason FROM subtitle_segment
            WHERE task_id=? AND user_id=? ORDER BY segment_index
            """,(r,n)->new TranscribedSegment(r.getInt(1),r.getLong(2),r.getLong(3),r.getString(4),
            TranscriptTimingSource.valueOf(r.getString(5)),r.getString(6)),task,user);
    }
    public record Frame(long id,int index,long time,String objectKey,long size) {}
    private List<Frame> frames(String task,long user) {
        return jdbc.query("SELECT id,frame_index,timestamp_millis,object_key,size_bytes FROM video_keyframe WHERE task_id=? AND user_id=? ORDER BY frame_index",
            (r,n)->new Frame(r.getLong(1),r.getInt(2),r.getLong(3),r.getString(4),r.getLong(5)),task,user);
    }
    public List<String> clearCapture(PipelineExecutionGuard.Identity identity) {
        return transaction.execute(status->{
            guard.lock(identity.taskId(),identity.userId(),identity.eventId(),identity.epoch());
            fence.sourceChanging(identity.taskId(),identity.userId());
            var objects=frames(identity.taskId(),identity.userId()).stream().map(Frame::objectKey).toList();
            jdbc.update("DELETE FROM video_keyframe_analysis WHERE task_id=? AND user_id=?",identity.taskId(),identity.userId());
            jdbc.update("DELETE FROM video_keyframe_ocr WHERE task_id=? AND user_id=?",identity.taskId(),identity.userId());
            jdbc.update("DELETE FROM video_keyframe WHERE task_id=? AND user_id=?",identity.taskId(),identity.userId());
            jdbc.update("DELETE FROM pipeline_step_checkpoint WHERE task_id=? AND user_id=? AND step_name='EXTRACT_KEYFRAMES'",identity.taskId(),identity.userId());
            return objects;
        });
    }
    public void recordCapture(PipelineExecutionGuard.Identity identity) {
        transaction.executeWithoutResult(status->{
            guard.lock(identity.taskId(),identity.userId(),identity.eventId(),identity.epoch());
            var data=frames(identity.taskId(),identity.userId());
            if(data.isEmpty())throw changed();
            String signature=PipelinePolicyService.hash(encode(data));
            jdbc.update("""
                INSERT INTO pipeline_step_checkpoint(task_id,step_name,user_id,source_fingerprint,result_hash,payload_json,execution_epoch)
                VALUES(?,'EXTRACT_KEYFRAMES',?,?,?,'{}',?)
                """,identity.taskId(),identity.userId(),signature,signature,identity.epoch());
        });
    }
    public boolean captureReady(String task,long user,String event,long epoch) {
        return Boolean.TRUE.equals(transaction.execute(status->{
            guard.lock(task,user,event,epoch);
            var rows=jdbc.queryForList("SELECT result_hash FROM pipeline_step_checkpoint WHERE task_id=? AND user_id=? AND step_name='EXTRACT_KEYFRAMES'",task,user);
            if(rows.isEmpty())return false;
            var data=frames(task,user);
            if(data.isEmpty() || !PipelinePolicyService.hash(encode(data)).equals(rows.getFirst().get("result_hash")))throw changed();
            return true;
        }));
    }
    private String encode(Object value){try{return json.writeValueAsString(value);}catch(Exception ignored){throw changed();}}
    private static TranslationFailure changed(){return TranslationFailure.of(TranslationFailure.Reason.SOURCE_CHANGED);}
}
