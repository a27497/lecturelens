package com.example.courselingo.systemmodel;

import com.example.courselingo.ai.asr.*;
import com.example.courselingo.media.*;
import com.example.courselingo.mq.AnalysisTaskMessage;
import com.example.courselingo.subtitle.pipeline.PipelinePolicyService;
import com.example.courselingo.task.service.PipelineCheckpointDeletion;
import com.example.courselingo.task.service.AsrExecutionStore;
import java.nio.file.Path;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.junit.jupiter.api.io.TempDir;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

@EnabledIfEnvironmentVariable(named="SYSTEM_MODEL_TEST_JDBC_URL",matches=".+")
class AsrExecutionMySqlTest {
    @TempDir Path directory;
    private record Active(PipelinePolicyService.Frozen frozen,AnalysisTaskMessage message) {}
    private PipelineCheckpointFixture fixture(boolean cache) throws Exception {
        return fixture(cache,false);
    }
    private PipelineCheckpointFixture fixture(boolean cache,boolean merge) throws Exception {
        return new PipelineCheckpointFixture(6,true,p->{p.getAsr().setEnabled(true);p.getAsr().setCacheEnabled(cache);p.getAsr().setMergeEnabled(merge);p.getAsr().setCooldownMillis(1);});
    }
    private SilenceAudioChunkPlanner.Plan plan(int count) {
        var clips=new ArrayList<AudioChunk>();
        for(int i=0;i<count;i++)clips.add(new AudioChunk(i,i*10000L,Path.of("clip-"+i+".wav"),(i+1)*10000L,TranscriptTimingSource.AUDIO_CLIP,null));
        return new SilenceAudioChunkPlanner.Plan(clips,"a".repeat(64),0,4*1024*1024);
    }
    private SpeechToTextResult result(){return new SpeechToTextResult("synthetic","en","course evidence",List.of(new TranscribedSegment(0,0,10000,"course evidence")),Duration.ofMillis(1),10000,Map.of());}
    private AsrExecutionStore store(PipelineCheckpointFixture f){return new AsrExecutionStore(f.db.jdbc,f.guard,f.db.transactions);}
    private AsrExecutionStore.Session session(PipelineCheckpointFixture f,int clips){return store(f).open(f.frozen,f.first.requestId(),1,plan(clips),"c".repeat(64));}
    private AsrExecutionStore.Permit acquire(PipelineCheckpointFixture f,AsrExecutionStore.Session session,int clip) {
        f.db.jdbc.update("UPDATE asr_scheduler_state SET next_dispatch_at=NULL,cooldown_until=NULL WHERE task_id=?",session.task());
        return session.tryAcquire(clip);
    }
    private Active next(PipelineCheckpointFixture f,long owner,String language) {
        String task=f.db.task(owner),snapshot=UUID.randomUUID().toString();
        f.db.jdbc.update("UPDATE analysis_task SET status='CREATED',source_language=? WHERE id=?",language,task);
        f.db.jdbc.update("INSERT INTO system_model_execution_snapshot(id,task_id,user_id,operation_type,operation_id,config_version,resolved_config_json) SELECT ?,?,?,'PIPELINE',?,config_version,resolved_config_json FROM system_model_execution_snapshot WHERE id=?",
            snapshot,task,owner,task,f.snapshot);
        var ref=new SystemModelExecutionRef(snapshot,0,task,owner);f.policies.freeze(ref);
        var message=new AnalysisTaskMessage(task,task,owner,language,"zh-CN","event-"+task,"trace",Instant.now(),2,1L);
        f.db.jdbc.update("UPDATE analysis_task SET status='QUEUED' WHERE id=?",task);f.leases.open(message);
        f.leases.publishSuccess(message,()->f.db.jdbc.update("UPDATE analysis_task SET status='RUNNING' WHERE id=?",task));
        return new Active(f.policies.find(task,owner).orElseThrow(),message);
    }
    private AsrExecutionStore.Session session(PipelineCheckpointFixture f,Active active) {
        return store(f).open(active.frozen(),active.message().requestId(),1,plan(1),"c".repeat(64));
    }

