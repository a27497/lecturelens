package com.example.courselingo.systemmodel;

import com.example.courselingo.ai.llm.*;
import com.example.courselingo.subtitle.pipeline.*;
import com.example.courselingo.task.usage.*;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import static org.assertj.core.api.Assertions.*;

@EnabledIfEnvironmentVariable(named="SYSTEM_MODEL_TEST_JDBC_URL",matches=".+")
class PipelineUsageLedgerMySqlTest {
    private static final byte[] SUMMARY="{\"model\":\"deepseek-flash\",\"max_tokens\":512,\"messages\":[]}".getBytes(StandardCharsets.UTF_8);
    private static final String USAGE="\"usage\":{\"prompt_tokens\":100,\"completion_tokens\":20,\"total_tokens\":120,\"completion_tokens_details\":{\"reasoning_tokens\":10},\"prompt_cache_hit_tokens\":40,\"prompt_cache_miss_tokens\":60}";
    @Test void ordinaryQaOnACompletedV2CourseDoesNotRequireAPipelineWorkerLease() throws Exception {
        try(var f=new PipelineCheckpointFixture(1)) {
            String operation=UUID.randomUUID().toString();
            f.db.jdbc.update("""
                INSERT INTO system_model_execution_snapshot(id,task_id,user_id,operation_type,operation_id,config_version,resolved_config_json)
                SELECT ?,task_id,user_id,'COURSE_QA',?,config_version,resolved_config_json FROM system_model_execution_snapshot WHERE id=?
                """,operation,operation,f.snapshot);
            f.db.jdbc.update("UPDATE analysis_task SET status='SUCCEEDED' WHERE id=?",f.task);f.leases.close(f.first);
            var ref=new SystemModelExecutionRef(operation,0,f.task,f.user);
            var ledger=new PipelineUsageLedger(f.db.jdbc,f.policies,f.guard,f.db.transactions);
            var calls=new AtomicInteger();
            try(var ignored=ModelCallScope.open(new ModelCallScope.Context(ref,"COURSE_QA","synthetic",null,"browser-request",null,null,null))) {
                ObservedModelCall.execute(ledger,URI.create("https://example.invalid/chat"),Map.of(),SUMMARY,true,()->{calls.incrementAndGet();return response(200,"{}");});
            }
            assertThat(calls.get()).isEqualTo(1);
            assertThat(f.db.jdbc.queryForObject("SELECT COUNT(*) FROM model_call_attempt WHERE task_id=?",Integer.class,f.task)).isZero();
        }
    }
    @Test void incompleteAccountingBlocksFinalSuccessAndKnownLateFactsCanResolveIt() throws Exception {
        try(var f=new PipelineCheckpointFixture(1)) {
            var ledger=new PipelineUsageLedger(f.db.jdbc,f.policies,f.guard,f.db.transactions);
            var id=ledger.begin(new ModelCallScope.Context(f.ref,"ASR_TRANSCRIPTION","qwen-audio-3.1-asr-flash",null,f.first.requestId(),0L,30000L,"SILENCE_SPLIT"),
                new ModelCallObserver.RequestSummary("https://dashscope.aliyuncs.com/api/v1/test",PipelinePolicyService.hash("body"),4,"{}"));
            assertThatThrownBy(()->f.leases.publishSuccess(f.first,()->{throw new AssertionError("Unaccounted result published");}))
                .isInstanceOf(TranslationFailure.class).hasMessageContaining("ACCOUNTING_INCOMPLETE");
            ledger.complete(id,new ModelCallObserver.Completion(200,new LlmUsage(100,20,120),null,null,1,null,10,false));
            assertThatCode(()->f.leases.publishSuccess(f.first,()->{})).doesNotThrowAnyException();
        }
    }
    @Test void failureSummaryCanRecoverUsageThatALegacyErrorWrapperDidNotReturn() throws Exception {
        try(var f=new PipelineCheckpointFixture(1)) {
            var session=f.session(f.first);session.initialize(List.of(f.source),f.codec());session.claim(1);var intent=session.begin(1,100,512);
            var ledger=new PipelineUsageLedger(f.db.jdbc,f.policies,f.guard,f.db.transactions);
            try(var ignored=ModelCallScope.open(new ModelCallScope.Context(f.ref,"TRANSLATION_FULL_TEXT","deepseek-flash",intent.id(),f.first.requestId(),null,null,null))) {
                ObservedModelCall.execute(ledger,URI.create("https://api.deepseek.com/chat/completions"),Map.of(),SUMMARY,true,()->response(429,"{"+USAGE+"}"));
            }
            session.failed(1,intent,TranslationFailure.of(TranslationFailure.Reason.RATE_LIMITED),1);
            var row=f.db.jdbc.queryForMap("SELECT prompt_tokens,reasoning_tokens,usage_status,accounted_tokens FROM translation_attempt WHERE id=?",intent.id());
            assertThat(((Number)row.get("prompt_tokens")).intValue()).isEqualTo(100);assertThat(((Number)row.get("reasoning_tokens")).intValue()).isEqualTo(10);
            assertThat(row.get("usage_status")).isEqualTo("PROVIDER_REPORTED");assertThat(((Number)row.get("accounted_tokens")).intValue()).isEqualTo(120);
        }
    }
    @Test void truncatedParentAndBothChildrenAreAllBilledButSummaryIsNotAddedAgain() throws Exception {
        try(var f=new PipelineCheckpointFixture(1)) {
            var ledger=new PipelineUsageLedger(f.db.jdbc,f.policies,f.guard,f.db.transactions);var count=new AtomicInteger();
            var provider=PipelineCheckpointFixture.provider(request->{
                try(var ignored=ModelCallScope.open(new ModelCallScope.Context(f.ref,"TRANSLATION_FULL_TEXT","deepseek-flash",
                        (String)request.metadata().get("translationAttemptId"),f.first.requestId(),null,null,null))) {
                    boolean truncated=count.incrementAndGet()==1;
                    var response=ObservedModelCall.execute(ledger,URI.create("https://api.deepseek.com/chat/completions"),Map.of(),SUMMARY,true,
                        ()->response(200,"{\"choices\":[{\"finish_reason\":\""+(truncated?"length":"stop")+"\",\"message\":{\"content\":\"{}\"}}],"+USAGE+"}"));
                    return TranslationResponseDecoder.decode(response,"deepseek-flash",Map.of());
                }
            });
            var session=f.session(f.first);var result=f.coordinator(f.first,provider,session).run(List.of(f.source));session.publish(()->{});
            assertThat(result.translations()).hasSize(1);assertThat(count.get()).isEqualTo(3);
            assertThat(f.db.jdbc.queryForObject("SELECT COUNT(*) FROM model_call_attempt WHERE task_id=?",Integer.class,f.task)).isEqualTo(3);
            assertThat(f.db.jdbc.queryForObject("SELECT COUNT(*) FROM model_call_attempt WHERE task_id=? AND error_category='TRUNCATED'",Integer.class,f.task)).isEqualTo(1);
            assertThat(f.db.jdbc.queryForObject("SELECT SUM(reasoning_tokens) FROM translation_attempt WHERE task_id=?",Long.class,f.task)).isEqualTo(30);
            assertThat(f.db.jdbc.queryForObject("SELECT SUM(prompt_tokens) FROM model_call_attempt WHERE task_id=?",Long.class,f.task)).isEqualTo(300);
            assertThat(ledger.totals(f.task,f.user,"TRANSLATION_FULL_TEXT")).isEqualTo(new LlmUsage(300,60,360));
            assertThat(f.db.jdbc.queryForObject("SELECT COUNT(*) FROM model_call_attempt WHERE task_id=? AND cost_lower IS NOT NULL AND currency='USD'",Integer.class,f.task)).isEqualTo(3);
            assertThatThrownBy(()->f.db.jdbc.update("UPDATE model_price_card SET currency='CNY'")).isInstanceOf(org.springframework.dao.DataAccessException.class);
        }
    }
    @Test void asrSilenceClipsAndRetriesKeepActualTokensAndAreCountedExactlyOnce() throws Exception {
        try(var f=new PipelineCheckpointFixture(1,true)) {
            var ledger=new PipelineUsageLedger(f.db.jdbc,f.policies,f.guard,f.db.transactions);
            for(int i=0;i<3;i++)try(var ignored=ModelCallScope.open(new ModelCallScope.Context(f.ref,"ASR_TRANSCRIPTION","qwen-audio-3.1-asr-flash",null,
                    f.first.requestId(),i<2?0L:30000L,i<2?30000L:60000L,"SILENCE_SPLIT"))) {
                int status=i==0?429:200;
                ObservedModelCall.execute(ledger,URI.create("https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"),Map.of(),SUMMARY,true,
                    ()->response(status,"{\"usage\":{\"input_tokens\":100,\"output_tokens\":20,\"total_tokens\":120},\"output\":{\"text\":\"synthetic\"}}"));
            }
            var counts=f.db.jdbc.queryForMap("SELECT COUNT(*) calls,COUNT(DISTINCT audio_start_millis) clips,SUM(prompt_tokens) inputs,SUM(cost_lower) cost FROM model_call_attempt WHERE task_id=? AND silence_segmentation=1",f.task);
            assertThat(((Number)counts.get("calls")).intValue()).isEqualTo(3);assertThat(((Number)counts.get("clips")).intValue()).isEqualTo(2);
            assertThat(((Number)counts.get("inputs")).intValue()).isEqualTo(300);
            assertThat((java.math.BigDecimal)counts.get("cost")).isEqualByComparingTo("0.000402");
            assertThat(f.db.jdbc.queryForObject("SELECT COUNT(*) FROM model_call_attempt WHERE task_id=? AND currency='CNY'",Integer.class,f.task)).isEqualTo(3);
        }
    }
    @Test void material400StoresOnlySafeSummaryAndPrivateRedactedErrorAndUnknownUsageRemainsNull() throws Exception {
        try(var f=new PipelineCheckpointFixture(1)) {
            var ledger=new PipelineUsageLedger(f.db.jdbc,f.policies,f.guard,f.db.transactions);
            String synthetic="sk-synthetic-private-test";
            try(var ignored=ModelCallScope.open(new ModelCallScope.Context(f.ref,"LEARNING_PACKAGE","synthetic-local",null,f.first.requestId(),null,null,null))) {
                ObservedModelCall.execute(ledger,URI.create("http://127.0.0.1:10000/v1/chat/completions"),Map.of("Authorization","Bearer "+synthetic),SUMMARY,true,
                    ()->response(400,"{\"error\":{\"message\":\"unsupported response_format, credential "+synthetic+"\"}}"));
            }
            var row=f.db.jdbc.queryForMap("SELECT * FROM model_call_attempt WHERE task_id=?",f.task);
            assertThat(row.get("private_error_excerpt").toString()).contains("unsupported response_format","[redacted]").doesNotContain(synthetic);
            assertThat(row.get("request_summary").toString()).doesNotContain("messages",synthetic);
            assertThat(row.get("prompt_tokens")).isNull();assertThat(row.get("cost_lower")).isNull();assertThat(row.get("usage_status")).isEqualTo("PROVIDER_USAGE_MISSING");
            assertThat(ledger.totals(f.task,f.user,"LEARNING_PACKAGE")).isEqualTo(new LlmUsage(null,null,null));
        }
    }
    @Test void interruptedUnknownCallCanFinishUsageLateButCannotRecreateAfterDeletion() throws Exception {
        try(var f=new PipelineCheckpointFixture(1)) {
            var ledger=new PipelineUsageLedger(f.db.jdbc,f.policies,f.guard,f.db.transactions);
            var context=new ModelCallScope.Context(f.ref,"ASR_TRANSCRIPTION","qwen-audio-3.1-asr-flash",null,f.first.requestId(),0L,30000L,"SILENCE_SPLIT");
            var summary=new ModelCallObserver.RequestSummary("https://dashscope.aliyuncs.com/api/v1/test",PipelinePolicyService.hash("body"),4,"{}");
            String id=ledger.begin(context,summary);f.expiredAndReopened();
            assertThat(f.db.jdbc.queryForObject("SELECT usage_status FROM model_call_attempt WHERE id=?",String.class,id)).isEqualTo("PROCESS_INTERRUPTED");
            assertThat(f.db.jdbc.queryForObject("SELECT prompt_tokens FROM model_call_attempt WHERE id=?",Integer.class,id)).isNull();
            ledger.complete(id,new ModelCallObserver.Completion(200,new LlmUsage(100,20,120),null,null,1,null,10,false));
            assertThat(f.db.jdbc.queryForObject("SELECT prompt_tokens FROM model_call_attempt WHERE id=?",Integer.class,id)).isEqualTo(100);
            f.db.jdbc.update("UPDATE analysis_task SET deleted_at=CURRENT_TIMESTAMP WHERE id=?",f.task);
            ledger.complete(id,new ModelCallObserver.Completion(200,new LlmUsage(900,900,1800),null,null,1,null,10,false));
            assertThat(f.db.jdbc.queryForObject("SELECT prompt_tokens FROM model_call_attempt WHERE id=?",Integer.class,id)).isEqualTo(100);
        }
    }
    private static OpenAiCompatibleClientResponse response(int status,String body){return new OpenAiCompatibleClientResponse(status,body,Map.of(),Duration.ofMillis(1));}
}
