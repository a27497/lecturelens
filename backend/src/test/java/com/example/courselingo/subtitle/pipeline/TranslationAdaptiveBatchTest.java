package com.example.courselingo.subtitle.pipeline;

import com.example.courselingo.ai.llm.*;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import java.time.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;
import static org.assertj.core.api.Assertions.*;

class TranslationAdaptiveBatchTest {
    static TranslationPolicy policy(int input) {
        var p=TranslationBatchCoordinatorTest.policy(6,256,200000);
        return new TranslationPolicy("translation-v2.3",p.tokenCounter(),p.requestTimeoutMillis(),p.totalTimeoutMillis(),
            p.outputMin(),p.outputMax(),p.outputRatio(),p.outputSlack(),p.safetyFactor(),p.contextReserve(),p.contextLimit(),p.maxDepth(),
            p.maxAttempts(),p.maxCalls(),p.tokenBudget(),1,1000,null,new TranslationAimdPolicy(input,1,1,4,3,4));
    }
    static List<SubtitleSegment> sources(int count,int length) {
        return IntStream.range(0,count).mapToObj(i->{var s=TranslationBatchCoordinatorTest.source(i+" "+"a".repeat(length));s.setSegmentIndex(i);return s;}).toList();
    }
    @Test void planningUsesFullPromptTokenBudgetAndPreservesAllInputPositions() {
        var source=sources(12,60);var p=policy(300);var codec=TranslationBatchCoordinatorTest.codec();
        var plan=TranslationBatchPlanner.plan(source,p,codec);
        assertThat(plan.size()).isBetween(2,11);
        assertThat(plan.stream().flatMap(List::stream).toList()).containsExactlyElementsOf(source);
        assertThat(plan).allSatisfy(batch->assertThat(TranslationTokenBudget.estimate(codec.planningRequest(batch),p)).isLessThanOrEqualTo(300));
    }
    @Test @Timeout(10) void realParallelDispatchFollowsWindowGrowthAndKeepsSourceOrder() {
        var p=policy(256);var source=sources(20,120);var events=Collections.synchronizedList(new ArrayList<AdaptiveTranslationController.Event>());
        var current=new AtomicInteger();var max=new AtomicInteger();var calls=new AtomicInteger();
        var provider=TranslationBatchCoordinatorTest.provider(r->{
            assertThat((Integer)r.metadata().get("estimatedInputTokens")).isLessThanOrEqualTo(256);
            assertThat(r.maxAttempts()).isEqualTo(1);
            int n=current.incrementAndGet();max.accumulateAndGet(n,Math::max);calls.incrementAndGet();
            try {Thread.sleep(10);return TranslationBatchCoordinatorTest.result(r.messages().getLast().content());}
            catch(InterruptedException ignored){Thread.currentThread().interrupt();throw TranslationFailure.of(TranslationFailure.Reason.CANCELED);}
            finally {current.decrementAndGet();}
        });
        var coordinator=new TranslationBatchCoordinator(TranslationBatchCoordinatorTest.frozen(p),provider,TranslationBatchCoordinatorTest.codec(),null,
            Clock.fixed(TranslationBatchCoordinatorTest.NOW,ZoneOffset.UTC),millis->{}).observe("parallel",events::add);
        var result=coordinator.run(source.stream().map(List::of).toList());
        assertThat(result.translations()).hasSize(20);assertThat(calls.get()).isEqualTo(20);assertThat(max.get()).isBetween(2,4);
        assertThat(result.translations().stream().map(t->t.source().getSegmentIndex()).toList()).containsExactlyElementsOf(IntStream.range(0,20).boxed().toList());
        assertThat(events.stream().filter(e->e.reason().equals("REQUEST_STARTED"))).allSatisfy(e->assertThat(e.inflight()).isLessThanOrEqualTo(e.window()));
        assertThat(events.stream().mapToInt(AdaptiveTranslationController.Event::window).max().orElseThrow()).isEqualTo(4);
    }
    @Test void oversizedAtomicInputSplitsBeforeItCanExceedInputBudgetOnTheWire() {
        var p=policy(256);var seen=new ArrayList<LlmRequest>();
        var provider=TranslationBatchCoordinatorTest.provider(r->{seen.add(r);return TranslationBatchCoordinatorTest.result("ok");});
        var coordinator=new TranslationBatchCoordinator(TranslationBatchCoordinatorTest.frozen(p),provider,TranslationBatchCoordinatorTest.codec(),null,
            Clock.fixed(TranslationBatchCoordinatorTest.NOW,ZoneOffset.UTC),millis->{}).observe("split-input",e->{});
        var original=TranslationBatchCoordinatorTest.source("A long source sentence. ".repeat(12));
        var result=coordinator.run(List.of(List.of(original)));
        assertThat(seen.size()).isGreaterThan(1);assertThat(result.translations()).singleElement().satisfies(t->assertThat(t.source()).isSameAs(original));
        assertThat(seen).allSatisfy(r->assertThat((Integer)r.metadata().get("estimatedInputTokens")).isLessThanOrEqualTo(256));
    }
}
