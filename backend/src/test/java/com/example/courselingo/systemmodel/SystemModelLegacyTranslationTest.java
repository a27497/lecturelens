package com.example.courselingo.systemmodel;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.example.courselingo.ai.llm.*;
import com.example.courselingo.subtitle.diagnostic.TranslationCallDiagnostics;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;

class SystemModelLegacyTranslationTest {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final String VALID = "{\"segments\":[{\"index\":0,\"text\":\"固定合成译文。\"}]}";

    @Test
    void lengthBeforeEmptyContentRetainsStatusUsageAndBoundedSafeDiagnosis() throws Exception {
        var transport = mock(OpenAiCompatibleLlmClient.class);
        var diagnostics = mock(TranslationCallDiagnostics.class);
        String response = body("length", "");
        when(transport.complete(any())).thenReturn(reply(200, response));
        var client = new SystemModelChatClient(transport, SystemModelTranslationV2Test.urls(), diagnostics);

        assertThatThrownBy(() -> client.generate(request(), route(), "synthetic-key"))
            .isInstanceOfSatisfying(TranslationFailure.class, failure -> {
                assertThat(failure.reason()).isEqualTo(TranslationFailure.Reason.TRUNCATED);
                assertThat(failure.check()).isEqualTo(TranslationFailure.Check.OUTPUT_TRUNCATED);
                assertThat(failure.status()).isEqualTo(200);
                assertThat(failure.finishReason()).isEqualTo("length");
                assertThat(failure.usage()).isEqualTo(new LlmUsage(903, 3073, 3976));
                assertThat(failure.transportRetryable()).isFalse();
                var stage = new LlmStageException("TRANSLATION_FULL_TEXT", failure);
                assertThat(stage.safeDiagnosticSummary()).contains("reason=TRUNCATED", "check=OUTPUT_TRUNCATED", "httpStatus=200", "finishReason=length");
                assertThat(stage.safeDiagnosticSummary()).doesNotContain(response, "synthetic-key", "synthetic reasoning");
            });
        verify(transport, times(1)).complete(any());
        verify(diagnostics).provider(anyString(), any(), any(), eq(1), eq(200), eq(response), any(), any(), eq("OUTPUT_TRUNCATED"), anyLong());
    }

    @ParameterizedTest
    @CsvSource({"empty,EMPTY_OUTPUT,CONTENT_EMPTY", "null,EMPTY_OUTPUT,CONTENT_NULL",
        "missing,FORMAT_INVALID,CONTENT_MISSING", "number,FORMAT_INVALID,CONTENT_NON_STRING",
        "json,FORMAT_INVALID,CONTENT_JSON_INVALID", "array,FORMAT_INVALID,CONTENT_NOT_OBJECT",
        "envelope,FORMAT_INVALID,ENVELOPE_JSON_INVALID"})
    void invalidOutputIsNotAcceptedOrBlindlyRetried(String kind, String reason, String check) throws Exception {
        var message = JSON.createObjectNode();
        switch (kind) {
            case "empty" -> message.put("content", "");
            case "null" -> message.putNull("content");
            case "number" -> message.put("content", 3);
            case "json" -> message.put("content", "{not-json}");
            case "array" -> message.put("content", "[]");
            default -> { }
        }
        String response = "envelope".equals(kind) ? "not-json" : JSON.writeValueAsString(Map.of(
            "choices", List.of(Map.of("message", message, "finish_reason", "stop"))));
        var calls = new AtomicInteger();
        var client = new SystemModelChatClient(r -> { calls.incrementAndGet(); return reply(200, response); }, SystemModelTranslationV2Test.urls());
        assertThatThrownBy(() -> client.generate(request(), route(), "synthetic-key"))
            .isInstanceOfSatisfying(TranslationFailure.class, failure -> {
                assertThat(failure.reason().name()).isEqualTo(reason);
                assertThat(failure.check().name()).isEqualTo(check);
                assertThat(failure.status()).isEqualTo(200);
                assertThat(failure.getCause()).isNull();
                assertThat(failure.getMessage()).doesNotContain(response, "synthetic-key");
            });
        assertThat(calls.get()).isEqualTo(1);
    }

