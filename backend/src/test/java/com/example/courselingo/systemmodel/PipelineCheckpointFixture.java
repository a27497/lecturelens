package com.example.courselingo.systemmodel;

import com.example.courselingo.ai.asr.*;
import com.example.courselingo.ai.llm.*;
import com.example.courselingo.mq.*;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.subtitle.pipeline.*;
import com.example.courselingo.task.service.*;
import com.example.courselingo.vision.keyframe.VideoKeyframeEvidenceLifecycleService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.transaction.support.TransactionTemplate;
import java.time.*;
import java.util.*;
import static org.mockito.Mockito.*;

final class PipelineCheckpointFixture implements AutoCloseable {
    final SystemModelMySqlFixture db=new SystemModelMySqlFixture();
    final long user=db.user();final String task=db.task(user),snapshot=UUID.randomUUID().toString();
    final SystemModelExecutionRef ref=new SystemModelExecutionRef(snapshot,0,task,user);
    final ObjectMapper json=new ObjectMapper().findAndRegisterModules();
    final PipelinePolicyService policies;
    final PipelinePolicyService.Frozen frozen;
    final GenerationFence fence=new GenerationFence(db.jdbc,db.transactions);
    final PipelineExecutionGuard guard=new PipelineExecutionGuard(db.jdbc);
    final PipelineSourceCheckpointStore sourceStore;
    final TranslationCheckpointStore batches;
    final RocketMqAnalysisTaskMessageProducer transport=mock(RocketMqAnalysisTaskMessageProducer.class);
    final VideoKeyframeEvidenceLifecycleService cleanup=mock(VideoKeyframeEvidenceLifecycleService.class);
    final DurableTaskOutbox outbox=new DurableTaskOutbox(db.jdbc,json,transport,cleanup,db.transactions);
    final PipelineResumeService resumes;
    final TaskExecutionLease leases=new TaskExecutionLease(db.jdbc,db.transactions);
    final AnalysisTaskMessage first;
    final List<SubtitleSegment> source;

