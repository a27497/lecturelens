package com.example.courselingo.systemmodel;

import com.example.courselingo.ai.llm.*;
import com.example.courselingo.subtitle.pipeline.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import static org.assertj.core.api.Assertions.*;
import static com.example.courselingo.ai.llm.TranslationFailure.Reason.*;

class SystemModelTranslationV2Test {
    static LlmRequest request(String feature,boolean v2) {
        return new LlmRequest("req","task",List.of(new LlmMessage(LlmRole.USER,"JSON")),Duration.ofSeconds(120),0d,7000,3,
            Map.of("translationV2",v2,"modelRouting.stage",feature),LlmResponseFormat.JSON_OBJECT,new SystemModelExecutionRef("snapshot",10,"task",9));
    }
    static SystemModelResolvedRoute route(String feature) {
        return new SystemModelResolvedRoute(feature,"DATABASE",SystemModelProtocol.OPENAI_CHAT,"credential",1L,1L,
            "https://api.deepseek.com","deepseek-flash",Set.of("JSON_OUTPUT"),null,6000,null,null,true,"1234");
    }
    static SystemModelUrlPolicy urls() { return new SystemModelUrlPolicy(h->new java.net.InetAddress[]{java.net.InetAddress.getByName("8.8.8.8")}); }
    static String body(String finish,String content) throws Exception {
        return new ObjectMapper().writeValueAsString(Map.of("choices",List.of(Map.of("finish_reason",finish,"message",Map.of("content",content,"reasoning_content","private synthetic reasoning"))),
            "usage",Map.of("prompt_tokens",903,"completion_tokens",3073,"total_tokens",3976)));
    }
    @Test void lengthTakesPrecedenceOverEmptyContentAndCarriesFailedUsage() throws Exception {
        String response=body("length","");
        var client=new SystemModelChatClient(r->new OpenAiCompatibleClientResponse(200,response,Map.of(),Duration.ZERO),urls());
        assertThatThrownBy(()->client.generate(request("TRANSLATION_FULL_TEXT",true),route("TRANSLATION_FULL_TEXT"),"synthetic-key"))
            .isInstanceOfSatisfying(TranslationFailure.class,e->{
                assertThat(e.reason()).isEqualTo(TRUNCATED);assertThat(e.finishReason()).isEqualTo("length");
                assertThat(e.usage()).isEqualTo(new LlmUsage(903,3073,3976));
                assertThat(e.getMessage()).doesNotContain("synthetic-key","reasoning",response);
            });
    }
    @Test void onlyV2FullTextAddsThinkingAndKeepsFinalUrlAndRouteCap() throws Exception {
        var sent=new ArrayList<OpenAiCompatibleChatCompletionRequest>(); String response=body("stop","{\"segments\":[]}");
        var client=new SystemModelChatClient(r->{sent.add(r);return new OpenAiCompatibleClientResponse(200,response,Map.of(),Duration.ZERO);},urls());
        for(var feature:List.of("TRANSLATION_FULL_TEXT","SUBTITLE_TRANSLATION","COURSE_QA"))
            client.generate(request(feature,true),route(feature),"synthetic-key");
        var json=new ObjectMapper();
        assertThat(json.readTree(sent.get(0).body()).path("thinking").path("type").asText()).isEqualTo("disabled");
        assertThat(json.readTree(sent.get(0).body()).path("max_tokens").asInt()).isEqualTo(6000);
        assertThat(sent.get(0).uri().toString()).isEqualTo("https://api.deepseek.com/chat/completions");
        for(int i=1;i<3;i++) assertThat(json.readTree(sent.get(i).body()).has("thinking")).isFalse();
    }
    @ParameterizedTest @CsvSource({"401,AUTHENTICATION","404,MODEL_NOT_FOUND","429,RATE_LIMITED","500,UPSTREAM_5XX","408,TIMEOUT","400,INVALID_REQUEST"})
    void v2MakesExactlyOnePhysicalAttemptAndNeverEchoesProviderErrors(int status,String expected) {
        var calls=new AtomicInteger();
        var client=new SystemModelChatClient(r->{calls.incrementAndGet();return new OpenAiCompatibleClientResponse(status,
            "{\"error\":\"synthetic-key private diagnostic\"}",Map.of("Retry-After",List.of("9")),Duration.ZERO);},urls());
        assertThatThrownBy(()->client.generate(request("TRANSLATION_FULL_TEXT",true),route("TRANSLATION_FULL_TEXT"),"synthetic-key"))
            .isInstanceOfSatisfying(TranslationFailure.class,e->{assertThat(e.reason().name()).isEqualTo(expected);assertThat(e.retryAfterMillis()).isEqualTo(9000);assertThat(e.getMessage()).doesNotContain("synthetic-key","private diagnostic");});
        assertThat(calls.get()).isEqualTo(1);
    }
    @Test void emptyNonLengthAndInvalidJsonAreDifferent() throws Exception {
        for(String value:List.of("","not-json")) {
            String response=body("stop",value);
            var client=new SystemModelChatClient(r->new OpenAiCompatibleClientResponse(200,response,Map.of(),Duration.ZERO),urls());
            assertThatThrownBy(()->client.generate(request("TRANSLATION_FULL_TEXT",true),route("TRANSLATION_FULL_TEXT"),"synthetic-key"))
                .isInstanceOfSatisfying(TranslationFailure.class,e->assertThat(e.reason()).isEqualTo(value.isEmpty()?EMPTY_OUTPUT:FORMAT_INVALID));
        }
    }
    @Test void envPathAlsoUsesStrictSingleAttemptInsteadOfTextFallback() {
        var properties=new OpenAiCompatibleLlmProperties();properties.setApiKey("synthetic-key");
        properties.setBaseUrl("https://api.deepseek.com");properties.setModel("deepseek-flash");
        var calls=new AtomicInteger();var sent=new ArrayList<OpenAiCompatibleChatCompletionRequest>();
        var provider=new OpenAiCompatibleLlmProvider(properties,r->{calls.incrementAndGet();sent.add(r);
            return new OpenAiCompatibleClientResponse(400,"{\"error\":\"response_format json_object unsupported synthetic-key\"}",Map.of(),Duration.ZERO);});
        assertThatThrownBy(()->provider.generate(request("TRANSLATION_FULL_TEXT",true))).isInstanceOf(TranslationFailure.class);
        assertThat(calls.get()).isEqualTo(1);assertThat(sent.getFirst().body()).contains("\"thinking\":{\"type\":\"disabled\"}");
    }
}
