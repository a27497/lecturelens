package com.example.courselingo.subtitle.pipeline;

import com.example.courselingo.ai.llm.*;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.systemmodel.SystemModelExecutionRef;
import org.junit.jupiter.api.Test;
import java.time.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import static org.assertj.core.api.Assertions.*;
import static com.example.courselingo.ai.llm.TranslationFailure.Reason.*;

class TranslationBatchCoordinatorTest {
    static final Instant NOW=Instant.parse("2026-10-16T08:00:00Z");
    static TranslationPolicy policy(int depth,int calls,long tokens) {
        return new TranslationPolicy("translation-v2.1","UTF8_CONSERVATIVE_V1",120000,900000,
            512,8192,2,128,1.10,512,32768,depth,3,calls,tokens,1,1000);
    }
    static PipelinePolicyService.Frozen frozen(TranslationPolicy policy) {
        return new PipelinePolicyService.Frozen(policy,"test-policy",NOW.plusSeconds(1800),new SystemModelExecutionRef("s",10,"task",9));
    }
    static SubtitleSegment source(String text) {
        var s=new SubtitleSegment();s.setSegmentIndex(7);s.setText(text);s.setTaskId("task");s.setUserId(9L);
        s.setStartMillis(12000L);s.setEndMillis(42000L);s.setLanguage("en");return s;
    }
    static LlmResult result(String content) { return new LlmResult("mock","mock",content,"stop",new LlmUsage(20,30,50),Duration.ofMillis(5),Map.of()); }
    static TranslationBatchCoordinator.Codec codec() {
        return new TranslationBatchCoordinator.Codec() {
            public LlmRequest request(List<SubtitleSegment> batch,String correction,Duration timeout) {
                return new LlmRequest("req","task",List.of(new LlmMessage(LlmRole.SYSTEM,"Return JSON"),
                    new LlmMessage(LlmRole.USER,batch.stream().map(SubtitleSegment::getText).reduce("",(a,b)->a+b))),timeout,0d,8192,1,Map.of(),LlmResponseFormat.JSON_OBJECT);
            }
            public List<TranslationBatchCoordinator.Translated> validate(List<SubtitleSegment> batch,LlmResult response) {
                return batch.stream().map(s->new TranslationBatchCoordinator.Translated(s,response.content())).toList();
            }
        };
    }
    static LlmProvider provider(java.util.function.Function<LlmRequest,LlmResult> fn) {
        return new LlmProvider() { public String providerName(){return "mock";} public LlmResult generate(LlmRequest r){return fn.apply(r);} };
    }
    static TranslationBatchCoordinator coordinator(TranslationPolicy p,LlmProvider provider) {
        return new TranslationBatchCoordinator(frozen(p),provider,codec(),null,Clock.fixed(NOW,ZoneOffset.UTC),millis->{});
    }
    @Test void truncatedSingleSegmentSplitsImmediatelyAndKeepsItsOriginalInterval() {
        var calls=new ArrayList<LlmRequest>();
        var p=provider(r->{calls.add(r);if(calls.size()==1) throw new TranslationFailure(TRUNCATED,200,new LlmUsage(10,5,15),"length",0);return result("中文译文。");});
        var input=source("First sentence includes unicode 😀 and examples. Second sentence explains a different point.");
        var output=coordinator(policy(6,256,200000),p).run(List.of(List.of(input)));
        assertThat(calls).hasSize(3);
        assertThat(output.translations()).singleElement().satisfies(t->{
            assertThat(t.source()).isSameAs(input);assertThat(t.source().getStartMillis()).isEqualTo(12000L);
            assertThat(t.text()).isEqualTo("中文译文。 中文译文。");
        });
        assertThat(calls).allSatisfy(r->{assertThat(r.maxAttempts()).isEqualTo(1);assertThat(TranslationResponseDecoder.enabled(r)).isTrue();});
        assertThat(calls.get(0).messages()).isNotEqualTo(calls.get(1).messages());
    }
    @Test void emptyOutputRetriesOnlyOnceBeforeSplitting() {
        var calls=new AtomicInteger();
        var p=provider(r->{if(calls.incrementAndGet()<=2) throw TranslationFailure.of(EMPTY_OUTPUT);return result("翻译完成。");});
        var out=coordinator(policy(6,256,200000),p).run(List.of(List.of(source("First part. Second part."))));
        assertThat(calls.get()).isEqualTo(4);assertThat(out.translations()).hasSize(1);
    }
    @Test void authenticationDoesNotRetryOrSplit() {
        var calls=new AtomicInteger();
        var p=provider(r->{calls.incrementAndGet();throw new TranslationFailure(AUTHENTICATION,401,null,null,0);});
        assertThatThrownBy(()->coordinator(policy(6,256,200000),p).run(List.of(List.of(source("A long enough source")))))
            .isInstanceOfSatisfying(TranslationFailure.class,e->assertThat(e.reason()).isEqualTo(AUTHENTICATION));
        assertThat(calls.get()).isEqualTo(1);
    }
    @Test void allRetryReasonsShareTheSameLeafAttemptLimit() {
        var calls=new AtomicInteger();
        var p=provider(r->{throw new TranslationFailure(calls.incrementAndGet()==1?TIMEOUT:RATE_LIMITED,429,null,null,0);});
        assertThatThrownBy(()->coordinator(policy(6,256,200000),p).run(List.of(List.of(source("Hello")))))
            .isInstanceOfSatisfying(TranslationFailure.class,e->assertThat(e.reason()).isEqualTo(RATE_LIMITED));
        assertThat(calls.get()).isEqualTo(3);
    }
    @Test void retryAfterAboveBoundFailsWithoutSleepingOrChangingProvider() {
        var sleeps=new AtomicInteger();
        var p=provider(r->{throw new TranslationFailure(RATE_LIMITED,429,null,null,60000);});
        var coordinator=new TranslationBatchCoordinator(frozen(policy(6,256,200000)),p,codec(),null,
            Clock.fixed(NOW,ZoneOffset.UTC),millis->sleeps.incrementAndGet());
        assertThatThrownBy(()->coordinator.run(List.of(List.of(source("Hello"))))).isInstanceOf(TranslationFailure.class);
        assertThat(sleeps.get()).isZero();
    }
    @Test void totalPhysicalCallBudgetAlsoBoundsRecursiveSplits() {
        var calls=new AtomicInteger();
        var p=provider(r->{calls.incrementAndGet();throw TranslationFailure.of(TRUNCATED);});
        assertThatThrownBy(()->coordinator(policy(6,2,200000),p).run(List.of(List.of(source("abcdefghijklmnopqrstuvwxyz")))))
            .isInstanceOfSatisfying(TranslationFailure.class,e->assertThat(e.reason()).isEqualTo(CALL_BUDGET_EXHAUSTED));
        assertThat(calls.get()).isEqualTo(2);
    }
    @Test void splitDepthIsBoundedWithoutAcceptingTruncatedOutput() {
        var calls=new AtomicInteger();
        var p=provider(r->{calls.incrementAndGet();throw TranslationFailure.of(TRUNCATED);});
        assertThatThrownBy(()->coordinator(policy(0,256,200000),p).run(List.of(List.of(source("First. Second.")))))
            .isInstanceOfSatisfying(TranslationFailure.class,e->assertThat(e.reason()).isEqualTo(SPLIT_DEPTH_EXHAUSTED));
        assertThat(calls.get()).isEqualTo(1);
    }
    @Test void unknownUsageKeepsItsReservationAcrossNetworkRetries() {
        var calls=new AtomicInteger();
        var p=provider(r->{calls.incrementAndGet();throw TranslationFailure.of(NETWORK);});
        assertThatThrownBy(()->coordinator(policy(6,256,850),p).run(List.of(List.of(source("Hello")))))
            .isInstanceOfSatisfying(TranslationFailure.class,e->assertThat(e.reason()).isEqualTo(TOKEN_BUDGET_EXHAUSTED));
        assertThat(calls.get()).isEqualTo(1);
    }
    @Test void expiredTaskIsRejectedBeforeTheFirstCall() {
        var count=new AtomicInteger();
        var c=new TranslationBatchCoordinator(new PipelinePolicyService.Frozen(policy(6,256,200000),"p",NOW.minusSeconds(1),frozen(policy(6,256,200000)).execution()),
            provider(r->{count.incrementAndGet();return result("ok");}),codec(),null,Clock.fixed(NOW,ZoneOffset.UTC),millis->{});
        assertThatThrownBy(()->c.run(List.of(List.of(source("Hello"))))).isInstanceOfSatisfying(TranslationFailure.class,e->assertThat(e.reason()).isEqualTo(DEADLINE_EXCEEDED));
        assertThat(count.get()).isZero();
    }
    @Test void dynamicOutputIsBoundedByTheFrozenRouteCapAndInputSize() {
        var requests=new ArrayList<LlmRequest>();
        var c=new TranslationBatchCoordinator(frozen(policy(6,256,200000)),provider(r->{requests.add(r);return result("ok");}),codec(),1500,
            Clock.fixed(NOW,ZoneOffset.UTC),millis->{});
        c.run(List.of(List.of(source("short")),List.of(source("some longer words ".repeat(40)))));
        assertThat(requests.get(0).maxTokens()).isBetween(512,1499);
        assertThat(requests.get(1).maxTokens()).isEqualTo(1500);
        assertThat(requests).allSatisfy(r->assertThat(r.metadata().get("translationTokenCounter")).isEqualTo("UTF8_CONSERVATIVE_V1"));
    }
    @Test void invalidPolicyCannotSilentlyClampToAValidValue() {
        var properties=new PipelineTranslationProperties();properties.setMaxDepth(7);
        assertThatThrownBy(()->properties.freeze(Duration.ofSeconds(120),Duration.ofMinutes(15),1,1000))
            .isInstanceOf(IllegalArgumentException.class);
    }
    @Test void elapsedProviderTimeCannotResetTheWholeTranslationDeadline() {
        var now=new java.util.concurrent.atomic.AtomicReference<>(NOW);
        var clock=new Clock() {
            public ZoneId getZone(){return ZoneOffset.UTC;}
            public Clock withZone(ZoneId zone){return this;}
            public Instant instant(){return now.get();}
        };
        var calls=new AtomicInteger();
        var c=new TranslationBatchCoordinator(frozen(policy(6,256,200000)),provider(r->{
            calls.incrementAndGet();now.set(NOW.plusSeconds(901));throw TranslationFailure.of(TIMEOUT);
        }),codec(),null,clock,millis->{throw new AssertionError("Deadline already expired");});
        assertThatThrownBy(()->c.run(List.of(List.of(source("Hello"))))).isInstanceOf(TranslationFailure.class);
        assertThat(calls.get()).isEqualTo(1);
    }
}
