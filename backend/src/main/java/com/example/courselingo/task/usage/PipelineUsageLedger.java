package com.example.courselingo.task.usage;

import com.example.courselingo.ai.llm.*;
import com.example.courselingo.subtitle.pipeline.*;
import com.example.courselingo.task.service.PipelineExecutionGuard;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import java.sql.Timestamp;
import java.util.*;

/** Canonical physical-call cost ledger; stage summaries and V26 diagnostics are never added to its totals. */
@Service
public class PipelineUsageLedger implements ModelCallObserver {
    private final JdbcTemplate jdbc;
    private final PipelinePolicyService policies;
    private final PipelineExecutionGuard guard;
    private final TransactionTemplate transaction;
    private final ObjectMapper json=new ObjectMapper();
    public PipelineUsageLedger(JdbcTemplate jdbc,PipelinePolicyService policies,PipelineExecutionGuard guard,PlatformTransactionManager manager) {
        this.jdbc=jdbc;this.policies=policies;this.guard=guard;transaction=new TransactionTemplate(manager);
    }
    @Override public String begin(ModelCallScope.Context context,RequestSummary summary) {
        if(context==null || context.execution()==null)return null;
        var ref=context.execution();var frozen=policies.find(ref.taskId(),ref.userId());
        if(frozen.isEmpty() || frozen.get().policy().priceSet()==null)return null;
        if(!frozen.get().execution().equals(ref)) {
            var operations=jdbc.queryForList("SELECT operation_type FROM system_model_execution_snapshot WHERE id=? AND task_id=? AND user_id=? AND config_version=?",
                String.class,ref.snapshotId(),ref.taskId(),ref.userId(),ref.configVersion());
            if(operations.size()==1 && !"PIPELINE".equals(operations.getFirst()))return null;
            throw TranslationFailure.of(TranslationFailure.Reason.SNAPSHOT_INVALID);
        }
        return transaction.execute(s->{
            var identity=guard.lock(ref.taskId(),ref.userId(),context.executionEvent(),null);
            try {
                var snapshots=jdbc.queryForList("SELECT resolved_config_json FROM system_model_execution_snapshot WHERE id=? AND task_id=? AND user_id=? AND config_version=?",
                    ref.snapshotId(),ref.taskId(),ref.userId(),ref.configVersion());
                if(snapshots.size()!=1)throw new IllegalStateException();
                var route=json.readTree((String)snapshots.getFirst().get("resolved_config_json")).path("routes").path(context.feature());
                String model=route.path("model").asText("");String source=route.path("source").asText("");
                if(model.isBlank() || !Set.of("ENV","DATABASE").contains(source))throw new IllegalStateException();
                String attempt=context.translationAttemptId();
                if("TRANSLATION_FULL_TEXT".equals(context.feature())) {
                    if(attempt==null || jdbc.queryForList("SELECT id FROM translation_attempt WHERE id=? AND task_id=? AND config_version=? AND execution_epoch=? AND status='STARTED'",attempt,ref.taskId(),ref.configVersion(),identity.epoch()).isEmpty())throw new IllegalStateException();
                }
                var card=ModelPriceCatalog.select(summary.address(),model);
                if(card!=null) {
                    jdbc.update("""
                        INSERT IGNORE INTO model_price_card(id,provider_model,currency,source_url,checked_at,rate_json,card_sha256)
                        VALUES(?,?,?,?,?,?,?)
                        """,card.id(),card.model(),card.currency(),card.source(),card.checkedAt(),card.rates(),PipelinePolicyService.hash(card.rates()));
                    if(!PipelinePolicyService.hash(card.rates()).equals(jdbc.queryForObject("SELECT card_sha256 FROM model_price_card WHERE id=?",String.class,card.id())))throw new IllegalStateException();
                }
                String id=UUID.randomUUID().toString();
                jdbc.update("""
                    INSERT INTO model_call_attempt(id,task_id,user_id,snapshot_id,config_version,execution_epoch,execution_event,feature,model,route_source,
                    translation_attempt_id,request_address,request_body_hash,request_body_bytes,request_summary,audio_start_millis,audio_end_millis,timing_source,silence_segmentation,price_card_id,silence_plan_hash)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,id,ref.taskId(),ref.userId(),ref.snapshotId(),ref.configVersion(),identity.epoch(),identity.eventId(),context.feature(),model,source,
                    attempt,summary.address(),summary.bodyHash(),summary.bodyBytes(),summary.optionsJson(),context.audioStartMillis(),context.audioEndMillis(),
                    context.timingSource(),frozen.get().policy().silence()!=null,card==null?null:card.id(),context.audioPlanHash());
                return id;
            }catch(TranslationFailure safe){throw safe;}
            catch(Exception ignored){throw TranslationFailure.of(TranslationFailure.Reason.ACCOUNTING_INCOMPLETE);}
        });
    }
    @Override public void complete(String id,Completion completion) {
        if(id==null)return;
        transaction.executeWithoutResult(s->{
            var initial=jdbc.queryForList("SELECT task_id,user_id FROM model_call_attempt WHERE id=?",id);
            if(initial.isEmpty())return;
            var owner=initial.getFirst();
            if(jdbc.queryForList("SELECT id FROM analysis_task WHERE id=? AND user_id=? AND deleted_at IS NULL FOR UPDATE",owner.get("task_id"),owner.get("user_id")).isEmpty())return;
            var rows=jdbc.queryForList("SELECT * FROM model_call_attempt WHERE id=? FOR UPDATE",id);
            if(rows.isEmpty() || rows.getFirst().get("completed_at")!=null)return;
            var row=rows.getFirst();var usage=completion.usage();
            String usageStatus=usageStatus(usage,completion.httpStatus());
            ModelPriceCatalog.Card card=Objects.equals(row.get("price_card_id"),ModelPriceCatalog.DEEPSEEK.id())?ModelPriceCatalog.DEEPSEEK:
                Objects.equals(row.get("price_card_id"),ModelPriceCatalog.BAILIAN.id())?ModelPriceCatalog.BAILIAN:null;
            var now=jdbc.queryForObject("SELECT CURRENT_TIMESTAMP(3)",Timestamp.class).toInstant();
            var created=row.get("created_at");
            var start=created instanceof Timestamp timestamp?timestamp.toInstant():((java.time.LocalDateTime)created).toInstant(java.time.ZoneOffset.UTC);
            var cost=ModelPriceCatalog.cost(card,usage,start,now);
            jdbc.update("""
                UPDATE model_call_attempt SET status='FINISHED',http_status=?,prompt_tokens=?,completion_tokens=?,total_tokens=?,reasoning_tokens=?,
                cache_hit_tokens=?,cache_miss_tokens=?,finish_reason=?,error_category=?,duration_millis=?,usage_status=?,price_tier=?,currency=?,cost_lower=?,cost_upper=?,
                private_error_excerpt=?,response_chars=?,response_truncated=?,response_model_sha256=?,provider_fingerprint_sha256=?,completed_at=CURRENT_TIMESTAMP(3) WHERE id=?
                """,completion.httpStatus(),usage==null?null:usage.promptTokens(),usage==null?null:usage.completionTokens(),usage==null?null:usage.totalTokens(),
                usage==null?null:usage.reasoningTokens(),usage==null?null:usage.cacheHitTokens(),usage==null?null:usage.cacheMissTokens(),completion.finishReason(),
                completion.errorCategory(),completion.durationMillis(),usageStatus,cost.tier(),cost.currency(),cost.lower(),cost.upper(),completion.privateErrorExcerpt(),
                completion.responseChars(),completion.truncated(),completion.responseModelHash(),completion.providerFingerprintHash(),id);
        });
    }
    public static String usageStatus(LlmUsage usage,Integer status) {
        if(usage!=null && usage.promptTokens()!=null && usage.completionTokens()!=null)return "PROVIDER_REPORTED";
        if(usage!=null && (usage.promptTokens()!=null || usage.completionTokens()!=null || usage.totalTokens()!=null
            || usage.reasoningTokens()!=null || usage.cacheHitTokens()!=null || usage.cacheMissTokens()!=null))return "PROVIDER_PARTIAL";
        return status==null?"NETWORK_OUTCOME_UNKNOWN":"PROVIDER_USAGE_MISSING";
    }
    public LlmUsage totals(String task,long user,String feature) {
        var rows=jdbc.queryForList("""
            SELECT COUNT(*) AS calls,COUNT(prompt_tokens) AS p,COUNT(completion_tokens) AS c,COUNT(total_tokens) AS t,
            SUM(prompt_tokens) AS prompt,SUM(completion_tokens) AS completion,SUM(total_tokens) AS total
            FROM model_call_attempt WHERE task_id=? AND user_id=? AND feature=?
            """,task,user,feature);
        var row=rows.getFirst();long calls=((Number)row.get("calls")).longValue();if(calls==0)return null;
        return new LlmUsage(sum(row,"p","prompt",calls),sum(row,"c","completion",calls),sum(row,"t","total",calls));
    }
    private static Integer sum(Map<String,Object> row,String count,String value,long expected) {
        if(((Number)row.get(count)).longValue()!=expected || row.get(value)==null)return null;
        long n=((Number)row.get(value)).longValue();return n>Integer.MAX_VALUE?null:(int)n;
    }
    @Override public void validation(String id,String category,String check) {
        if(id==null)return;
        String safe=Set.of("OUTPUT_INVALID","AUTHENTICATION","MODEL_NOT_FOUND","RATE_LIMIT","SERVER_ERROR","INVALID_REQUEST","TIMEOUT","NETWORK","CANCELLED").contains(category)?category:"UNKNOWN";
        transaction.executeWithoutResult(s->{
            var rows=jdbc.queryForList("SELECT task_id,user_id FROM model_call_attempt WHERE id=?",id);
            if(rows.isEmpty())return;var row=rows.getFirst();
            if(jdbc.queryForList("SELECT id FROM analysis_task WHERE id=? AND user_id=? AND deleted_at IS NULL FOR UPDATE",row.get("task_id"),row.get("user_id")).isEmpty())return;
            jdbc.update("UPDATE model_call_attempt SET error_category=? WHERE id=?",safe,id);
        });
    }
}