    @Test
    void validCompletedObjectPreservesPayloadRequestParametersAndMetadata() throws Exception {
        var sent = new ArrayList<OpenAiCompatibleChatCompletionRequest>();
        var client = new SystemModelChatClient(r -> { sent.add(r); return reply(200, bodyUnchecked("stop", VALID)); }, SystemModelTranslationV2Test.urls());
        var result = client.generate(request(), route(), "synthetic-key");
        assertThat(result.content()).isEqualTo(VALID);
        assertThat(result.finishReason()).isEqualTo("stop");
        assertThat(result.metadata()).containsEntry("systemModel.snapshotId", "snapshot").containsEntry("systemModel.configVersion", 10L);
        assertThat(sent).hasSize(1);
        var payload = JSON.readTree(sent.getFirst().body());
        assertThat(payload.path("response_format").path("type").asText()).isEqualTo("json_object");
        assertThat(payload.path("max_tokens").asInt()).isEqualTo(6000);
        assertThat(payload.path("thinking").path("type").asText()).isEqualTo("disabled");
    }

    @Test
    void nonemptyLengthOutputIsStillTruncated() throws Exception {
        var client = new SystemModelChatClient(r -> reply(200, bodyUnchecked("length", VALID)), SystemModelTranslationV2Test.urls());
        assertThatThrownBy(() -> client.generate(request(), route(), "synthetic-key"))
            .isInstanceOfSatisfying(TranslationFailure.class, failure -> assertThat(failure.reason()).isEqualTo(TranslationFailure.Reason.TRUNCATED));
    }

    @Test
    void legacyMissingFinishRemainsCompatibleWhileV2StaysStrict() throws Exception {
        var node = JSON.readTree(body("stop", VALID));
        ((com.fasterxml.jackson.databind.node.ObjectNode) node.path("choices").path(0)).remove("finish_reason");
        var client = new SystemModelChatClient(r -> reply(200, node.toString()), SystemModelTranslationV2Test.urls());
        assertThat(client.generate(request(), route(), "synthetic-key").content()).isEqualTo(VALID);
        assertThatThrownBy(() -> client.generate(SystemModelTranslationV2Test.request("TRANSLATION_FULL_TEXT", true), route(), "synthetic-key"))
            .isInstanceOfSatisfying(TranslationFailure.class, failure -> assertThat(failure.check()).isEqualTo(TranslationFailure.Check.FINISH_REASON));
    }

    @Test
    void systemModelRouterPropagatesTruncationWithoutLegacyFallbackAndClearsScope() {
        var executions = mock(SystemModelExecutionService.class);
        var request = request();
        when(executions.route(request.execution(), "TRANSLATION_FULL_TEXT")).thenReturn(route());
        when(executions.credential(request.execution(), "TRANSLATION_FULL_TEXT")).thenReturn("synthetic-key");
        var transport = mock(OpenAiCompatibleLlmClient.class);
        var fallback = mock(OpenAiCompatibleLlmClient.class);
        when(transport.complete(any())).thenReturn(reply(200, bodyUnchecked("length", "")));
        var provider = new SystemModelLlmProvider(executions, transport, SystemModelTranslationV2Test.urls(), fallback);
        assertThatThrownBy(() -> provider.generate(request))
            .isInstanceOfSatisfying(TranslationFailure.class, failure -> {
                assertThat(failure.reason()).isEqualTo(TranslationFailure.Reason.TRUNCATED);
                assertThat(failure.status()).isEqualTo(200);
                assertThat(failure.usage().totalTokens()).isEqualTo(3976);
            });
        verify(transport, times(1)).complete(any());
        verifyNoInteractions(fallback);
        assertThat(ModelCallScope.current()).isNull();
    }

