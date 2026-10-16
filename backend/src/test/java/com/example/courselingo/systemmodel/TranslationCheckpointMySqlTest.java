package com.example.courselingo.systemmodel;

import com.example.courselingo.ai.llm.*;
import com.example.courselingo.subtitle.pipeline.*;
import com.example.courselingo.task.service.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import static org.assertj.core.api.Assertions.*;

@EnabledIfEnvironmentVariable(named="SYSTEM_MODEL_TEST_JDBC_URL",matches=".+")
class TranslationCheckpointMySqlTest {
    @Test void workerLossResumesOnlyUnfinishedBatchesWithoutReadingTheCurrentBinding() throws Exception {
        try(var f=new PipelineCheckpointFixture()) {
            var calls=new HashMap<Integer,Integer>();var original=f.session(f.first);
            var provider=PipelineCheckpointFixture.provider(r->{
                int batch=((Number)r.metadata().get("translationBatchNo")).intValue();calls.merge(batch,1,Integer::sum);
                assertThat(r.execution().configVersion()).isZero();
                if(batch==2)throw new AssertionError("Synthetic process loss after STARTED, no completion callback");
                return PipelineCheckpointFixture.success();
            });
            assertThatThrownBy(()->f.coordinator(f.first,provider,original).run(f.source.stream().map(List::of).toList())).isInstanceOf(TranslationFailure.class);
            var before=f.db.jdbc.queryForMap("SELECT result_hash,attempt_count FROM translation_batch WHERE task_id=? AND batch_no=1",f.task);
            assertThat(f.db.jdbc.queryForObject("SELECT status FROM translation_attempt WHERE task_id=? AND batch_no=2",String.class,f.task)).isEqualTo("STARTED");
            f.db.jdbc.update("INSERT INTO system_model_config_version(version,parent_version,config_json,config_sha256,reason) VALUES(1,0,'{}',SHA2('{}',256),'SYNTHETIC_HEAD_CHANGE')");
            f.db.jdbc.update("UPDATE system_model_config_state SET current_version=1 WHERE id=1");
            var next=f.expiredAndReopened();assertThat(next.epoch()).isEqualTo(2);
            assertThat(new SystemModelExecutionService(f.db.jdbc,null,f.db.transactions).existingPipeline(f.task,f.user)).isEqualTo(f.ref);
            var restored=f.sourceStore.restore(f.task,f.user,next.requestId(),next.epoch()).orElseThrow();
            assertThat(restored.segments()).hasSize(3);assertThat(restored.metadata().get("systemModelSnapshotId")).isEqualTo(f.snapshot);
            var resumedProvider=PipelineCheckpointFixture.provider(r->{
                int batch=((Number)r.metadata().get("translationBatchNo")).intValue();calls.merge(batch,1,Integer::sum);
                assertThat(r.execution().configVersion()).isZero();return PipelineCheckpointFixture.success();
            });
            var second=f.session(next);var result=f.coordinator(next,resumedProvider,second).run(f.source.stream().map(List::of).toList());
            assertThat(result.translations()).hasSize(3);assertThat(calls.get(1)).isEqualTo(1);assertThat(calls.get(2)).isEqualTo(2);assertThat(calls.get(3)).isEqualTo(1);
            assertThat(f.db.jdbc.queryForMap("SELECT result_hash,attempt_count FROM translation_batch WHERE task_id=? AND batch_no=1",f.task)).isEqualTo(before);
            assertThat(f.db.jdbc.queryForObject("SELECT COUNT(*) FROM translation_attempt WHERE task_id=? AND batch_no=1",Integer.class,f.task)).isEqualTo(1);
            assertThat(f.db.jdbc.queryForObject("SELECT status FROM translation_attempt WHERE task_id=? AND batch_no=2 AND attempt_no=1",String.class,f.task)).isEqualTo("UNKNOWN_OUTCOME");
            second.publish(()->{});assertThat(f.db.jdbc.queryForObject("SELECT status FROM translation_plan WHERE task_id=?",String.class,f.task)).isEqualTo("PUBLISHED");
            f.leases.close(f.first);assertThat(f.db.jdbc.queryForObject("SELECT event_id FROM task_execution WHERE task_id=?",String.class,f.task)).isEqualTo(next.requestId());
            assertThat(f.leases.publishFailure(f.first,()->f.db.jdbc.update("UPDATE analysis_task SET status='FAILED' WHERE id=?",f.task))).isFalse();
            assertThat(f.db.jdbc.queryForObject("SELECT status FROM analysis_task WHERE id=?",String.class,f.task)).isEqualTo("RUNNING");
        }
    }
    @Test void persistedSplitTreeDoesNotRepeatTheTruncatedParentOrCompletedChild() throws Exception {
        try(var f=new PipelineCheckpointFixture(1)) {
            var calls=new HashMap<Integer,Integer>();var first=f.session(f.first);
            var provider=PipelineCheckpointFixture.provider(r->{int batch=((Number)r.metadata().get("translationBatchNo")).intValue();calls.merge(batch,1,Integer::sum);
                if(batch==1)throw new TranslationFailure(TranslationFailure.Reason.TRUNCATED,200,new LlmUsage(10,20,30),"length",0);
                if(batch==3)throw new AssertionError("Synthetic child crash");return PipelineCheckpointFixture.success();});
            assertThatThrownBy(()->f.coordinator(f.first,provider,first).run(List.of(f.source))).isInstanceOf(TranslationFailure.class);
            assertThat(f.db.jdbc.queryForObject("SELECT status FROM translation_batch WHERE task_id=? AND batch_no=1",String.class,f.task)).isEqualTo("SPLIT");
            assertThat(f.db.jdbc.queryForObject("SELECT status FROM translation_batch WHERE task_id=? AND batch_no=2",String.class,f.task)).isEqualTo("SUCCEEDED");
            var next=f.expiredAndReopened();var provider2=PipelineCheckpointFixture.provider(r->{calls.merge(((Number)r.metadata().get("translationBatchNo")).intValue(),1,Integer::sum);return PipelineCheckpointFixture.success();});
            var result=f.coordinator(next,provider2,f.session(next)).run(List.of(f.source));
            assertThat(result.translations()).hasSize(1);assertThat(calls.get(1)).isEqualTo(1);assertThat(calls.get(2)).isEqualTo(1);assertThat(calls.get(3)).isEqualTo(2);
            assertThat(f.db.jdbc.queryForObject("SELECT COUNT(*) FROM translation_batch WHERE task_id=? AND status<>'SUCCEEDED'",Integer.class,f.task)).isZero();
        }
    }
    @Test void allCommittedBatchesCanRepublishWithoutAnyModelCall() throws Exception {
        try(var f=new PipelineCheckpointFixture(2)) {
            var first=f.session(f.first);f.coordinator(f.first,PipelineCheckpointFixture.provider(r->PipelineCheckpointFixture.success()),first)
                .run(f.source.stream().map(List::of).toList());
            var next=f.expiredAndReopened();var count=new AtomicInteger();var resumed=f.session(next);
            var result=f.coordinator(next,PipelineCheckpointFixture.provider(r->{count.incrementAndGet();throw new AssertionError("Completed batch replayed");}),resumed)
                .run(f.source.stream().map(List::of).toList());
            resumed.publish(()->{});assertThat(count.get()).isZero();assertThat(result.translations()).hasSize(2);
            assertThat(result.responses()).allSatisfy(r->assertThat(r.metadata().get("checkpointReused")).isEqualTo(true));
        }
    }
    @Test void changedSourceOrCanceledTaskRejectsCachedOutputWithoutCallingTheModel() throws Exception {
        try(var f=new PipelineCheckpointFixture(1)) {
            var session=f.session(f.first);f.coordinator(f.first,PipelineCheckpointFixture.provider(r->PipelineCheckpointFixture.success()),session).run(List.of(f.source));
            f.db.jdbc.update("UPDATE subtitle_segment SET text='changed' WHERE task_id=?",f.task);
            assertThatThrownBy(()->session.publish(()->{throw new AssertionError("Source fence bypassed");})).isInstanceOf(TranslationFailure.class);
            f.db.jdbc.update("UPDATE analysis_task SET status='CANCELED' WHERE id=?",f.task);
            assertThatThrownBy(()->f.session(f.first)).isInstanceOf(TranslationFailure.class);
        }
    }
}
