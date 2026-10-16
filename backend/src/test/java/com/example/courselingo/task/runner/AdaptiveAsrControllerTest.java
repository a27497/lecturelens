package com.example.courselingo.task.runner;

import com.example.courselingo.ai.asr.*;
import com.example.courselingo.ai.llm.TranslationFailure;
import com.example.courselingo.task.service.AsrExecutionStore;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

class AdaptiveAsrControllerTest {
    @TempDir Path directory;
    private AsrPipelinePolicy policy(int maximum){return new AsrPipelinePolicy(1,maximum,3,10,1,false,60000,90000,120000,false,86400,256,"a".repeat(64),"b".repeat(64));}
    private SpeechToTextResult result(){return new SpeechToTextResult("fake","en","source",List.of(new TranscribedSegment(0,0,1000,"source")),Duration.ZERO,1000,Map.of());}
    private AsrExecutionStore.Session session() {
        var session=mock(AsrExecutionStore.Session.class);
        when(session.policy()).thenReturn(policy(4));when(session.deadline()).thenReturn(Instant.now().plusSeconds(5));
        return session;
    }
    @Test void persistedReusableResultSkipsBothPhysicalCallAndPermit() throws Exception {
        Path file=Files.writeString(directory.resolve("a.wav"),"audio");var session=session();
        when(session.reusable(0,AdaptiveAsrController.audioHash(file))).thenReturn(Optional.of(result()));
        try(var controller=new AdaptiveAsrController(session)) {
            var calls=new AtomicInteger();assertThat(controller.transcribe(0,file,()->{calls.incrementAndGet();return result();}).fullText()).isEqualTo("source");
            assertThat(calls).hasValue(0);verify(session,never()).tryAcquire(anyInt());
        }
    }
    @Test void lostCompletionFenceNeverBecomesARetryableProviderFailure() throws Exception {
        Path file=Files.writeString(directory.resolve("a.wav"),"audio");var session=session();
        var permit=new AsrExecutionStore.Permit(0,1);
        when(session.reusable(anyInt(),anyString())).thenReturn(Optional.empty());when(session.tryAcquire(0)).thenReturn(permit);
        doThrow(TranslationFailure.of(TranslationFailure.Reason.CANCELED)).when(session).succeeded(eq(permit),any());
        try(var controller=new AdaptiveAsrController(session)) {
            var calls=new AtomicInteger();
            assertThatThrownBy(()->controller.transcribe(0,file,()->{calls.incrementAndGet();return result();})).hasMessageContaining("CANCELED");
            assertThat(calls).hasValue(1);verify(session,never()).failed(any(),any());
        }
    }
    @Test void closingRegistrationCancelsWaitingSharedPermit() throws Exception {
        var registration=AsrProviderLimiter.register(policy(1));
        var first=registration.acquire(System.nanoTime()+TimeUnit.SECONDS.toNanos(2));
        var executor=Executors.newSingleThreadExecutor();
        try {
            var waiting=executor.submit(()->{try(var ignored=registration.acquire(System.nanoTime()+TimeUnit.SECONDS.toNanos(2))){return "unexpected";}});
            assertThatThrownBy(()->waiting.get(50,TimeUnit.MILLISECONDS)).isInstanceOf(TimeoutException.class);
            registration.close();
            assertThatThrownBy(()->waiting.get(1,TimeUnit.SECONDS)).isInstanceOf(ExecutionException.class).hasCauseInstanceOf(TranslationFailure.class);
        } finally {first.close();registration.close();executor.shutdownNow();}
    }
}
