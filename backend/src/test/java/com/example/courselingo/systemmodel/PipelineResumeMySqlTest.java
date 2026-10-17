package com.example.courselingo.systemmodel;

import com.example.courselingo.ai.llm.*;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.subtitle.pipeline.*;
import com.example.courselingo.task.service.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import java.util.*;
import java.util.concurrent.*;
import static org.assertj.core.api.Assertions.*;

@EnabledIfEnvironmentVariable(named="SYSTEM_MODEL_TEST_JDBC_URL",matches=".+")
class PipelineResumeMySqlTest {
    @Test void explicitResumeIsOwnedEpochCheckedAndQueuesOnlyOneEventUnderConcurrency() throws Exception {
        try(var f=new PipelineCheckpointFixture(1)) {
            f.db.jdbc.update("UPDATE analysis_task SET status='FAILED' WHERE id=?",f.task);f.leases.close(f.first);
            assertThatThrownBy(()->f.resumes.resume(f.task,f.db.user(),1)).isInstanceOf(BusinessException.class)
                .extracting("errorCode").isEqualTo(ErrorCode.TASK_NOT_FOUND);
            assertThatThrownBy(()->f.resumes.resume(f.task,f.user,2)).isInstanceOf(BusinessException.class)
                .extracting("errorCode").isEqualTo(ErrorCode.TASK_RESUME_CONFLICT);
            var start=new CountDownLatch(1);
            try(var pool=Executors.newFixedThreadPool(2)) {
                Callable<String> work=()->{start.await();try {f.resumes.resume(f.task,f.user,1);return "QUEUED";}
                    catch(BusinessException failure){return failure.errorCode().name();}};
                var a=pool.submit(work);var b=pool.submit(work);start.countDown();
                assertThat(List.of(a.get(20,TimeUnit.SECONDS),b.get(20,TimeUnit.SECONDS)))
                    .containsExactlyInAnyOrder("QUEUED","TASK_RESUME_CONFLICT");
            }
            assertThat(f.db.jdbc.queryForObject("SELECT COUNT(*) FROM task_outbox WHERE task_id=? AND event_type='ANALYSIS_RETRY'",Integer.class,f.task)).isEqualTo(1);
            assertThat(f.db.jdbc.queryForObject("SELECT execution_epoch FROM task_execution WHERE task_id=?",Long.class,f.task)).isEqualTo(2);
            assertThatThrownBy(()->f.leases.publishQueued(f.first,()->{throw new AssertionError("Old MQ event admitted");})).isInstanceOf(BusinessException.class);
        }
    }
    @Test void staleWorkerCanRecordPhysicalUsageButCannotPublishOrOverwriteTheNewWorker() throws Exception {
        try(var f=new PipelineCheckpointFixture(1)) {
            var old=f.session(f.first);old.initialize(List.of(f.source),f.codec());old.claim(1);var attempt=old.begin(1,100,512);
            var ticket=f.fence.begin(f.task,f.user,"TRANSLATION");
            var next=f.expiredAndReopened();var resumed=f.session(next);
            f.coordinator(next,PipelineCheckpointFixture.provider(r->PipelineCheckpointFixture.success()),resumed).run(List.of(f.source));
            var hash=f.db.jdbc.queryForObject("SELECT result_hash FROM translation_batch WHERE task_id=?",String.class,f.task);
            var output=f.source.stream().map(s->new TranslationBatchCoordinator.Translated(s,"过期译文")).toList();
            assertThatThrownBy(()->old.succeeded(1,attempt,output,PipelineCheckpointFixture.success(),3)).isInstanceOf(TranslationFailure.class);
            assertThat(f.db.jdbc.queryForObject("SELECT result_hash FROM translation_batch WHERE task_id=?",String.class,f.task)).isEqualTo(hash);
            assertThat(f.db.jdbc.queryForObject("SELECT status FROM translation_attempt WHERE id=?",String.class,attempt.id())).isEqualTo("STALE_FINISHED");
            assertThat(f.db.jdbc.queryForObject("SELECT total_tokens FROM translation_attempt WHERE id=?",Integer.class,attempt.id())).isEqualTo(50);
            assertThatThrownBy(()->f.fence.commit(ticket,()->{throw new AssertionError("Old generation published");})).isInstanceOf(BusinessException.class);
            assertThatThrownBy(()->f.leases.open(next)).isInstanceOf(BusinessException.class);
        }
    }
    @Test void completedPublicationRollsBackAtomicallyAndSameEpochCannotClaimTwice() throws Exception {
        try(var f=new PipelineCheckpointFixture(1)) {
            var a=f.session(f.first);a.initialize(List.of(f.source),f.codec());a.claim(1);
            var b=f.session(f.first);b.initialize(List.of(f.source),f.codec());
            assertThatThrownBy(()->b.claim(1)).isInstanceOf(TranslationFailure.class);
            f.coordinator(f.first,PipelineCheckpointFixture.provider(r->PipelineCheckpointFixture.success()),a).run(List.of(f.source));
            assertThatThrownBy(()->a.publish(()->{
                f.db.jdbc.update("UPDATE analysis_task SET error_message='uncommitted marker' WHERE id=?",f.task);
                throw new IllegalStateException("Synthetic publish rollback");
            })).isInstanceOf(TranslationFailure.class).extracting("reason").isEqualTo(TranslationFailure.Reason.ACCOUNTING_INCOMPLETE);
            assertThat(f.db.jdbc.queryForObject("SELECT error_message FROM analysis_task WHERE id=?",String.class,f.task)).isNull();
            assertThat(f.db.jdbc.queryForObject("SELECT status FROM translation_plan WHERE task_id=?",String.class,f.task)).isEqualTo("RUNNING");
        }
    }
    @Test void unknownAttemptReservationAndLeafAttemptLimitSurviveRestart() throws Exception {
        try(var f=new PipelineCheckpointFixture(1)) {
            var a=f.session(f.first);a.initialize(List.of(f.source),f.codec());a.claim(1);
            for(int i=0;i<3;i++) {
                var attempt=a.begin(1,100,512);
                a.failed(1,attempt,TranslationFailure.of(TranslationFailure.Reason.TIMEOUT),10);
            }
            assertThat(f.db.jdbc.queryForObject("SELECT physical_calls FROM translation_plan WHERE task_id=?",Integer.class,f.task)).isEqualTo(3);
            assertThat(f.db.jdbc.queryForObject("SELECT accounted_tokens FROM translation_plan WHERE task_id=?",Long.class,f.task)).isEqualTo(1836);
            f.db.jdbc.update("UPDATE analysis_task SET status='FAILED' WHERE id=?",f.task);f.leases.close(f.first);
            assertThatThrownBy(()->f.resumes.resume(f.task,f.user,1)).isInstanceOf(BusinessException.class)
                .extracting("errorCode").isEqualTo(ErrorCode.TASK_RESUME_CONFLICT);
            assertThat(f.db.jdbc.queryForObject("SELECT COUNT(*) FROM task_outbox WHERE task_id=?",Integer.class,f.task)).isZero();
        }
    }
    @Test void cancellationAndDeletionNeverResumeOrPurgeAnotherOwnersCheckpoints() throws Exception {
        try(var f=new PipelineCheckpointFixture(1)) {
            f.db.jdbc.update("UPDATE analysis_task SET status='CANCELED' WHERE id=?",f.task);f.leases.close(f.first);
            assertThatThrownBy(()->f.resumes.resume(f.task,f.user,1)).isInstanceOf(BusinessException.class);
            var deletion=new PipelineCheckpointDeletion(f.db.jdbc);
            deletion.clearDeleted(f.task,f.user);
            assertThat(f.db.jdbc.queryForObject("SELECT COUNT(*) FROM pipeline_policy_snapshot WHERE task_id=?",Integer.class,f.task)).isEqualTo(1);
            f.db.jdbc.update("UPDATE analysis_task SET deleted_at=CURRENT_TIMESTAMP WHERE id=?",f.task);
            deletion.clearDeleted(f.task,f.db.user());
            assertThat(f.db.jdbc.queryForObject("SELECT COUNT(*) FROM pipeline_policy_snapshot WHERE task_id=?",Integer.class,f.task)).isEqualTo(1);
            new org.springframework.transaction.support.TransactionTemplate(f.db.transactions).executeWithoutResult(s->deletion.clearDeleted(f.task,f.user));
            assertThat(f.db.jdbc.queryForObject("SELECT COUNT(*) FROM pipeline_policy_snapshot WHERE task_id=?",Integer.class,f.task)).isZero();
            assertThat(f.db.jdbc.queryForObject("SELECT COUNT(*) FROM pipeline_step_checkpoint WHERE task_id=?",Integer.class,f.task)).isZero();
            assertThatThrownBy(()->f.resumes.resume(f.task,f.user,1)).isInstanceOf(BusinessException.class)
                .extracting("errorCode").isEqualTo(ErrorCode.TASK_NOT_FOUND);
        }
    }
}
