package com.example.courselingo.ai.asr;

import com.example.courselingo.ai.llm.*;
import com.example.courselingo.systemmodel.SystemModelExecutionRef;
import java.net.URI;
import java.net.http.*;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

class AsrPhysicalObservationTest {
    @TempDir Path temp;
    @Test @SuppressWarnings("unchecked") void environmentBailianHttpRecordsEachPhysicalAttemptBeforeAdapterValidation() throws Exception {
        var http=mock(HttpClient.class);HttpResponse<String> reply=mock(HttpResponse.class);
        when(reply.statusCode()).thenReturn(200);when(reply.body()).thenReturn("{\"usage\":{\"input_tokens\":100,\"output_tokens\":20,\"total_tokens\":120},\"output\":{\"text\":\"test\"}}");
        when(http.send(any(HttpRequest.class),any(HttpResponse.BodyHandler.class))).thenReturn(reply);
        var observer=new Capture();var transport=new JavaHttpBailianAsrTransport(http).observed(observer);
        try(var ignored=scope()) {transport.send(URI.create("https://example.invalid/asr"),"synthetic",new byte[0],Duration.ofSeconds(1));}
        assertThat(observer.calls.get()).isEqualTo(1);assertThat(observer.completion.usage()).isEqualTo(new LlmUsage(100,20,120));
        assertThat(observer.completion.errorCategory()).isNull();
    }
    @Test void environmentSiliconFlowMultipartIsObservedOnceWithoutKeepingTheAudioBody() throws Exception {
        var observer=new Capture();var sent=new AtomicInteger();Path audio=Files.write(temp.resolve("synthetic.wav"),new byte[]{1,2,3});
        var client=new JavaHttpSiliconFlowAsrClient(request->{sent.incrementAndGet();return new SiliconFlowAsrClientResponse(429,"{}",Map.of(),Duration.ZERO);}).observed(observer);
        try(var ignored=scope()) {client.transcribe(new SiliconFlowAsrClientRequest(URI.create("https://example.invalid/asr"),Map.of(),audio,"file",Map.of("model","synthetic"),Duration.ofSeconds(1)));}
        assertThat(observer.calls.get()).isEqualTo(1);assertThat(sent.get()).isEqualTo(1);
        assertThat(observer.summary.optionsJson()).isEqualTo("{}");assertThat(observer.summary.bodyBytes()).isGreaterThan(3);
        assertThat(observer.completion.errorCategory()).isEqualTo("RATE_LIMITED");assertThat(observer.completion.usage().promptTokens()).isNull();
    }
    private ModelCallScope scope(){return ModelCallScope.open(new ModelCallScope.Context(new SystemModelExecutionRef("s",10,"t",9),"ASR_TRANSCRIPTION","m",null,"event",0L,1000L,"SILENCE_SPLIT"));}
    static class Capture implements ModelCallObserver {
        AtomicInteger calls=new AtomicInteger();RequestSummary summary;Completion completion;
        public String begin(ModelCallScope.Context c,RequestSummary r){calls.incrementAndGet();summary=r;return "id";}
        public void complete(String id,Completion c){completion=c;}
    }
}
