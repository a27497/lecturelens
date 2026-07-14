package com.example.courselingo.ai.llm;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.courselingo.modelrouting.AiModelRoutedLlmRequestFactory;
import java.io.IOException;
import java.net.URI;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class OpenAiCompatibleLlmProviderTest {

    @Test
    void providerImplementsLlmProviderAndReturnsStableName() {
        OpenAiCompatibleLlmProvider provider = newProvider(properties(), new CapturingClient(ok("hello")));

        assertThat(provider).isInstanceOf(LlmProvider.class);
        assertThat(provider.providerName()).isEqualTo("openai-compatible");
    }

    @Test
    void validRequestCallsClientWithFixedPathJsonBodyAndAuthorization() {
        CapturingClient client = new CapturingClient(ok("hello"));
        OpenAiCompatibleLlmProvider provider = newProvider(properties(), client);

        provider.generate(validRequest());

        OpenAiCompatibleChatCompletionRequest sent = client.singleRequest();
        assertThat(sent.uri()).isEqualTo(URI.create("https://api.siliconflow.cn/v1/chat/completions"));
        assertThat(sent.method()).isEqualTo("POST");
        assertThat(sent.contentType()).isEqualTo("application/json");
        assertThat(sent.headers()).containsEntry("Authorization", "Bearer test-api-key");
        assertThat(sent.timeout()).isEqualTo(Duration.ofSeconds(30));
        assertThat(sent.body())
            .contains("\"model\":\"Qwen/Qwen2.5-7B-Instruct\"")
            .contains("\"messages\"")
            .contains("\"role\":\"system\"")
            .contains("\"role\":\"user\"")
            .contains("\"temperature\":0.4")
            .contains("\"max_tokens\":512")
            .contains("\"response_format\":{\"type\":\"json_object\"}")
            .contains("\"stream\":false");
    }

    @Test
    void nullOptionalRequestSettingsUseConfiguredDefaults() {
        CapturingClient client = new CapturingClient(ok("hello"));
        OpenAiCompatibleLlmProvider provider = newProvider(properties(), client);
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

        OpenAiCompatibleChatCompletionRequest sent = client.singleRequest();
        assertThat(sent.timeout()).isEqualTo(Duration.ofSeconds(60));
        assertThat(sent.body())
            .contains("\"temperature\":0.0")
            .contains("\"max_tokens\":4096");
    }

    @Test
    void routedMetadataOverridesModelAndBaseUrlWithoutChangingApiKey() {
        CapturingClient client = new CapturingClient(ok("hello"));
        OpenAiCompatibleLlmProvider provider = newProvider(properties(), client);
        LlmRequest request = new LlmRequest(
            "req_1",
            "task_1",
            List.of(new LlmMessage(LlmRole.USER, "hello")),
            Duration.ofSeconds(45),
            0.0,
            1024,
            Map.of(
                AiModelRoutedLlmRequestFactory.METADATA_MODEL_NAME, "deepseek-ai/DeepSeek-V4-Pro",
                AiModelRoutedLlmRequestFactory.METADATA_BASE_URL, "https://api.siliconflow.cn/v1"
            )
        );

        provider.generate(request);

        OpenAiCompatibleChatCompletionRequest sent = client.singleRequest();
        assertThat(sent.uri()).isEqualTo(URI.create("https://api.siliconflow.cn/v1/chat/completions"));
        assertThat(sent.headers()).containsEntry("Authorization", "Bearer test-api-key");
        assertThat(sent.body())
            .contains("\"model\":\"deepseek-ai/DeepSeek-V4-Pro\"")
            .doesNotContain("test-api-key");
    }

    @Test
    void defaultSiliconFlowSettingsUseCnEndpointAndQwenModel() {
        CapturingClient client = new CapturingClient(ok("hello"));
        OpenAiCompatibleLlmProvider provider = newProvider(properties(), client);

        provider.generate(validRequestWithDefaults());

        OpenAiCompatibleChatCompletionRequest sent = client.singleRequest();
        assertThat(sent.uri()).isEqualTo(URI.create("https://api.siliconflow.cn/v1/chat/completions"));
        assertThat(sent.body())
            .contains("\"model\":\"Qwen/Qwen2.5-7B-Instruct\"")
            .contains("\"temperature\":0.0")
            .contains("\"max_tokens\":4096")
            .contains("\"response_format\":{\"type\":\"json_object\"}");
    }

    @Test
    void textResponseFormatOmitsJsonObjectResponseFormat() {
        CapturingClient client = new CapturingClient(ok("translated text"));
        OpenAiCompatibleLlmProvider provider = newProvider(properties(), client);

        provider.generate(textRequest());

        assertThat(client.singleRequest().body())
            .doesNotContain("response_format")
            .doesNotContain("json_object");
    }

    @Test
    void learningPackageJsonRequestStillIncludesJsonObjectResponseFormat() {
        CapturingClient client = new CapturingClient(ok("hello"));
        OpenAiCompatibleLlmProvider provider = newProvider(properties(), client);

        provider.generate(learningPackageJsonRequest());

        assertThat(client.singleRequest().body())
            .contains("\"response_format\":{\"type\":\"json_object\"}");
    }

    @Test
    void qwen3ModelDisablesThinking() {
        OpenAiCompatibleLlmProperties properties = properties();
        properties.setModel("Qwen/Qwen3-8B");
        CapturingClient client = new CapturingClient(ok("hello"));
        OpenAiCompatibleLlmProvider provider = newProvider(properties, client);

        provider.generate(validRequestWithDefaults());

        assertThat(client.singleRequest().body()).contains("\"enable_thinking\":false");
    }

    @Test
    void emptyApiKeyFailsBeforeClientCallAndIsSanitized() {
        OpenAiCompatibleLlmProperties properties = properties();
        properties.setApiKey(" ");
        CapturingClient client = new CapturingClient(ok("hello"));
        OpenAiCompatibleLlmProvider provider = newProvider(properties, client);

        assertThatThrownBy(() -> provider.generate(validRequest()))
            .isInstanceOf(OpenAiCompatibleLlmException.class)
            .satisfies(error -> {
                OpenAiCompatibleLlmException exception = (OpenAiCompatibleLlmException) error;
                assertThat(exception.retryable()).isFalse();
                assertSanitized(error.getMessage());
            });
        assertThat(client.requests()).isEmpty();
    }

    @ParameterizedTest
    @CsvSource({
        "'',base URL is required",
        "ftp://api.openai.com,base URL must use http or https"
    })
    void invalidBaseUrlFailsBeforeClientCall(String baseUrl, String expectedMessage) {
        OpenAiCompatibleLlmProperties properties = properties();
        properties.setBaseUrl(baseUrl);
        CapturingClient client = new CapturingClient(ok("hello"));
        OpenAiCompatibleLlmProvider provider = newProvider(properties, client);

        assertThatThrownBy(() -> provider.generate(validRequest()))
            .isInstanceOf(OpenAiCompatibleLlmException.class)
            .hasMessageContaining(expectedMessage)
            .satisfies(error -> assertSanitized(error.getMessage()));
        assertThat(client.requests()).isEmpty();
    }

    @ParameterizedTest
    @CsvSource({
        "'',model is required",
        "too-long-model-name-too-long-model-name-too-long-model-name-too-long-model-name-too-long-model-name-too-long-model-name-too-long-model-name-too-long-model-name,model is too long"
    })
    void invalidModelFailsBeforeClientCall(String model, String expectedMessage) {
        OpenAiCompatibleLlmProperties properties = properties();
        properties.setModel(model);
        CapturingClient client = new CapturingClient(ok("hello"));
        OpenAiCompatibleLlmProvider provider = newProvider(properties, client);

        assertThatThrownBy(() -> provider.generate(validRequest()))
            .isInstanceOf(OpenAiCompatibleLlmException.class)
            .hasMessageContaining(expectedMessage);
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
        OpenAiCompatibleLlmProvider provider = newProvider(properties(), client);

        assertThatThrownBy(() -> provider.generate(invalidRequest(scenario)))
            .isInstanceOf(LlmProviderException.class)
            .hasMessageContaining(expectedMessage)
            .satisfies(error -> assertSanitized(error.getMessage()));
        assertThat(client.requests()).isEmpty();
    }

    @Test
    void successfulResponseMapsContentFinishReasonUsageAndSafeMetadata() {
        CapturingClient client = new CapturingClient(new OpenAiCompatibleClientResponse(
            200,
            """
                {
                  "id": "chatcmpl-safe",
                  "model": "gpt-4o-mini-2024-07-18",
                  "choices": [
                    {
                      "message": {"role": "assistant", "content": "translated text"},
                      "finish_reason": "stop"
                    }
                  ],
                  "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}
                }
                """,
            Map.of("x-request-id", List.of("provider-trace-1")),
            Duration.ofMillis(123)
        ));
        OpenAiCompatibleLlmProvider provider = newProvider(properties(), client);

        LlmResult result = provider.generate(validRequest());

        assertThat(result.provider()).isEqualTo("openai-compatible");
        assertThat(result.model()).isEqualTo("gpt-4o-mini-2024-07-18");
        assertThat(result.content()).isEqualTo("translated text");
        assertThat(result.finishReason()).isEqualTo("stop");
        assertThat(result.usage()).isEqualTo(new LlmUsage(11, 7, 18));
        assertThat(result.duration()).isEqualTo(Duration.ofMillis(123));
        assertThat(result.metadata()).containsEntry("providerTraceId", "provider-trace-1");
        assertSafeMetadata(result.metadata());
    }

    @Test
    void siliconFlowStandardChatCompletionResponseParsesPlainTextContent() {
        OpenAiCompatibleLlmProvider provider = newProvider(
            properties(),
            new CapturingClient(new OpenAiCompatibleClientResponse(
                200,
                """
                    {
                      "id": "xxx",
                      "object": "chat.completion",
                      "created": 1782759060,
                      "model": "Qwen/Qwen2.5-7B-Instruct",
                      "choices": [
                        {
                          "index": 0,
                          "message": {
                            "role": "assistant",
                            "content": "Hello everyone 这是一个关于 Spring Boot 的短课程视频。"
                          },
                          "finish_reason": "stop"
                        }
                      ]
                    }
                    """,
                Map.of(),
                Duration.ofMillis(675)
            ))
        );

        LlmResult result = provider.generate(textRequest());

        assertThat(result.model()).isEqualTo("Qwen/Qwen2.5-7B-Instruct");
        assertThat(result.content()).isEqualTo("Hello everyone 这是一个关于 Spring Boot 的短课程视频。");
        assertThat(result.finishReason()).isEqualTo("stop");
        assertThat(result.usage()).isEqualTo(new LlmUsage(null, null, null));
    }

    @Test
    void responseWithoutUsageStillParses() {
        OpenAiCompatibleLlmProvider provider = newProvider(
            properties(),
            new CapturingClient(new OpenAiCompatibleClientResponse(
                200,
                """
                    {
                      "model": "Qwen/Qwen2.5-7B-Instruct",
                      "choices": [
                        {
                          "message": {"role": "assistant", "content": "translated text"},
                          "finish_reason": "stop"
                        }
                      ]
                    }
                    """,
                Map.of(),
                Duration.ofMillis(1)
            ))
        );

        LlmResult result = provider.generate(textRequest());

        assertThat(result.content()).isEqualTo("translated text");
        assertThat(result.usage()).isEqualTo(new LlmUsage(null, null, null));
    }

    @Test
    void responseWithoutFinishReasonStillParses() {
        OpenAiCompatibleLlmProvider provider = newProvider(
            properties(),
            new CapturingClient(new OpenAiCompatibleClientResponse(
                200,
                """
                    {
                      "model": "Qwen/Qwen2.5-7B-Instruct",
                      "choices": [
                        {
                          "message": {"role": "assistant", "content": "translated text"}
                        }
                      ]
                    }
                    """,
                Map.of(),
                Duration.ofMillis(1)
            ))
        );

        LlmResult result = provider.generate(textRequest());

        assertThat(result.content()).isEqualTo("translated text");
        assertThat(result.finishReason()).isEmpty();
    }

    @Test
    void responseWithExtraFieldsStillParses() {
        OpenAiCompatibleLlmProvider provider = newProvider(
            properties(),
            new CapturingClient(new OpenAiCompatibleClientResponse(
                200,
                """
                    {
                      "id": "xxx",
                      "object": "chat.completion",
                      "created": 1782759060,
                      "model": "Qwen/Qwen2.5-7B-Instruct",
                      "extra_top_level": {"ignored": true},
                      "choices": [
                        {
                          "index": 0,
                          "message": {
                            "role": "assistant",
                            "content": "translated text",
                            "tool_calls": []
                          },
                          "finish_reason": "stop",
                          "extra_choice_field": "ignored"
                        }
                      ],
                      "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3, "extra_usage": 4}
                    }
                    """,
                Map.of(),
                Duration.ofMillis(1)
            ))
        );

        LlmResult result = provider.generate(textRequest());

        assertThat(result.content()).isEqualTo("translated text");
        assertThat(result.usage()).isEqualTo(new LlmUsage(1, 2, 3));
    }

    @Test
    void successfulChatCompletionEnvelopeReturnsMessageContentOnly() {
        String content = "{\"segments\":[{\"index\":0,\"text\":\"hello\"}]}";
        OpenAiCompatibleLlmProvider provider = newProvider(
            properties(),
            new CapturingClient(chatCompletion(content))
        );

        LlmResult result = provider.generate(validRequest());

        assertThat(result.content()).isEqualTo(content);
    }

    @Test
    void successfulChatCompletionEnvelopeReturnsEscapedJsonStringContentOnly() {
        String content = "\"{\\\"segments\\\":[{\\\"index\\\":0,\\\"text\\\":\\\"hello\\\"}]}\"";
        OpenAiCompatibleLlmProvider provider = newProvider(
            properties(),
            new CapturingClient(chatCompletion(content))
        );

        LlmResult result = provider.generate(validRequest());

        assertThat(result.content()).isEqualTo(content);
    }

    @Test
    void textModeReturnsTrimmedMessageContentWithoutParsingContentAsJson() {
        OpenAiCompatibleLlmProvider provider = newProvider(
            properties(),
            new CapturingClient(chatCompletion("  not-json: plain translated text  \n"))
        );

        LlmResult result = provider.generate(textRequest());

        assertThat(result.content()).isEqualTo("not-json: plain translated text");
    }

    @Test
    void emptyChoicesMapsToProviderException() {
        OpenAiCompatibleLlmProvider provider = newProvider(
            properties(),
            new CapturingClient(new OpenAiCompatibleClientResponse(200, "{\"choices\":[]}", Map.of(), Duration.ZERO))
        );

        assertThatThrownBy(() -> provider.generate(validRequest()))
            .isInstanceOf(OpenAiCompatibleLlmException.class)
            .satisfies(error -> {
                OpenAiCompatibleLlmException exception = (OpenAiCompatibleLlmException) error;
                assertThat(exception.failureType()).isEqualTo(LlmProviderFailureType.MALFORMED_RESPONSE);
                assertThat(exception.retryable()).isFalse();
                assertSanitized(error.getMessage());
            });
    }

    @Test
    void missingMessageMapsToMalformedResponse() {
        OpenAiCompatibleLlmProvider provider = newProvider(
            properties(),
            new CapturingClient(new OpenAiCompatibleClientResponse(
                200,
                "{\"model\":\"gpt-4o-mini\",\"choices\":[{\"finish_reason\":\"stop\"}]}",
                Map.of(),
                Duration.ofMillis(1)
            ))
        );

        assertThatThrownBy(() -> provider.generate(textRequest()))
            .isInstanceOf(OpenAiCompatibleLlmException.class)
            .satisfies(error -> {
                OpenAiCompatibleLlmException exception = (OpenAiCompatibleLlmException) error;
                assertThat(exception.failureType()).isEqualTo(LlmProviderFailureType.MALFORMED_RESPONSE);
                assertThat(exception.retryable()).isFalse();
            });
    }

    @Test
    void emptyContentResponseMapsToMalformedResponse() {
        OpenAiCompatibleLlmProvider provider = newProvider(
            properties(),
            new CapturingClient(new OpenAiCompatibleClientResponse(
                200,
                "{\"model\":\"gpt-4o-mini\",\"choices\":[{\"message\":{\"content\":\"\"},\"finish_reason\":\"stop\"}]}",
                Map.of(),
                Duration.ofMillis(1)
            ))
        );

        assertThatThrownBy(() -> provider.generate(validRequest()))
            .isInstanceOf(OpenAiCompatibleLlmException.class)
            .satisfies(error -> {
                OpenAiCompatibleLlmException exception = (OpenAiCompatibleLlmException) error;
                assertThat(exception.failureType()).isEqualTo(LlmProviderFailureType.MALFORMED_RESPONSE);
                assertThat(exception.retryable()).isFalse();
            });
    }

    @Test
    void missingMessageContentPathMapsToMalformedResponse() {
        OpenAiCompatibleLlmProvider provider = newProvider(
            properties(),
            new CapturingClient(new OpenAiCompatibleClientResponse(
                200,
                "{\"model\":\"gpt-4o-mini\",\"choices\":[{\"message\":{\"role\":\"assistant\"},\"finish_reason\":\"stop\"}]}",
                Map.of(),
                Duration.ofMillis(1)
            ))
        );

        assertThatThrownBy(() -> provider.generate(validRequest()))
            .isInstanceOf(OpenAiCompatibleLlmException.class)
            .satisfies(error -> {
                OpenAiCompatibleLlmException exception = (OpenAiCompatibleLlmException) error;
                assertThat(exception.failureType()).isEqualTo(LlmProviderFailureType.MALFORMED_RESPONSE);
                assertThat(exception.retryable()).isFalse();
            });
    }

    @ParameterizedTest
    @CsvSource({
        "400,false",
        "401,false",
        "403,false",
        "404,false",
        "429,true",
        "500,true",
        "503,true",
        "504,true"
    })
    void httpStatusMapsToProviderException(int statusCode, boolean retryable) {
        OpenAiCompatibleLlmProvider provider = newProvider(
            properties(),
            new CapturingClient(new OpenAiCompatibleClientResponse(
                statusCode,
                "{\"error\":\"token=abc secret=def apiKey=ghi Authorization: Bearer nope C:\\\\Users\\\\demo\\\\private.txt\"}",
                Map.of(),
                Duration.ofMillis(1)
            ))
        );

        assertThatThrownBy(() -> provider.generate(validRequest()))
            .isInstanceOf(OpenAiCompatibleLlmException.class)
            .satisfies(error -> {
                OpenAiCompatibleLlmException exception = (OpenAiCompatibleLlmException) error;
                assertThat(exception.failureType()).isEqualTo(expectedFailureType(statusCode));
                assertThat(exception.retryable()).isEqualTo(retryable);
                assertThat(exception.statusCode()).contains(statusCode);
                assertThat(exception.responseBodySummary()).isPresent();
                assertThat(exception.responseBodySummary().orElseThrow()).hasSizeLessThanOrEqualTo(1000);
                assertSanitized(error.getMessage());
            });
    }

    @Test
    void timeoutMapsToRetryableProviderException() {
        OpenAiCompatibleLlmProvider provider = newProvider(
            properties(),
            new ThrowingClient(new OpenAiCompatibleLlmException("timeout token=abc", true))
        );

        assertThatThrownBy(() -> provider.generate(validRequest()))
            .isInstanceOf(OpenAiCompatibleLlmException.class)
            .satisfies(error -> {
                OpenAiCompatibleLlmException exception = (OpenAiCompatibleLlmException) error;
                assertThat(exception.failureType()).isEqualTo(LlmProviderFailureType.TIMEOUT);
                assertThat(exception.retryable()).isTrue();
                assertSanitized(error.getMessage());
            });
    }

    @Test
    void networkExceptionMapsToRetryableProviderException() {
        OpenAiCompatibleLlmProvider provider = newProvider(
            properties(),
            new ThrowingClient(new IllegalStateException("network secret=abc"))
        );

        assertThatThrownBy(() -> provider.generate(validRequest()))
            .isInstanceOf(OpenAiCompatibleLlmException.class)
            .satisfies(error -> {
                OpenAiCompatibleLlmException exception = (OpenAiCompatibleLlmException) error;
                assertThat(exception.failureType()).isEqualTo(LlmProviderFailureType.CONNECTION_ERROR);
                assertThat(exception.retryable()).isTrue();
                assertSanitized(error.getMessage());
            });
    }

    @Test
    void invalidJsonMapsToProviderException() {
        OpenAiCompatibleLlmProvider provider = newProvider(
            properties(),
            new CapturingClient(new OpenAiCompatibleClientResponse(200, "{not-json", Map.of(), Duration.ofMillis(1)))
        );

        assertThatThrownBy(() -> provider.generate(validRequest()))
            .isInstanceOf(OpenAiCompatibleLlmException.class)
            .satisfies(error -> {
                OpenAiCompatibleLlmException exception = (OpenAiCompatibleLlmException) error;
                assertThat(exception.failureType()).isEqualTo(LlmProviderFailureType.MALFORMED_RESPONSE);
                assertThat(exception.retryable()).isFalse();
                assertThat(exception.responseBodySummary()).isPresent();
                assertSanitized(error.getMessage());
            });
    }

    @Test
    void retryableHttpStatusesAreRetriedOnceBeforeFailure() {
        SequencedClient client = new SequencedClient(
            new OpenAiCompatibleClientResponse(500, "{\"error\":\"temporary\"}", Map.of(), Duration.ofMillis(10)),
            ok("hello")
        );
        OpenAiCompatibleLlmProvider provider = newProvider(properties(), client);

        LlmResult result = provider.generate(validRequest());

        assertThat(result.content()).isEqualTo("hello");
        assertThat(client.requests()).hasSize(2);
    }

    @Test
    void javaHttpClientBuildsJsonRequestWithoutRealNetworkCall() {
        CapturingHttpTransport transport = new CapturingHttpTransport(new OpenAiCompatibleClientResponse(
            200,
            "{\"choices\":[{\"message\":{\"content\":\"ok\"},\"finish_reason\":\"stop\"}]}",
            Map.of(),
            Duration.ofMillis(2)
        ));
        JavaHttpOpenAiCompatibleLlmClient client = new JavaHttpOpenAiCompatibleLlmClient(transport);
        OpenAiCompatibleChatCompletionRequest request = new OpenAiCompatibleChatCompletionRequest(
            URI.create("https://api.openai.com/v1/chat/completions"),
            Map.of("Authorization", "Bearer test-api-key"),
            "POST",
            "application/json",
            "{\"model\":\"gpt-4o-mini\",\"stream\":false}",
            Duration.ofSeconds(60)
        );

        OpenAiCompatibleClientResponse response = client.complete(request);

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(transport.request().method()).isEqualTo("POST");
        assertThat(transport.request().contentType()).isEqualTo("application/json");
        assertThat(transport.request().headers()).containsEntry("Authorization", "Bearer test-api-key");
        assertThat(transport.request().body()).contains("\"model\":\"gpt-4o-mini\"");
    }

    @Test
    void configurationIsDisabledByDefaultAndEnabledOnlyByProperty() {
        new ApplicationContextRunner()
            .withUserConfiguration(OpenAiCompatibleLlmConfiguration.class)
            .run(context -> assertThat(context).doesNotHaveBean(OpenAiCompatibleLlmProvider.class));

        new ApplicationContextRunner()
            .withUserConfiguration(OpenAiCompatibleLlmConfiguration.class)
            .withPropertyValues("courselingo.ai.llm.openai-compatible.enabled=true")
            .run(context -> {
                assertThat(context).hasSingleBean(OpenAiCompatibleLlmProvider.class);
                assertThat(context).hasSingleBean(OpenAiCompatibleLlmProperties.class);
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

    private OpenAiCompatibleLlmProvider newProvider(OpenAiCompatibleLlmProperties properties, OpenAiCompatibleLlmClient client) {
        return new OpenAiCompatibleLlmProvider(properties, client);
    }

    private OpenAiCompatibleLlmProperties properties() {
        OpenAiCompatibleLlmProperties properties = new OpenAiCompatibleLlmProperties();
        properties.setApiKey("test-api-key");
        return properties;
    }

    private LlmRequest validRequest() {
        return new LlmRequest(
            "req_1",
            "task_1",
            List.of(
                new LlmMessage(LlmRole.SYSTEM, "You are concise."),
                new LlmMessage(LlmRole.USER, "Translate this.")
            ),
            Duration.ofSeconds(30),
            0.4,
            512,
            Map.of("safe", true)
        );
    }

    private LlmRequest validRequestWithDefaults() {
        return new LlmRequest(
            "req_1",
            "task_1",
            List.of(new LlmMessage(LlmRole.USER, "Translate this.")),
            null,
            null,
            null,
            Map.of("safe", true)
        );
    }

    private LlmRequest textRequest() {
        return new LlmRequest(
            "req_1",
            "task_1",
            List.of(new LlmMessage(LlmRole.USER, "Translate this.")),
            Duration.ofSeconds(30),
            0.1,
            512,
            Map.of("scenario", "subtitle_translation"),
            LlmResponseFormat.TEXT
        );
    }

    private LlmRequest learningPackageJsonRequest() {
        return new LlmRequest(
            "req_1",
            "task_1",
            List.of(new LlmMessage(LlmRole.USER, "Build a learning package.")),
            Duration.ofSeconds(30),
            0.2,
            512,
            Map.of("scenario", "learning_package"),
            LlmResponseFormat.JSON_OBJECT
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

    private static OpenAiCompatibleClientResponse ok(String content) {
        return new OpenAiCompatibleClientResponse(
            200,
            "{\"model\":\"gpt-4o-mini\",\"choices\":[{\"message\":{\"content\":\"" + content + "\"},\"finish_reason\":\"stop\"}],\"usage\":{\"prompt_tokens\":1,\"completion_tokens\":1,\"total_tokens\":2}}",
            Map.of(),
            Duration.ofMillis(1)
        );
    }

    private static OpenAiCompatibleClientResponse chatCompletion(String content) {
        try {
            String body = new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(Map.of(
                "model", "Qwen/Qwen2.5-7B-Instruct",
                "choices", List.of(Map.of(
                    "message", Map.of("role", "assistant", "content", content),
                    "finish_reason", "stop"
                )),
                "usage", Map.of("prompt_tokens", 1, "completion_tokens", 1, "total_tokens", 2)
            ));
            return new OpenAiCompatibleClientResponse(200, body, Map.of(), Duration.ofMillis(1));
        } catch (com.fasterxml.jackson.core.JsonProcessingException exception) {
            throw new IllegalStateException(exception);
        }
    }

    private static void assertSafeMetadata(Map<String, Object> metadata) {
        assertSanitized(metadata.toString());
        assertThat(metadata.toString()).doesNotContain("test-api-key", "Authorization");
    }

    private static LlmProviderFailureType expectedFailureType(int statusCode) {
        return switch (statusCode) {
            case 401, 403 -> LlmProviderFailureType.PROVIDER_AUTH_FAILED;
            case 429 -> LlmProviderFailureType.PROVIDER_RATE_LIMIT;
            default -> LlmProviderFailureType.HTTP_ERROR;
        };
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

    private static final class CapturingClient implements OpenAiCompatibleLlmClient {

        private final OpenAiCompatibleClientResponse response;
        private final List<OpenAiCompatibleChatCompletionRequest> requests = new ArrayList<>();

        private CapturingClient(OpenAiCompatibleClientResponse response) {
            this.response = response;
        }

        @Override
        public OpenAiCompatibleClientResponse complete(OpenAiCompatibleChatCompletionRequest request) {
            requests.add(request);
            return response;
        }

        List<OpenAiCompatibleChatCompletionRequest> requests() {
            return requests;
        }

        OpenAiCompatibleChatCompletionRequest singleRequest() {
            assertThat(requests).hasSize(1);
            return requests.getFirst();
        }
    }

    private static final class ThrowingClient implements OpenAiCompatibleLlmClient {

        private final RuntimeException exception;

        private ThrowingClient(RuntimeException exception) {
            this.exception = exception;
        }

        @Override
        public OpenAiCompatibleClientResponse complete(OpenAiCompatibleChatCompletionRequest request) {
            throw exception;
        }
    }

    private static final class SequencedClient implements OpenAiCompatibleLlmClient {

        private final List<OpenAiCompatibleClientResponse> responses;
        private final List<OpenAiCompatibleChatCompletionRequest> requests = new ArrayList<>();

        private SequencedClient(OpenAiCompatibleClientResponse... responses) {
            this.responses = List.of(responses);
        }

        @Override
        public OpenAiCompatibleClientResponse complete(OpenAiCompatibleChatCompletionRequest request) {
            requests.add(request);
            return responses.get(Math.min(requests.size() - 1, responses.size() - 1));
        }

        List<OpenAiCompatibleChatCompletionRequest> requests() {
            return requests;
        }
    }

    private static final class CapturingHttpTransport implements OpenAiCompatibleHttpTransport {

        private final OpenAiCompatibleClientResponse response;
        private OpenAiCompatibleChatCompletionRequest request;

        private CapturingHttpTransport(OpenAiCompatibleClientResponse response) {
            this.response = response;
        }

        @Override
        public OpenAiCompatibleClientResponse send(OpenAiCompatibleChatCompletionRequest request) {
            this.request = request;
            return response;
        }

        OpenAiCompatibleChatCompletionRequest request() {
            return request;
        }
    }
}