    @Test void taskWindowPacingAndCooldownPersistWithoutResetOnReopen() throws Exception {
        try(var f=fixture(false)) {
            var session=session(f,6);
            session.reusable(0,"d".repeat(64));session.reusable(1,"e".repeat(64));
            var first=session.tryAcquire(0);assertThat(first).isNotNull();
            assertThat(session.tryAcquire(1)).isNull();
            var second=acquire(f,session,1);assertThat(second).isNotNull();
            assertThat(acquire(f,session,2)).isNull();
            session.succeeded(first,result());session.failed(second,new AsrProviderException("limited",true,429,5000));
            var before=f.db.jdbc.queryForMap("SELECT * FROM asr_scheduler_state WHERE task_id=?",f.task);
            assertThat(((Number)before.get("window_size")).intValue()).isEqualTo(1);
            assertThat(((Number)before.get("rate_limits")).intValue()).isEqualTo(1);
            assertThat(((Number)before.get("decreases")).intValue()).isEqualTo(1);
            var reopened=session(f,6);
            assertThat(reopened.tryAcquire(1)).isNull();
            assertThat(reopened.reusable(0,"d".repeat(64))).isPresent();
            assertThat(f.db.jdbc.queryForObject("SELECT COUNT(*) FROM asr_result_cache",Integer.class)).isZero();
        }
    }

    @Test void retryCountsAndWindowSurviveEpochRecoveryAndRejectLateResults() throws Exception {
        try(var f=fixture(false)) {
            var first=session(f,1);first.reusable(0,"d".repeat(64));var permit=first.tryAcquire(0);
            var message=f.expiredAndReopened();
            var resumed=store(f).open(f.frozen,message.requestId(),message.executionEpoch(),plan(1),"c".repeat(64));
            assertThatThrownBy(()->first.succeeded(permit,result())).isInstanceOf(com.example.courselingo.ai.llm.TranslationFailure.class);
            assertThat(resumed.reusable(0,"d".repeat(64))).isEmpty();
            var second=acquire(f,resumed,0);assertThat(second.attempt()).isEqualTo(2);
            resumed.failed(second,new AsrProviderException("failure",true,500));
            var third=acquire(f,resumed,0);assertThat(third.attempt()).isEqualTo(3);
            resumed.failed(third,new AsrProviderException("failure",true,500));
            assertThatThrownBy(()->acquire(f,resumed,0)).hasMessageContaining("CALL_BUDGET_EXHAUSTED");
            assertThat(f.db.jdbc.queryForObject("SELECT physical_calls FROM asr_scheduler_state WHERE task_id=?",Integer.class,f.task)).isEqualTo(3);
        }
    }

    @Test void successfulStreakGrowsToFourAndStopsAtTheFrozenMaximum() throws Exception {
        try(var f=fixture(false)) {
            var session=session(f,6);
            for(int clip=0;clip<6;clip++) {
                session.reusable(clip,Integer.toString(clip).repeat(64));
                session.succeeded(acquire(f,session,clip),result());
            }
            assertThat(f.db.jdbc.queryForObject("SELECT window_size FROM asr_scheduler_state WHERE task_id=?",Integer.class,f.task)).isEqualTo(4);
        }
    }

    @Test void ownerScopedCacheHitsAcrossTasksButChangedLanguageAndForeignOwnersMiss() throws Exception {
        try(var f=fixture(true)) {
            var cold=session(f,1);assertThat(cold.reusable(0,"d".repeat(64))).isEmpty();cold.succeeded(cold.tryAcquire(0),result());
            var hot=session(f,next(f,f.user,"en"));assertThat(hot.reusable(0,"d".repeat(64))).isPresent();
            assertThat(f.db.jdbc.queryForObject("SELECT physical_calls FROM asr_scheduler_state WHERE task_id=?",Integer.class,hot.task())).isZero();
            assertThat(session(f,next(f,f.user,"zh-CN")).reusable(0,"d".repeat(64))).isEmpty();
            assertThat(session(f,next(f,f.db.user(),"en")).reusable(0,"d".repeat(64))).isEmpty();
            f.db.jdbc.update("UPDATE analysis_task SET deleted_at=CURRENT_TIMESTAMP WHERE id=?",f.task);
            assertThat(session(f,next(f,f.user,"en")).reusable(0,"d".repeat(64))).isEmpty();
            new org.springframework.transaction.support.TransactionTemplate(f.db.transactions).executeWithoutResult(s->new PipelineCheckpointDeletion(f.db.jdbc).clearDeleted(f.task,f.user));
            assertThat(f.db.jdbc.queryForObject("SELECT COUNT(*) FROM asr_result_cache",Integer.class)).isZero();
        }
    }