    @ParameterizedTest
    @ValueSource(strings = {"not JSON", "[]", "", "```json\n{}\n```"})
    void routerRejectsInvalidStructuredOutputWithNoFallbackOrRetry(String content) {
        var executions = mock(SystemModelExecutionService.class);
        var request = request();
        when(executions.route(request.execution(), "TRANSLATION_FULL_TEXT")).thenReturn(route());
        when(executions.credential(request.execution(), "TRANSLATION_FULL_TEXT")).thenReturn("synthetic-key");
        var transport = mock(OpenAiCompatibleLlmClient.class);
        var fallback = mock(OpenAiCompatibleLlmClient.class);
        when(transport.complete(any())).thenReturn(reply(200, bodyUnchecked("stop", content)));
        var provider = new SystemModelLlmProvider(executions, transport, SystemModelTranslationV2Test.urls(), fallback);
        assertThatThrownBy(() -> provider.generate(request))
            .isInstanceOfSatisfying(TranslationFailure.class, failure -> {
                assertThat(failure.details().category()).isEqualTo(LlmProviderFailureCategory.OUTPUT_INVALID);
                assertThat(failure.status()).isEqualTo(200);
                assertThat(failure.transportRetryable()).isFalse();
                assertThat(failure.getCause()).isNull();
            });
        verify(transport, times(1)).complete(any());
        verifyNoInteractions(fallback);
        assertThat(ModelCallScope.current()).isNull();
    }

    @Test
    void truncationAfterHttpRetryRetainsTheConsumedRetryCount() {
        var transport = mock(OpenAiCompatibleLlmClient.class);
        when(transport.complete(any())).thenReturn(reply(429, "{}"), reply(200, bodyUnchecked("length", "")));
        var client = new SystemModelChatClient(transport, SystemModelTranslationV2Test.urls());
        assertThatThrownBy(() -> client.generate(request(), route(), "synthetic-key"))
            .isInstanceOfSatisfying(TranslationFailure.class, failure -> {
                assertThat(failure.reason()).isEqualTo(TranslationFailure.Reason.TRUNCATED);
                assertThat(failure.providerRetryCount()).isEqualTo(1);
                assertThat(failure.usage().totalTokens()).isEqualTo(3976);
            });
        verify(transport, times(2)).complete(any());
    }

    @Test
    void otherFeaturesAlsoRejectTruncationWhileHttpRetryClassificationStaysUnchanged() {
        var calls = new AtomicInteger();
        var client = new SystemModelChatClient(r -> { calls.incrementAndGet(); return reply(429, "{\"error\":\"synthetic-limit\"}"); }, SystemModelTranslationV2Test.urls());
        assertThatThrownBy(() -> client.generate(request(), route(), "synthetic-key"))
            .isInstanceOfSatisfying(SystemModelCallFailure.class, failure -> {
                assertThat(failure.details().category()).isEqualTo(LlmProviderFailureCategory.RATE_LIMIT);
                assertThat(failure.details().httpStatus()).isEqualTo(429);
            });
        assertThat(calls.get()).isEqualTo(3);
        var other = new SystemModelChatClient(r -> reply(200, bodyUnchecked("length", "")), SystemModelTranslationV2Test.urls());
        assertThatThrownBy(() -> other.generate(SystemModelTranslationV2Test.request("COURSE_QA", false),
            SystemModelTranslationV2Test.route("COURSE_QA"), "synthetic-key"))
            .isInstanceOfSatisfying(TranslationFailure.class,
                failure -> assertThat(failure.reason()).isEqualTo(TranslationFailure.Reason.TRUNCATED));
    }

    private static LlmRequest request() { return SystemModelTranslationV2Test.request("TRANSLATION_FULL_TEXT", false); }
    private static SystemModelResolvedRoute route() { return SystemModelTranslationV2Test.route("TRANSLATION_FULL_TEXT"); }
    private static OpenAiCompatibleClientResponse reply(int status, String body) { return new OpenAiCompatibleClientResponse(status, body, Map.of(), Duration.ZERO); }
    private static String body(String finish, String content) throws Exception { return SystemModelTranslationV2Test.body(finish, content); }
    private static String bodyUnchecked(String finish, String content) { try { return body(finish, content); } catch (Exception e) { throw new AssertionError(e); } }
}
