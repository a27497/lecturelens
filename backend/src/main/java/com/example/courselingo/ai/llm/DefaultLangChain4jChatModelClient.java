package com.example.courselingo.ai.llm;

import dev.langchain4j.http.client.jdk.JdkHttpClientBuilder;
import dev.langchain4j.model.chat.ChatModel;
import dev.langchain4j.model.chat.request.ChatRequest;
import dev.langchain4j.model.chat.response.ChatResponse;
import dev.langchain4j.model.openai.OpenAiChatModel;
import java.time.Duration;

public class DefaultLangChain4jChatModelClient implements LangChain4jChatModelClient {

    private final LangChain4jLlmProperties properties;

    public DefaultLangChain4jChatModelClient(LangChain4jLlmProperties properties) {
        this.properties = properties;
    }

    @Override
    public LangChain4jClientResponse complete(LangChain4jClientRequest request) {
        ChatModel chatModel = OpenAiChatModel.builder()
            .baseUrl(properties.getBaseUrl().strip())
            .apiKey(properties.getApiKey().strip())
            .modelName(request.model())
            .temperature(request.temperature())
            .maxTokens(request.maxTokens())
            .timeout(request.timeout())
            .httpClientBuilder(new JdkHttpClientBuilder()
                .connectTimeout(properties.getConnectTimeout())
                .readTimeout(request.timeout()))
            .logRequests(false)
            .logResponses(false)
            .build();
        ChatRequest chatRequest = ChatRequest.builder()
            .messages(request.messages())
            .modelName(request.model())
            .temperature(request.temperature())
            .maxOutputTokens(request.maxTokens())
            .build();

        long started = System.nanoTime();
        try {
            ChatResponse response = chatModel.chat(chatRequest);
            return new LangChain4jClientResponse(response, Duration.ofNanos(System.nanoTime() - started));
        } catch (RuntimeException exception) {
            throw mapRuntimeException(exception);
        }
    }

    private static LangChain4jLlmException mapRuntimeException(RuntimeException exception) {
        Integer statusCode = statusCodeFromMessage(exception.getMessage());
        boolean retryable = statusCode == null || isRetryableStatus(statusCode);
        return new LangChain4jLlmException("LangChain4j LLM request failed: " + exception.getMessage(), retryable, statusCode, exception);
    }

    private static Integer statusCodeFromMessage(String message) {
        if (message == null) {
            return null;
        }
        for (int statusCode : new int[] {400, 401, 403, 404, 408, 429, 500, 502, 503, 504}) {
            if (message.contains(String.valueOf(statusCode))) {
                return statusCode;
            }
        }
        return null;
    }

    private static boolean isRetryableStatus(int statusCode) {
        return statusCode == 408 || statusCode == 429 || statusCode == 500 || statusCode == 502
            || statusCode == 503 || statusCode == 504;
    }
}