    @Test void corruptedCacheMissesExplicitlyAndOffModeNeverPopulatesCache() throws Exception {
        try(var f=fixture(true)) {
            var cold=session(f,1);cold.reusable(0,"d".repeat(64));cold.succeeded(cold.tryAcquire(0),result());
            f.db.jdbc.update("UPDATE asr_result_cache SET result_hash=?","f".repeat(64));
            var hot=session(f,next(f,f.user,"en"));assertThat(hot.reusable(0,"d".repeat(64))).isEmpty();
            assertThat(f.db.jdbc.queryForObject("SELECT COUNT(*) FROM asr_scheduler_event WHERE task_id=? AND category='CACHE_CORRUPT_MISS'",Integer.class,hot.task())).isEqualTo(1);
        }
    }
    @Test void offModeIgnoresAnExistingValidCacheEntry() throws Exception {
        try(var f=fixture(false)) {
            var cold=session(f,1);cold.reusable(0,"d".repeat(64));cold.succeeded(cold.tryAcquire(0),result());
            f.db.jdbc.update("""
                INSERT INTO asr_result_cache(user_id,audio_hash,config_identity,source_task_id,result_json,result_hash,expires_at)
                SELECT ?,audio_hash,?,task_id,result_json,result_hash,DATE_ADD(CURRENT_TIMESTAMP,INTERVAL 1 HOUR)
                FROM asr_chunk_checkpoint WHERE task_id=? AND chunk_no=0
                """,f.user,f.frozen.policy().asr().configIdentity(),f.task);
            var off=session(f,next(f,f.user,"en"));assertThat(off.reusable(0,"d".repeat(64))).isEmpty();
            assertThat(f.db.jdbc.queryForObject("SELECT cache_hits FROM asr_scheduler_state WHERE task_id=?",Integer.class,off.task())).isZero();
            assertThat(f.db.jdbc.queryForObject("SELECT COUNT(*) FROM asr_result_cache",Integer.class)).isEqualTo(1);
        }
    }
    @Test void productionStepKeepsMergedIntervalsAndRestoresWithoutPhysicalReplay() throws Exception {
        try(var f=fixture(false,true)) {
            var input=java.nio.file.Files.writeString(directory.resolve("source.wav"),"synthetic source audio");
            var planner=mock(SilenceAudioChunkPlanner.class);
            when(planner.plan(eq(input),eq(180000L),any(),any(),anyLong(),any())).thenAnswer(call->{
                Path clips=call.getArgument(2);
                return new SilenceAudioChunkPlanner.Plan(List.of(
                    new AudioChunk(0,0,clips.resolve("first.wav"),90000,TranscriptTimingSource.AUDIO_CLIP,"MERGED_ADJACENT"),
                    new AudioChunk(1,90000,clips.resolve("second.wav"),180000,TranscriptTimingSource.AUDIO_CLIP,"MERGED_ADJACENT")),
                    "a".repeat(64),0,4*1024*1024);
            });
            doAnswer(call->{var clip=(AudioChunk)call.getArgument(1);java.nio.file.Files.createDirectories(clip.audioFile().getParent());
                java.nio.file.Files.writeString(clip.audioFile(),"synthetic bytes "+clip.index());return null;})
                .when(planner).materialize(eq(input),any(),any(),anyLong());
            var task=new com.example.courselingo.task.entity.AnalysisTask();task.setId(f.task);task.setUserId(f.user);task.setStatus("RUNNING");
            var mapper=mock(com.example.courselingo.task.mapper.AnalysisTaskMapper.class);when(mapper.selectByIdAndUserId(f.task,f.user)).thenReturn(task);
            var count=new java.util.concurrent.atomic.AtomicInteger();
            SpeechToTextProvider provider=new SpeechToTextProvider() {
                public String providerName(){return "synthetic";}
                public SpeechToTextResult transcribe(SpeechToTextRequest request){count.incrementAndGet();
                    return new SpeechToTextResult("synthetic","en","source "+request.interval().startMillis(),
                        List.of(new TranscribedSegment(0,0,0,"source "+request.interval().startMillis())),Duration.ZERO,0,Map.of("segmentTimingSource","provider_not_available"));}
            };
            for(int repeat=0;repeat<2;repeat++) {
                var result=com.example.courselingo.task.runner.AsrPipelineTestHarness.runFrozenSilence(provider,f.ref,f.first,input,directory.resolve("workspace"),
                    f.policies,store(f),f.sourceStore,mapper,planner,180000);
                assertThat(result.segments()).hasSize(2);
                assertThat(result.segments().getFirst().endMillis()).isEqualTo(90000);
                assertThat(result.segments().getLast().startMillis()).isEqualTo(90000);
                assertThat(result.segments().getLast().endMillis()).isEqualTo(180000);
                assertThat(result.metadata()).containsEntry("asrCacheEnabled",false);
            }
            assertThat(count).hasValue(2);
            assertThat(f.db.jdbc.queryForObject("SELECT physical_calls FROM asr_scheduler_state WHERE task_id=?",Integer.class,f.task)).isEqualTo(2);
            assertThat(f.db.jdbc.queryForObject("SELECT checkpoint_hits FROM asr_scheduler_state WHERE task_id=?",Integer.class,f.task)).isEqualTo(2);
        }
    }
}
