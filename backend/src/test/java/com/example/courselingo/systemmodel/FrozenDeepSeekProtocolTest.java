package com.example.courselingo.systemmodel;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.example.courselingo.ai.llm.*;
import com.example.courselingo.modelrouting.*;
import com.example.courselingo.vision.analysis.*;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import java.awt.image.BufferedImage;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
import java.util.*;
import java.util.stream.Stream;
import javax.imageio.ImageIO;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class FrozenDeepSeekProtocolTest {
    enum Entry { TEXT, TEXT_PLAIN, SYSTEM_TEXT, SYSTEM_ENV, TRANSLATION_FULL, TRANSLATION_SEGMENT,
        VISION, SYSTEM_VISION, SYSTEM_VISION_ENV, PROBE, LANGCHAIN }
    enum Output { NORMAL, LENGTH_EMPTY, LENGTH_PARTIAL, LENGTH_JSON, LENGTH_DETAILED, EMPTY }
    private static final ObjectMapper JSON = new ObjectMapper();
    @TempDir Path temp;
    private final List<JsonNode> sent = new ArrayList<>();

    static Stream<Arguments> outputs() {
        return Arrays.stream(Entry.values()).flatMap(entry -> Arrays.stream(Output.values())
            .map(output -> Arguments.of(entry, output)));
    }

    static Stream<Arguments> models() {
        return Arrays.stream(Entry.values()).flatMap(entry -> Stream.of("deepseek-flash", "deepseek-v4-pro",
            "deepseek-v4-flash", "deepseek-v4-flash-vision-exp", "deepseek-chat", "deepseek-reasoner",
            "DeepSeek-V4.1-Flash-1017", "other-deepseek-flash", "Qwen/Qwen3-8B", "Qwen/Qwen3-VL-8B-Instruct")
            .map(model -> Arguments.of(entry, model)));
    }

    @ParameterizedTest @MethodSource("outputs")
    void requestAndOutputContractAtEachActualEntry(Entry entry, Output output) throws Exception {
        var outcome = execute(entry, output, "deepseek-flash");
        assertThat(sent).hasSize(1);
        assertThat(outcome.success()).isEqualTo(output == Output.NORMAL);
        if (output != Output.NORMAL) {
            Object diagnostics = outcome.failure() == null ? outcome.diagnostics()
                : property(outcome.failure(), "diagnostics");
            assertThat(diagnostics).isNotNull();
            assertThat(property(diagnostics, "reason").toString()).isEqualTo(
                output == Output.EMPTY ? "EMPTY_OUTPUT" : "TRUNCATED");
            assertThat(property(diagnostics, "httpStatus")).isEqualTo(entry == Entry.LANGCHAIN ? null : 200);
            assertThat(property(diagnostics, "finishReason")).isEqualTo(output == Output.EMPTY ? "stop" : "length");
            var usage = (LlmUsage) property(diagnostics, "usage");
            assertThat(usage).isEqualTo(new LlmUsage(750, 3072, 3822));
            assertThat(property(diagnostics, "reasoningTokens")).isEqualTo(output == Output.LENGTH_DETAILED ? 7 : null);
            if (outcome.failure() != null) {
                var details = LlmProviderFailureClassifier.from(outcome.failure());
                assertThat(details.category()).isEqualTo(LlmProviderFailureCategory.OUTPUT_INVALID);
                assertThat(details.retryable()).isFalse();
                assertThat(outcome.failure().getCause()).isNull();
                assertThat(outcome.failure().toString()).doesNotContain("private-response-marker", "synthetic-key");
            }
        }
        var body = sent.getFirst();
        int budget = body.has("max_tokens") ? body.path("max_tokens").asInt()
            : body.path("max_completion_tokens").asInt();
        assertThat(budget).isEqualTo(entry == Entry.PROBE ? 32 : 128);
    }

    @ParameterizedTest @MethodSource("models")
    void officialAllowlistAndOtherProvidersKeepTheirParameters(Entry entry, String model) throws Exception {
        assertThat(execute(entry, Output.NORMAL, model).success()).isTrue();
        assertThat(sent).hasSize(1);
        var body = sent.getFirst();
        boolean supported = Set.of("deepseek-flash", "deepseek-v4-pro", "deepseek-v4-flash",
            "deepseek-v4-flash-vision-exp").contains(model);
        assertThat(body.path("thinking").path("type").asText()).isEqualTo(supported ? "disabled" : "");
        assertThat(body.has("enable_thinking")).isEqualTo(entry != Entry.LANGCHAIN && model.equals("Qwen/Qwen3-8B"));
    }

    static Stream<Arguments> otherVendorLengths() {
        return Arrays.stream(Entry.values()).flatMap(entry -> Stream.of(Output.LENGTH_EMPTY, Output.LENGTH_PARTIAL, Output.LENGTH_JSON)
            .map(output -> Arguments.of(entry, output)));
    }

    @ParameterizedTest @MethodSource("otherVendorLengths")
    void truncationNeverSucceedsForOtherVendorsEither(Entry entry, Output output) throws Exception {
        var outcome = execute(entry, output, "Qwen/Qwen3-8B");
        assertThat(outcome.success()).isFalse();
        assertThat(sent).hasSize(1);
        Object diagnostics = outcome.failure() == null ? outcome.diagnostics() : property(outcome.failure(), "diagnostics");
        assertThat(diagnostics).isNotNull();
        assertThat(property(diagnostics, "reason").toString()).isEqualTo("TRUNCATED");
    }

    @ParameterizedTest @org.junit.jupiter.params.provider.ValueSource(strings = {
        "cancel", "snapshot", "lease"})
    void frozenRouteControlFailuresPropagateBeforeTransport(String control) throws Exception {
        RuntimeException failure = switch (control) {
            case "cancel" -> new java.util.concurrent.CancellationException("cancelled");
            case "snapshot" -> new com.example.courselingo.common.exception.BusinessException(
                com.example.courselingo.common.error.ErrorCode.SYSTEM_MODEL_CONFIG_CONFLICT);
            default -> new com.example.courselingo.common.exception.BusinessException(
                com.example.courselingo.common.error.ErrorCode.TASK_INVALID_STATUS);
        };
        var executions = mock(SystemModelExecutionService.class);
        when(executions.route(any(), anyString())).thenThrow(failure);
        var transport = mock(OpenAiCompatibleLlmClient.class);
        var urls = new SystemModelUrlPolicy(host -> new InetAddress[] { InetAddress.getByAddress(new byte[] {8,8,8,8}) });
        var ref = new SystemModelExecutionRef("snapshot-test", 13, "task-test", 42);
        var request = new LlmRequest("request-test", "task-test", List.of(new LlmMessage(LlmRole.USER, "JSON")),
            Duration.ofSeconds(2), 0d, 128, 3, Map.of("modelRouting.stage", "COURSE_QA"), LlmResponseFormat.JSON_OBJECT, ref);
        org.assertj.core.api.Assertions.assertThatThrownBy(() ->
            new SystemModelLlmProvider(executions, transport, urls, transport).generate(request)).isSameAs(failure);
        var modelRoute = new AiModelRoute(AiModelStage.VISION_FRAME_ANALYSIS, "system-13", "test", "openai-compatible",
            "https://model.example/v1", "deepseek-flash", "TEST_KEY", Set.of(ModelCapability.VISION), 0d, 128, Duration.ofSeconds(2), 3, ref);
        org.assertj.core.api.Assertions.assertThatThrownBy(() ->
            new SystemModelVisionProvider(executions, transport, new VisionAnalysisProperties(), urls)
                .analyze(new VisionAnalysisRequest("task-test", 42L, 0L, temp.resolve("unused.png"), "", "", modelRoute)))
            .isSameAs(failure);
        verifyNoInteractions(transport);
    }

    private Outcome execute(Entry entry, Output output, String model) throws Exception {
        String complete = entry == Entry.VISION || entry == Entry.SYSTEM_VISION || entry == Entry.SYSTEM_VISION_ENV
            ? "{\"screenType\":\"PPT\",\"summary\":\"private-response-marker\",\"detectedElements\":[\"title\"]}"
            : entry == Entry.TRANSLATION_FULL || entry == Entry.TRANSLATION_SEGMENT
                ? "{\"segments\":[]}" : "{\"ok\":true,\"value\":\"private-response-marker\"}";
        String content = switch (output) {
            case NORMAL, LENGTH_JSON, LENGTH_DETAILED -> complete;
            case EMPTY, LENGTH_EMPTY -> "";
            case LENGTH_PARTIAL -> "{\"value\":\"private-response-marker";
        };
        var usage = new HashMap<String, Object>(Map.of("prompt_tokens", 750, "completion_tokens", 3072, "total_tokens", 3822));
        if (output == Output.LENGTH_DETAILED) usage.put("completion_tokens_details", Map.of("reasoning_tokens", 7));
        String response = JSON.writeValueAsString(Map.of("model", model, "choices", List.of(Map.of(
            "index", 0, "finish_reason", output.name().startsWith("LENGTH") ? "length" : "stop",
            "message", Map.of("role", "assistant", "content", content))),
            "usage", usage));
        OpenAiCompatibleLlmClient transport = request -> {
            try { sent.add(JSON.readTree(request.body())); }
            catch (Exception e) { throw new AssertionError(e); }
            return new OpenAiCompatibleClientResponse(200, response, Map.of(), Duration.ZERO);
        };
        String feature = entry == Entry.TRANSLATION_FULL ? "TRANSLATION_FULL_TEXT"
            : entry == Entry.TRANSLATION_SEGMENT ? "SUBTITLE_TRANSLATION"
            : entry == Entry.SYSTEM_VISION || entry == Entry.SYSTEM_VISION_ENV ? "VISION_FRAME_ANALYSIS" : "COURSE_QA";
        HttpServer fixture = null;
        String baseUrl = "https://model.example/v1";
        if (entry == Entry.LANGCHAIN || entry == Entry.SYSTEM_VISION_ENV) {
            fixture = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            fixture.createContext("/v1/chat/completions", exchange -> {
                synchronized (sent) { sent.add(JSON.readTree(exchange.getRequestBody())); }
                byte[] bytes = response.getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().add("Content-Type", "application/json");
                exchange.sendResponseHeaders(200, bytes.length);
                try (var stream = exchange.getResponseBody()) { stream.write(bytes); }
            });
            fixture.start();
            baseUrl = "http://127.0.0.1:" + fixture.getAddress().getPort() + "/v1";
        }
        var ref = new SystemModelExecutionRef("snapshot-test", 13, "task-test", 42);
        var route = new SystemModelResolvedRoute(feature, entry == Entry.SYSTEM_ENV || entry == Entry.SYSTEM_VISION_ENV ? "ENV" : "DATABASE",
            SystemModelProtocol.OPENAI_CHAT, "credential-test", 1L, 1L, baseUrl, model,
            Set.of("TEXT_CHAT", "VISION", "JSON_OUTPUT"), 0d, 128, 2000L, 3, true, "test");
        var executions = mock(SystemModelExecutionService.class);
        when(executions.route(ref, feature)).thenReturn(route);
        when(executions.credential(ref, feature)).thenReturn("synthetic-key");
        var urls = new SystemModelUrlPolicy(host -> new InetAddress[] {InetAddress.getByAddress(new byte[] {8,8,8,8})});
        var request = new LlmRequest("request-test", "task-test", List.of(new LlmMessage(LlmRole.USER, "JSON")),
            Duration.ofSeconds(2), 0d, 128, 3, Map.of("modelRouting.stage", feature),
            entry == Entry.TEXT_PLAIN || entry == Entry.TRANSLATION_SEGMENT ? LlmResponseFormat.TEXT : LlmResponseFormat.JSON_OBJECT, ref);
        try {
            LlmResult generated = null;
            switch (entry) {
                case TEXT, TEXT_PLAIN -> {
                    var properties = new OpenAiCompatibleLlmProperties();
                    properties.setApiKey("synthetic-key"); properties.setBaseUrl("https://model.example/v1");
                    properties.setModel(model);
                    generated = new OpenAiCompatibleLlmProvider(properties, transport).generate(request);
                }
                case SYSTEM_TEXT, SYSTEM_ENV, TRANSLATION_FULL, TRANSLATION_SEGMENT ->
                    generated = new SystemModelLlmProvider(executions, transport, urls, transport).generate(request);
                case VISION, SYSTEM_VISION, SYSTEM_VISION_ENV -> {
                    Path image = temp.resolve("frame.png");
                    ImageIO.write(new BufferedImage(2, 2, BufferedImage.TYPE_INT_RGB), "png", image.toFile());
                    var modelRoute = new AiModelRoute(AiModelStage.VISION_FRAME_ANALYSIS, "system-13", "test",
                        "openai-compatible", route.baseUrl(), model, "TEST_KEY", Set.of(ModelCapability.VISION),
                        0d, 128, Duration.ofSeconds(2), 3, ref);
                    VisionModelProvider provider = entry == Entry.VISION
                        ? new OpenAiCompatibleVisionProvider(new VisionAnalysisProperties(), transport,
                            ignored -> "synthetic-key", JSON)
                        : new SystemModelVisionProvider(executions, transport, new VisionAnalysisProperties(), urls);
                    var result = provider.analyze(new VisionAnalysisRequest("task-test", 42L, 0L, image, "", "", modelRoute));
                    return new Outcome(result.status() == VisionAnalysisStatus.SUCCEEDED, null, result.errorCode(), optionalProperty(result, "outputDiagnostics"));
                }
                case PROBE -> {
                    var registry = mock(SystemModelRegistry.class);
                    when(registry.currentVersion()).thenReturn(13L);
                    when(registry.probeRoute(13, 1)).thenReturn(route);
                    when(registry.credential(13, route)).thenReturn("synthetic-key");
                    var http = mock(SystemModelHttpClient.class);
                    when(http.post(any(), anyMap(), anyString(), any(byte[].class), any())).thenAnswer(call -> {
                        sent.add(JSON.readTree((byte[]) call.getArgument(3)));
                        return new OpenAiCompatibleClientResponse(200, response, Map.of(), Duration.ZERO);
                    });
                    try (var probes = new SystemModelProbeService(registry, urls, http,
                            "https://model.example", Duration.ofSeconds(2), 1)) {
                        var result = probes.probe(new SystemModelProbeService.Command(13, 1), 42);
                        return new Outcome(result.ok(), null, result.category(), optionalProperty(result, "outputDiagnostics"));
                    }
                }
                case LANGCHAIN -> {
                    var properties = new LangChain4jLlmProperties();
                    properties.setBaseUrl(baseUrl);
                    properties.setApiKey("synthetic-key"); properties.setModel(model);
                    generated = new LangChain4jLlmProvider(properties, new DefaultLangChain4jChatModelClient(properties)).generate(request);
                }
            }
            if (output == Output.NORMAL) {
                assertThat(generated.content()).isEqualTo(complete);
                assertThat(generated.usage()).isEqualTo(new LlmUsage(750, 3072, 3822));
                assertThat(generated.finishReason()).isEqualTo(entry == Entry.LANGCHAIN ? "STOP" : "stop");
            }
            return new Outcome(true, null, null);
        } catch (RuntimeException failure) {
            return new Outcome(false, failure, null);
        } finally {
            if (fixture != null) fixture.stop(0);
        }
    }

    // Reflection lets the same behavioral regression compile against the untouched frozen baseline.
    private static Object property(Object target, String name) throws Exception {
        try { return target.getClass().getMethod(name).invoke(target); }
        catch (NoSuchMethodException missingOnBaseline) {
            throw new AssertionError("Missing safe protocol diagnostics accessor: " + name, missingOnBaseline);
        }
    }

    private static Object optionalProperty(Object target, String name) throws Exception {
        try { return property(target, name); }
        catch (AssertionError missingOnBaseline) { return null; }
    }

    private record Outcome(boolean success, Throwable failure, String category, Object diagnostics) {
        Outcome(boolean success, Throwable failure, String category) { this(success, failure, category, null); }
    }
}
