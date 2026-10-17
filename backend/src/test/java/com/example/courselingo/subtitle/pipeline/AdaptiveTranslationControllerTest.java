package com.example.courselingo.subtitle.pipeline;

import com.example.courselingo.ai.llm.TranslationFailure;
import org.junit.jupiter.api.Test;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import static org.assertj.core.api.Assertions.*;

class AdaptiveTranslationControllerTest {
    @Test void startsLowAddsOneAfterConsecutiveValidatedSuccessAndNeverExceedsMaximum() {
        var events=new ArrayList<AdaptiveTranslationController.Event>();
        try(var controller=new AdaptiveTranslationController(new TranslationAimdPolicy(2048,1,1,2,3,4),"growth",events::add)) {
            assertThat(controller.window()).isEqualTo(1);
            for(int i=0;i<8;i++) {
                try(var permit=controller.acquire(i+1,1,1000)){permit.succeeded();}
                assertThat(controller.window()).isEqualTo(i<2?1:2);
            }
            assertThat(controller.inflight()).isZero();
            assertThat(events.stream().filter(e->e.reason().equals("SUCCESS") && e.oldWindow()==1 && e.window()==2)).hasSize(1);
        }
    }
    @Test void oneCongestionGenerationHalvesOnlyOnceAndDoesNotCancelHealthyRequests() {
        try(var controller=new AdaptiveTranslationController(new TranslationAimdPolicy(2048,1,4,4,3,4),"halve",e->{})) {
            var a=controller.acquire(1,1,1000);var b=controller.acquire(2,1,1000);var c=controller.acquire(3,1,1000);
            a.failed(TranslationFailure.of(TranslationFailure.Reason.RATE_LIMITED));assertThat(controller.window()).isEqualTo(2);
            b.failed(TranslationFailure.of(TranslationFailure.Reason.TIMEOUT));assertThat(controller.window()).isEqualTo(2);
            c.succeeded();assertThat(controller.inflight()).isZero();assertThat(controller.window()).isEqualTo(2);
        }
    }
    @Test void differentTasksShareOneProviderPermitBudget() throws Exception {
        var policy=new TranslationAimdPolicy(2048,1,4,4,3,2);
        try(var a=new AdaptiveTranslationController(policy,"shared",e->{});
            var b=new AdaptiveTranslationController(policy,"shared",e->{});
            var first=a.acquire(1,1,1000);var second=a.acquire(2,1,1000)) {
            var executor=Executors.newSingleThreadExecutor();
            try {
                var pending=executor.submit(()->b.acquire(1,1,2000));
                assertThatThrownBy(()->pending.get(100,TimeUnit.MILLISECONDS)).isInstanceOf(TimeoutException.class);
                first.succeeded();
                try(var available=pending.get(1,TimeUnit.SECONDS)){assertThat(b.inflight()).isEqualTo(1);available.succeeded();}
                second.succeeded();
            } finally {executor.shutdownNow();}
        }
    }
    @Test void observationFailureDoesNotLeakTaskOrGlobalPermits() {
        var fail=new AtomicBoolean(true);
        try(var controller=new AdaptiveTranslationController(new TranslationAimdPolicy(2048,1,1,1,3,1),"observer",e->{
            if(e.reason().equals("REQUEST_STARTED") && fail.getAndSet(false))throw new IllegalStateException("synthetic observer failure");
        })) {
            assertThatThrownBy(()->controller.acquire(1,1,500)).isInstanceOf(IllegalStateException.class);
            try(var next=controller.acquire(1,2,500)){next.succeeded();}
            assertThat(controller.inflight()).isZero();
        }
    }
    @Test void closingControllerWakesTaskWaitersWithoutReusingTheOldWorker() throws Exception {
        var controller=new AdaptiveTranslationController(new TranslationAimdPolicy(2048,1,1,1,3,1),"close",e->{});
        var active=controller.acquire(1,1,1000);var pool=Executors.newSingleThreadExecutor();
        try {
            var queued=pool.submit(()->controller.acquire(2,1,10000));controller.close();
            assertThatThrownBy(()->queued.get(1,TimeUnit.SECONDS)).hasCauseInstanceOf(TranslationFailure.class);
        } finally {active.close();controller.close();pool.shutdownNow();}
        try(var next=new AdaptiveTranslationController(new TranslationAimdPolicy(2048,1,1,1,3,1),"close",e->{});
            var permit=next.acquire(1,1,1000)){permit.succeeded();}
    }
    @Test void serverErrorUsesRetryPolicyWithoutAnExtraMultiplicativeDecrease() {
        try(var controller=new AdaptiveTranslationController(new TranslationAimdPolicy(2048,1,4,4,3,4),"server",e->{});
            var permit=controller.acquire(1,1,1000)) {
            permit.failed(TranslationFailure.of(TranslationFailure.Reason.UPSTREAM_5XX));assertThat(controller.window()).isEqualTo(4);
        }
    }
}
