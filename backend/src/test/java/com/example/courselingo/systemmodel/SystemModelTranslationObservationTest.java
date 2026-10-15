package com.example.courselingo.systemmodel;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
import com.example.courselingo.ai.llm.*;
import com.example.courselingo.subtitle.diagnostic.TranslationCallDiagnostics;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.JsonNode;
import java.time.Duration;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class SystemModelTranslationObservationTest {
    @ParameterizedTest @CsvSource({"empty,CONTENT_EMPTY", "null,CONTENT_NULL", "missing,CONTENT_MISSING",
        "number,CONTENT_NON_STRING", "malformed,CONTENT_JSON_INVALID", "array,CONTENT_NOT_OBJECT", "envelope,ENVELOPE_JSON_INVALID"})
    void recordsSpecificFailureWithoutChangingPublicErrorOrRetries(String kind, String expected) throws Exception {
        var diagnostics = mock(TranslationCallDiagnostics.class);
        var transport = mock(OpenAiCompatibleLlmClient.class);
        String body = body(kind);
        when(transport.complete(any())).thenReturn(new OpenAiCompatibleClientResponse(200, body, Map.of(), Duration.ZERO));
        var client = new SystemModelChatClient(transport, urls(), diagnostics);
        assertThatThrownBy(() -> client.generate(request(), route(), "synthetic-runtime-key"))
            .isInstanceOfSatisfying(SystemModelCallFailure.class, e -> {
                assertThat(e.category()).isEqualTo("OUTPUT_INVALID");
                assertThat(e.details().retryable()).isFalse();
                assertThat(e.getMessage()).doesNotContain(expected, body, "synthetic-runtime-key");
            });
        var root = org.mockito.ArgumentCaptor.forClass(JsonNode.class);
        verify(diagnostics).provider(anyString(), eq(request()), eq("deepseek-flash"), eq(1), eq(200),
            eq(body), eq("synthetic-runtime-key"), root.capture(), eq(expected), anyLong());
        if (!kind.equals("envelope")) assertThat(root.getValue().path("usage").path("total_tokens").asInt()).isEqualTo(3373);
        verify(transport, times(1)).complete(any());
    }

    @Test void successfulContentAndLengthFinishAreUnchangedAndReferencePrivateDiagnostic() throws Exception {
        var diagnostics = mock(TranslationCallDiagnostics.class);
        String body = body("valid");
        var client = new SystemModelChatClient(r -> new OpenAiCompatibleClientResponse(200, body, Map.of(), Duration.ZERO), urls(), diagnostics);
        var result = client.generate(request(), route(), "synthetic-runtime-key");
        assertThat(result.finishReason()).isEqualTo("length");
        assertThat(result.content()).isEqualTo("{\"segments\":[{\"index\":0,\"text\":\"中文译文\"}]}");
        assertThat(result.usage().totalTokens()).isEqualTo(3373);
        assertThat(result.metadata().get(TranslationCallDiagnostics.RESULT_ID)).isInstanceOf(String.class);
        verify(diagnostics).provider(anyString(), any(), any(), eq(1), eq(200), eq(body), any(), any(), eq("PASSED"), anyLong());
    }

    @Test void httpRetriesRemainBoundedWithSeparateObservations() {
        var diagnostics = mock(TranslationCallDiagnostics.class);
        var transport = mock(OpenAiCompatibleLlmClient.class);
        when(transport.complete(any())).thenReturn(new OpenAiCompatibleClientResponse(429,"{\"error\":\"limited\"}",Map.of(),Duration.ZERO));
        var client = new SystemModelChatClient(transport, urls(), diagnostics);
        assertThatThrownBy(() -> client.generate(request(), route(), "synthetic-runtime-key")).isInstanceOf(SystemModelCallFailure.class);
        verify(transport,times(3)).complete(any());
        for (int attempt=1;attempt<=3;attempt++) verify(diagnostics).provider(anyString(),any(),any(),eq(attempt),eq(429),any(),any(),isNull(),eq("RATE_LIMIT"),anyLong());
    }

    private static String body(String kind) throws Exception {
        if (kind.equals("envelope")) return "not-json";
        var mapper = new ObjectMapper();
        var message = new LinkedHashMap<String,Object>();
        if (!kind.equals("missing")) message.put("content", switch (kind) {
            case "empty" -> ""; case "null" -> null; case "number" -> 5;
            case "malformed" -> "{bad"; case "array" -> "[]";
            default -> "{\"segments\":[{\"index\":0,\"text\":\"中文译文\"}]}";
        });
        return mapper.writeValueAsString(Map.of("choices",List.of(Map.of("message",message,"finish_reason","length")),
            "usage",Map.of("prompt_tokens",301,"completion_tokens",3072,"total_tokens",3373)));
    }
    private static SystemModelUrlPolicy urls() { return new SystemModelUrlPolicy(host -> new java.net.InetAddress[]{java.net.InetAddress.getByName("8.8.8.8")}); }
    private static LlmRequest request() { return new LlmRequest("req","task",List.of(new LlmMessage(LlmRole.USER,"JSON")),Duration.ofSeconds(120),0d,3072,3,Map.of(),LlmResponseFormat.JSON_OBJECT,new SystemModelExecutionRef("snapshot",10,"task",7)); }
    private static SystemModelResolvedRoute route() { return new SystemModelResolvedRoute("TRANSLATION_FULL_TEXT","DATABASE",SystemModelProtocol.OPENAI_CHAT,"credential",1L,1L,"https://api.deepseek.com","deepseek-flash",Set.of("JSON_OUTPUT"),null,null,null,null,true,"****"); }
}
