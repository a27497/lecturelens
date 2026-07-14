package com.example.courselingo.ai.llm;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import dev.langchain4j.data.message.AiMessage;
import dev.langchain4j.data.message.ChatMessage;
import dev.langchain4j.data.message.SystemMessage;
import dev.langchain4j.data.message.UserMessage;
import dev.langchain4j.model.chat.response.ChatResponse;
import dev.langchain4j.model.output.FinishReason;
import dev.langchain4j.model.output.TokenUsage;
import java.io.IOException;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class LangChain4jLlmProviderTest {

    @Test
    void providerImplementsLlmProviderAndReturnsStableName() {
        LangChain4jLlmProvider provider = newProvider(properties(), new CapturingClient(ok("hello")));

        assertThat(provider).isInstanceOf(LlmProvider.class);
        assertThat(provider.providerName()).isEqualTo("langchain4j-openai-compatible");
    }

    @Test
    void validRequestCallsFakeClientWithMappedMessagesAndSettings() {
        CapturingClient client = new CapturingClient(ok("hello"));
        LangChain4jLlmProvider provider = newProvider(properties(), client);

        provider.generate(validRequest());

        LangChain4jClientRequest sent = client.singleRequest();
        assertThat(sent.messages()).hasSize(3);
        assertThat(sent.messages().get(0)).isInstanceOf(SystemMessage.class);
        assertThat(((SystemMessage) sent.messages().get(0)).text()).isEqualTo("system content");
        assertThat(sent.messages().get(1)).isInstanceOf(UserMessage.class);
        assertThat(((UserMessage) sent.messages().get(1)).singleText()).isEqualTo("user content");
        assertThat(sent.messages().get(2)).isInstanceOf(AiMessage.class);
        assertThat(((AiMessage) sent.messages().get(2)).text()).isEqualTo("assistant content");
        assertThat(sent.model()).isEqualTo("gpt-4o-mini");
        assertThat(sent.timeout()).isEqualTo(Duration.ofSeconds(30));
        assertThat(sent.temperature()).isEqualTo(0.4);
        assertThat(sent.maxTokens()).isEqualTo(512);
    }

    @Test
    void nullOptionalRequestSettingsUseConfiguredDefaults() {
        CapturingClient client = new CapturingClient(ok("hello"));
        LangChain4jLlmProvider provider = newProvider(properties(), client);
        LlmRequest request = new LlmRequest(
            "req_1",
            "task_1",
            List.of(new LlmMessage(LlmRole.USER, "hello")),
            null,
            null,
            null,
            Map.of()
        );

        provider.generate(request);

        LangChain4jClientRequest sent = client.singleRequest();
        assertThat(sent.timeout()).isEqualTo(Duration.ofSeconds(60));
        assertThat(sent.temperature()).isEqualTo(0.2);
        assertThat(sent.maxTokens()).isEqualTo(2048);
    }

    @Test
    void emptyApiKeyFailsBeforeClientCallAndIsSanitized() {
        LangChain4jLlmProperties properties = properties();
        properties.setApiKey(" ");
        CapturingClient client = new CapturingClient(ok("hello"));
        LangChain4jLlmProvider provider = newProvider(properties, client);

        assertThatThrownBy(() -> provider.generate(validRequest()))
            .isInstanceOf(LangChain4jLlmException.class)
            .satisfies(error -> {
                LangChain4jLlmException exception = (LangChain4jLlmException) error;
                assertThat(exception.retryable()).isFalse();
                assertSanitized(error.getMessage());
            });
        assertThat(client.requests()).isEmpty();
    }

    @ParameterizedTest
    @CsvSource({
        "'',base URL is required",
        "ftp://api.openai.com/v1,base URL must use http or https"
    })
    void invalidBaseUrlFailsBeforeClientCall(String baseUrl, String expectedMessage) {
        LangChain4jLlmProperties properties = properties();
        properties.setBaseUrl(baseUrl);
        CapturingClient client = new CapturingClient(ok("hello"));
        LangChain4jLlmProvider provider = newProvider(properties, client);

        assertThatThrownBy(() -> provider.generate(validRequest()))
            .isInstanceOf(LangChain4jLlmException.class)
            .hasMessageContaining(expectedMessage)
            .satisfies(error -> assertSanitized(error.getMessage()));
        assertThat(client.requests()).isEmpty();
    }

    @Test
    void emptyModelFailsBeforeClientCall() {
        LangChain4jLlmProperties properties = properties();
        properties.setModel(" ");
        CapturingClient client = new CapturingClient(ok("hello"));
        LangChain4jLlmProvider provider = newProvider(properties, client);

        assertThatThrownBy(() -> provider.generate(validRequest()))
            .isInstanceOf(LangChain4jLlmException.class)
            .hasMessageContaining("model is required");
        assertThat(client.requests()).isEmpty();
    }

    @ParameterizedTest
    @CsvSource({
        "requestId,request id is required",
        "taskId,task id is required",
        "messages,messages are required",
        "role,message role is required",
        "content,message content is required",
        "timeout,timeout must be positive",
        "temperatureLow,temperature must be between 0 and 2",
        "temperatureHigh,temperature must be between 0 and 2",
        "maxTokensZero,max completion count must be positive",
        "maxTokensHigh,max completion count exceeds limit"
    })
    void invalidRequestFailsBeforeClientCall(String scenario, String expectedMessage) {
        CapturingClient client = new CapturingClient(ok("hello"));
        LangChain4jLlmProvider provider = newProvider(properties(), client);

        assertThatThrownBy(() -> provider.generate(invalidRequest(scenario)))
            .isInstanceOf(LlmProviderException.class)
            .hasMessageContaining(expectedMessage)
            .satisfies(error -> assertSanitized(error.getMessage()));
        assertThat(client.requests()).isEmpty();
    }

    @ParameterizedTest
    @CsvSource({
        "connectTimeout,connect timeout must be positive",
        "requestTimeout,request timeout must be positive",
        "temperatureLow,temperature must be between 0 and 2",
        "temperatureHigh,temperature must be between 0 and 2",
        "maxTokensZero,max completion count must be positive",
        "maxTokensHigh,max completion count exceeds limit"
    })
    void invalidConfiguredDefaultsFailBeforeClientCall(String scenario, String expectedMessage) {
        LangChain4jLlmProperties properties = invalidProperties(scenario);
        CapturingClient client = new CapturingClient(ok("hello"));
        LangChain4jLlmProvider provider = newProvider(properties, client);

        assertThatThrownBy(() -> provider.generate(requestUsingDefaults()))
            .isInstanceOf(LangChain4jLlmException.class)
            .hasMessageContaining(expectedMessage)
            .satisfies(error -> assertSanitized(error.getMessage()));
        assertThat(client.requests()).isEmpty();
    }

    @Test
    void successfulResponseMapsContentModelFinishReasonUsageAndSafeMetadata() {
        CapturingClient client = new CapturingClient(new LangChain4jClientResponse(
            ChatResponse.builder()
                .aiMessage(AiMessage.from("mapped content"))
                .modelName("gpt-4o-mini-2026")
                .finishReason(FinishReason.STOP)
                .tokenUsage(new TokenUsage(11, 7, 18))
                .id("provider-trace-1")
                .build(),
            Duration.ofMillis(123)
        ));
        LangChain4jLlmProvider provider = newProvider(properties(), client);

        LlmResult result = provider.generate(validRequest());

        assertThat(result.provider()).isEqualTo("langchain4j-openai-compatible");
        assertThat(result.model()).isEqualTo("gpt-4o-mini-2026");
        assertThat(result.content()).isEqualTo("mapped content");
        assertThat(result.finishReason()).isEqualTo("STOP");
        assertThat(result.usage()).isEqualTo(new LlmUsage(11, 7, 18));
        assertThat(result.duration()).isEqualTo(Duration.ofMillis(123));
        assertThat(result.metadata()).containsEntry("providerTraceId", "provider-trace-1");
        assertSafeMetadata(result.metadata());
    }

    @Test
    void missingResponseMetadataUsesSafeDefaults() {
        CapturingClient client = new CapturingClient(new LangChain4jClientResponse(
            ChatResponse.builder()
                .aiMessage(AiMessage.from("mapped content"))
                .build(),
            Duration.ofMillis(1)
        ));
        LangChain4jLlmProvider provider = newProvider(properties(), client);

        LlmResult result = provider.generate(validRequest());

        assertThat(result.model()).isEqualTo("gpt-4o-mini");
        assertThat(result.finishReason()).isEqualTo("UNKNOWN");
        assertThat(result.usage()).isEqualTo(new LlmUsage(null, null, null));
        assertThat(result.metadata()).isEmpty();
    }

    @Test
    void sensitiveResponseIdIsNotCopiedToMetadata() {
        CapturingClient client = new CapturingClient(new LangChain4jClientResponse(
            ChatResponse.builder()
                .aiMessage(AiMessage.from("mapped content"))
                .id("Authorization: Bearer test-api-key")
                .build(),
            Duration.ofMillis(1)
        ));
        LangChain4jLlmProvider provider = newProvider(properties(), client);

        LlmResult result = provider.generate(validRequest());

        assertThat(result.metadata()).isEmpty();
        assertSafeMetadata(result.metadata());
    }

    @ParameterizedTest
    @CsvSource({
        "429,true",
        "500,true",
        "503,true",
        "504,true",
        "400,false"
    })
    void clientStatusExceptionPreservesRetryableFlagAndSanitizesMessage(int statusCode, boolean retryable) {
        LangChain4jLlmProvider provider = newProvider(
            properties(),
            new ThrowingClient(new LangChain4jLlmException(
                "LangChain4j request failed with HTTP " + statusCode + " token=abc secret=def apiKey=ghi Authorization: Bearer nope",
                retryable,
                statusCode
            ))
        );

        assertThatThrownBy(() -> provider.generate(validRequest()))
            .isInstanceOf(LangChain4jLlmException.class)
            .satisfies(error -> {
                LangChain4jLlmException exception = (LangChain4jLlmException) error;
                assertThat(exception.retryable()).isEqualTo(retryable);
                assertThat(exception.statusCode()).contains(statusCode);
                assertSanitized(error.getMessage());
            });
    }

    @Test
    void timeoutMapsToRetryableProviderException() {
        LangChain4jLlmProvider provider = newProvider(
            properties(),
            new ThrowingClient(new LangChain4jLlmException("timeout token=abc", true))
        );

        assertThatThrownBy(() -> provider.generate(validRequest()))
            .isInstanceOf(LangChain4jLlmException.class)
            .satisfies(error -> {
                LangChain4jLlmException exception = (LangChain4jLlmException) error;
                assertThat(exception.retryable()).isTrue();
                assertSanitized(error.getMessage());
            });
    }

    @Test
    void networkExceptionMapsToRetryableProviderException() {
        LangChain4jLlmProvider provider = newProvider(
            properties(),
            new ThrowingClient(new IllegalStateException("network secret=abc"))
        );

        assertThatThrownBy(() -> provider.generate(validRequest()))
            .isInstanceOf(LangChain4jLlmException.class)
            .satisfies(error -> {
                LangChain4jLlmException exception = (LangChain4jLlmException) error;
                assertThat(exception.retryable()).isTrue();
                assertSanitized(error.getMessage());
            });
    }

    @Test
    void nullResponseMapsToProviderException() {
        LangChain4jLlmProvider provider = newProvider(properties(), new CapturingClient(new LangChain4jClientResponse(null, Duration.ZERO)));

        assertThatThrownBy(() -> provider.generate(validRequest()))
            .isInstanceOf(LangChain4jLlmException.class)
            .satisfies(error -> {
                LangChain4jLlmException exception = (LangChain4jLlmException) error;
                assertThat(exception.retryable()).isFalse();
                assertSanitized(error.getMessage());
            });
    }

    @Test
    void configurationIsDisabledByDefaultAndEnabledOnlyByProperty() {
        new ApplicationContextRunner()
            .withUserConfiguration(LangChain4jLlmConfiguration.class)
            .run(context -> assertThat(context).doesNotHaveBean(LangChain4jLlmProvider.class));

        new ApplicationContextRunner()
            .withUserConfiguration(LangChain4jLlmConfiguration.class)
            .withPropertyValues("courselingo.ai.llm.langchain4j.enabled=true")
            .run(context -> {
                assertThat(context).hasSingleBean(LangChain4jLlmProvider.class);
                assertThat(context).hasSingleBean(LangChain4jLlmProperties.class);
            });
    }

    @Test
    void llmProviderDoesNotReferenceForbiddenPipelineIntegrations() throws IOException {
        String source = readJavaSources("src/main/java/com/example/courselingo/ai/llm");

        assertThat(source)
            .doesNotContain("AnalysisTaskRunner")
            .doesNotContain("RocketMQ")
            .doesNotContain("Jdbc")
            .doesNotContain("BaseMapper")
            .doesNotContain("Repository")
            .doesNotContain("subtitle")
            .doesNotContain("artifact")
            .doesNotContain("learning");
    }

    private LangChain4jLlmProvider newProvider(LangChain4jLlmProperties properties, LangChain4jChatModelClient client) {
        return new LangChain4jLlmProvider(properties, client);
    }

    private LangChain4jLlmProperties properties() {
        LangChain4jLlmProperties properties = new LangChain4jLlmProperties();
        properties.setApiKey("test-api-key");
        return properties;
    }

    private LangChain4jLlmProperties invalidProperties(String scenario) {
        LangChain4jLlmProperties properties = properties();
        switch (scenario) {
            case "connectTimeout" -> properties.setConnectTimeout(Duration.ZERO);
            case "requestTimeout" -> properties.setRequestTimeout(Duration.ZERO);
            case "temperatureLow" -> properties.setTemperature(-0.1);
            case "temperatureHigh" -> properties.setTemperature(2.1);
            case "maxTokensZero" -> properties.setMaxTokens(0);
            case "maxTokensHigh" -> properties.setMaxTokens(32769);
            default -> throw new IllegalArgumentException("unknown scenario");
        }
        return properties;
    }

    private LlmRequest validRequest() {
        return new LlmRequest(
            "req_1",
            "task_1",
            List.of(
                new LlmMessage(LlmRole.SYSTEM, "system content"),
                new LlmMessage(LlmRole.USER, "user content"),
                new LlmMessage(LlmRole.ASSISTANT, "assistant content")
            ),
            Duration.ofSeconds(30),
            0.4,
            512,
            Map.of("safe", true)
        );
    }

    private LlmRequest requestUsingDefaults() {
        return new LlmRequest(
            "req_1",
            "task_1",
            List.of(new LlmMessage(LlmRole.USER, "hello")),
            null,
            null,
            null,
            Map.of()
        );
    }

    private LlmRequest invalidRequest(String scenario) {
        return switch (scenario) {
            case "requestId" -> new LlmRequest("", "task_1", messages(), Duration.ofSeconds(30), 0.2, 512, Map.of());
            case "taskId" -> new LlmRequest("req_1", " ", messages(), Duration.ofSeconds(30), 0.2, 512, Map.of());
            case "messages" -> new LlmRequest("req_1", "task_1", List.of(), Duration.ofSeconds(30), 0.2, 512, Map.of());
            case "role" -> new LlmRequest("req_1", "task_1", List.of(new LlmMessage(null, "hello")), Duration.ofSeconds(30), 0.2, 512, Map.of());
            case "content" -> new LlmRequest("req_1", "task_1", List.of(new LlmMessage(LlmRole.USER, " ")), Duration.ofSeconds(30), 0.2, 512, Map.of());
            case "timeout" -> new LlmRequest("req_1", "task_1", messages(), Duration.ZERO, 0.2, 512, Map.of());
            case "temperatureLow" -> new LlmRequest("req_1", "task_1", messages(), Duration.ofSeconds(30), -0.1, 512, Map.of());
            case "temperatureHigh" -> new LlmRequest("req_1", "task_1", messages(), Duration.ofSeconds(30), 2.1, 512, Map.of());
            case "maxTokensZero" -> new LlmRequest("req_1", "task_1", messages(), Duration.ofSeconds(30), 0.2, 0, Map.of());
            case "maxTokensHigh" -> new LlmRequest("req_1", "task_1", messages(), Duration.ofSeconds(30), 0.2, 32769, Map.of());
            default -> throw new IllegalArgumentException("unknown scenario");
        };
    }

    private static List<LlmMessage> messages() {
        return List.of(new LlmMessage(LlmRole.USER, "hello"));
    }

    private static LangChain4jClientResponse ok(String content) {
        return new LangChain4jClientResponse(
            ChatResponse.builder()
                .aiMessage(AiMessage.from(content))
                .modelName("gpt-4o-mini")
                .finishReason(FinishReason.STOP)
                .tokenUsage(new TokenUsage(1, 1, 2))
                .build(),
            Duration.ofMillis(1)
        );
    }

    private static void assertSafeMetadata(Map<String, Object> metadata) {
        assertSanitized(metadata.toString());
        assertThat(metadata.toString()).doesNotContain("test-api-key", "Authorization");
    }

    private static void assertSanitized(String message) {
        assertThat(message).doesNotContain("abc", "def", "ghi", "test-api-key", "C:\\Users", "demo");
        assertThat(message.toLowerCase()).doesNotContain("token", "secret", "apikey", "api_key", "api key", "authorization");
    }

    private static String readJavaSources(String directory) throws IOException {
        java.nio.file.Path root = java.nio.file.Path.of(directory);
        if (!java.nio.file.Files.exists(root)) {
            return "";
        }
        StringBuilder source = new StringBuilder();
        try (var paths = java.nio.file.Files.walk(root)) {
            for (java.nio.file.Path path : paths.filter(path -> path.toString().endsWith(".java")).toList()) {
                source.append(java.nio.file.Files.readString(path)).append('\n');
            }
        }
        return source.toString();
    }

    private static final class CapturingClient implements LangChain4jChatModelClient {

        private final LangChain4jClientResponse response;
        private final List<LangChain4jClientRequest> requests = new ArrayList<>();

        private CapturingClient(LangChain4jClientResponse response) {
            this.response = response;
        }

        @Override
        public LangChain4jClientResponse complete(LangChain4jClientRequest request) {
            requests.add(request);
            return response;
        }

        List<LangChain4jClientRequest> requests() {
            return requests;
        }

        LangChain4jClientRequest singleRequest() {
            assertThat(requests).hasSize(1);
            return requests.getFirst();
        }
    }

    private static final class ThrowingClient implements LangChain4jChatModelClient {

        private final RuntimeException exception;

        private ThrowingClient(RuntimeException exception) {
            this.exception = exception;
        }

        @Override
        public LangChain4jClientResponse complete(LangChain4jClientRequest request) {
            throw exception;
        }
    }
}
