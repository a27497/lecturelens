package com.example.courselingo.ai.llm;

import com.example.courselingo.systemmodel.SystemModelExecutionRef;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.*;

class ObservedModelCallTest {
    private static final String SYNTHETIC="sk-synthetic-observation-test";
    private ModelCallScope scope(){return ModelCallScope.open(new ModelCallScope.Context(new SystemModelExecutionRef("s",10,"t",9L),"LEARNING_PACKAGE","m",null,"event",null,null,null));}
    @Test void beginFailurePreventsNetworkAndCompletionFailureIsSafe() {
        var calls=new AtomicInteger();
        try(var ignored=scope()) {
            ModelCallObserver before=new ModelCallObserver(){public String begin(ModelCallScope.Context c,RequestSummary s){throw new IllegalStateException(SYNTHETIC);}public void complete(String id,Completion c){}};
            assertThatThrownBy(()->ObservedModelCall.execute(before,URI.create("https://example.invalid/chat"),Map.of(),new byte[0],true,()->{calls.incrementAndGet();return null;}))
                .isInstanceOf(TranslationFailure.class).hasMessageContaining("ACCOUNTING_INCOMPLETE").hasMessageNotContaining(SYNTHETIC).hasNoCause();
            assertThat(calls.get()).isZero();
            ModelCallObserver after=new ModelCallObserver(){public String begin(ModelCallScope.Context c,RequestSummary s){return "id";}public void complete(String id,Completion c){throw new IllegalStateException(SYNTHETIC);}};
            assertThatThrownBy(()->ObservedModelCall.execute(after,URI.create("https://example.invalid/chat"),Map.of(),new byte[0],true,()->{calls.incrementAndGet();return response(200,"{}");}))
                .isInstanceOf(TranslationFailure.class).hasNoCause();assertThat(calls.get()).isEqualTo(1);
        }
        assertThat(ModelCallScope.current()).isNull();
    }
    @Test void requestSummaryOmitsTextCredentialsAndQueryWhilePrivate400IsRedactedBeforeTruncation() {
        var observer=new Capture();String source="PRIVATE COURSE FULL TEXT";
        byte[] body=("{\"model\":\"m\",\"max_tokens\":512,\"messages\":[{\"role\":\"user\",\"content\":\""+source+"\"}],\"api_key\":\""+SYNTHETIC+"\"}").getBytes(StandardCharsets.UTF_8);
        try(var ignored=scope()) {
            ObservedModelCall.execute(observer,URI.create("https://example.invalid/chat?secret=value"),Map.of("Authorization","Bearer "+SYNTHETIC),body,true,
                ()->response(400,"{\"error\":\"bad format "+SYNTHETIC+"\"} "+"x".repeat(5000)));
        }
        assertThat(observer.summary.toString()).doesNotContain(source,SYNTHETIC,"secret=value");
        assertThat(observer.completion.privateErrorExcerpt()).hasSize(4000).contains("[redacted]").doesNotContain(SYNTHETIC);
        assertThat(observer.completion.truncated()).isTrue();assertThat(observer.completion.errorCategory()).isEqualTo("INVALID_REQUEST");
    }
    @Test void truncatedHttp200RetainsReasoningCacheAndUsageBeforeContentChecks() {
        var observer=new Capture();String body="{\"choices\":[{\"finish_reason\":\"length\",\"message\":{\"content\":\"\"}}],\"usage\":{\"prompt_tokens\":100,\"completion_tokens\":20,\"total_tokens\":120,\"prompt_cache_hit_tokens\":40,\"prompt_cache_miss_tokens\":60,\"completion_tokens_details\":{\"reasoning_tokens\":20}}}";
        try(var ignored=scope()){ObservedModelCall.execute(observer,URI.create("https://example.invalid/chat"),Map.of(),new byte[0],false,()->response(200,body));}
        assertThat(observer.completion.errorCategory()).isEqualTo("TRUNCATED");
        assertThat(observer.completion.usage()).isEqualTo(new LlmUsage(100,20,120,20,40,60));
        assertThat(observer.completion.privateErrorExcerpt()).isNull();
        assertThatThrownBy(()->TranslationResponseDecoder.decode(response(200,body),"m",Map.of()))
            .isInstanceOf(TranslationFailure.class).extracting("usage").isEqualTo(observer.completion.usage());
    }
    static OpenAiCompatibleClientResponse response(int status,String body){return new OpenAiCompatibleClientResponse(status,body,Map.of(),Duration.ofMillis(1));}
    static class Capture implements ModelCallObserver {
        RequestSummary summary;Completion completion;
        public String begin(ModelCallScope.Context context,RequestSummary summary){this.summary=summary;return "id";}
        public void complete(String id,Completion completion){this.completion=completion;}
    }
}