    PipelineCheckpointFixture() throws Exception {this(3);}
    PipelineCheckpointFixture(int count) throws Exception {this(count,false);}
    PipelineCheckpointFixture(int count,boolean silence) throws Exception {
        db.jdbc.update("UPDATE analysis_task SET status='CREATED',source_language='en' WHERE id=?",task);
        db.jdbc.update("""
            INSERT INTO system_model_execution_snapshot(id,task_id,user_id,operation_type,operation_id,config_version,resolved_config_json)
            VALUES(?,?,?,'PIPELINE',?,0,?)
            """,snapshot,task,user,task,"{\"routes\":{\"TRANSLATION_FULL_TEXT\":{\"model\":\"deepseek-flash\",\"source\":\"DATABASE\"},\"ASR_TRANSCRIPTION\":{\"model\":\"qwen-audio-3.1-asr-flash\",\"source\":\"ENV\"},\"LEARNING_PACKAGE\":{\"model\":\"synthetic-local\",\"source\":\"ENV\"}}}");
        var settings=new PipelineTranslationProperties();settings.setEnabled(true);settings.getSilence().setEnabled(silence);
        settings.getAdaptive().setMaximum(1);settings.getAdaptive().setInputTokenBudget(256);
        policies=new PipelinePolicyService(db.jdbc,settings,new com.example.courselingo.subtitle.service.SubtitleTranslationProperties());
        policies.freeze(ref);frozen=policies.find(task,user).orElseThrow();
        sourceStore=new PipelineSourceCheckpointStore(db.jdbc,policies,guard,fence,db.transactions);
        batches=new TranslationCheckpointStore(db.jdbc,db.transactions,guard,sourceStore);
        resumes=new PipelineResumeService(db.jdbc,policies,sourceStore,outbox,db.transactions);leases.configureRecovery(resumes);
        outbox.configurePipelineDeletion(new PipelineCheckpointDeletion(db.jdbc));
        first=new AnalysisTaskMessage(task,task,user,"en","zh-CN","initial-event","trace",Instant.now(),2,1L);
        db.jdbc.update("UPDATE analysis_task SET status='QUEUED' WHERE id=?",task);leases.open(first);
        leases.publishSuccess(first,()->db.jdbc.update("UPDATE analysis_task SET status='RUNNING' WHERE id=?",task));
        var segments=new ArrayList<SubtitleSegment>();var transcript=new ArrayList<TranscribedSegment>();
        for(int i=0;i<count;i++) {
            var segment=new SubtitleSegment();segment.setTaskId(task);segment.setUserId(user);segment.setSegmentIndex(i);
            segment.setStartMillis(i*10000L);segment.setEndMillis((i+1)*10000L);segment.setLanguage("en");segment.setText("Unit "+i+" "+"words ".repeat(20));
            segments.add(segment);transcript.add(new TranscribedSegment(i,segment.getStartMillis(),segment.getEndMillis(),segment.getText()));
            db.jdbc.update("INSERT INTO subtitle_segment(task_id,user_id,segment_index,start_millis,end_millis,text,language) VALUES(?,?,?,?,?,?,'en')",
                task,user,i,segment.getStartMillis(),segment.getEndMillis(),segment.getText());
        }
        source=List.copyOf(segments);
        var asr=new SpeechToTextResult("mock","en","synthetic",transcript,Duration.ofMillis(3),count*10000L,
            Map.of("systemModelConfigVersion",0L,"systemModelSnapshotId",snapshot,"segmentationMode","MOCK"));
        new TransactionTemplate(db.transactions).executeWithoutResult(s->sourceStore.record(task,user,first.requestId(),asr));
    }
    TranslationBatchCoordinator.Codec codec() {
        return new TranslationBatchCoordinator.Codec() {
            public LlmRequest request(List<SubtitleSegment> batch,String correction,Duration timeout) {
                return new LlmRequest("r",task,List.of(new LlmMessage(LlmRole.USER,batch.stream().map(SubtitleSegment::getText)
                    .collect(java.util.stream.Collectors.joining("\n")))),timeout,0d,8192,1,Map.of(),LlmResponseFormat.JSON_OBJECT,ref);
            }
            public List<TranslationBatchCoordinator.Translated> validate(List<SubtitleSegment> batch,LlmResult response) {
                return batch.stream().map(s->new TranslationBatchCoordinator.Translated(s,"译文 "+s.getSegmentIndex())).toList();
            }
        };
    }
    TranslationBatchCoordinator coordinator(AnalysisTaskMessage message,LlmProvider provider,TranslationCheckpointStore.Session session) {
        return new TranslationBatchCoordinator(frozen,provider,codec(),null).checkpoint(session).observe("test-"+task,e->{});
    }
    TranslationCheckpointStore.Session session(AnalysisTaskMessage message) {
        return batches.open(frozen,message.requestId(),source,"zh-CN","frozen-deepseek","mock");
    }
    AnalysisTaskMessage expiredAndReopened() throws Exception {
        db.jdbc.update("UPDATE task_execution SET lease_until=DATE_SUB(CURRENT_TIMESTAMP,INTERVAL 1 SECOND) WHERE task_id=?",task);
        leases.recoverExpired();outbox.dispatch();
        var captor=org.mockito.ArgumentCaptor.forClass(AnalysisTaskMessage.class);
        verify(transport).send(eq(AnalysisTaskMessageTag.ANALYSIS_RETRY),captor.capture());
        var next=captor.getValue();
        leases.publishQueued(next,()->db.jdbc.update("UPDATE analysis_task SET status='QUEUED' WHERE id=?",task));
        leases.open(next);leases.publishSuccess(next,()->db.jdbc.update("UPDATE analysis_task SET status='RUNNING' WHERE id=?",task));
        return next;
    }
    static LlmProvider provider(java.util.function.Function<LlmRequest,LlmResult> fn) {
        return new LlmProvider(){public String providerName(){return "mock";}public LlmResult generate(LlmRequest request){return fn.apply(request);}};
    }
    static LlmResult success(){return new LlmResult("mock","frozen-deepseek","{\"segments\":[]}","stop",new LlmUsage(20,30,50),Duration.ofMillis(1),Map.of());}
    @Override public void close() throws Exception {db.close();}
}
