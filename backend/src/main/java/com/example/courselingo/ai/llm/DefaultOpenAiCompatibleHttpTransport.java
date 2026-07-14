package com.example.courselingo.ai.llm;

import java.io.IOException;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

final class DefaultOpenAiCompatibleHttpTransport implements OpenAiCompatibleHttpTransport {

    private final HttpClient httpClient;

    DefaultOpenAiCompatibleHttpTransport(Duration connectTimeout) {
        this.httpClient = HttpClient.newBuilder()
            .connectTimeout(connectTimeout)
            .build();
    }

    @Override
    public OpenAiCompatibleClientResponse send(OpenAiCompatibleChatCompletionRequest request) {
        long startedNanos = System.nanoTime();
        HttpRequest.Builder builder = HttpRequest.newBuilder(request.uri())
            .timeout(request.timeout())
            .header("Content-Type", request.contentType())
            .POST(HttpRequest.BodyPublishers.ofString(request.body(), StandardCharsets.UTF_8));
        request.headers().forEach(builder::header);
        try {
            HttpResponse<String> response = httpClient.send(builder.build(), HttpResponse.BodyHandlers.ofString());
            return new OpenAiCompatibleClientResponse(
                response.statusCode(),
                response.body(),
                response.headers().map(),
                Duration.ofNanos(System.nanoTime() - startedNanos)
            );
        } catch (HttpTimeoutException exception) {
            throw new OpenAiCompatibleLlmException(
                "OpenAI-compatible LLM request timed out",
                LlmProviderFailureType.TIMEOUT,
                true,
                null,
                exception,
                OpenAiCompatibleLlmProvider.PROVIDER_NAME,
                null,
                request.uri().toString(),
                Duration.ofNanos(System.nanoTime() - startedNanos).toMillis(),
                null,
                exception.getClass().getName(),
                exception.getMessage()
            );
        } catch (IOException exception) {
            throw new OpenAiCompatibleLlmException(
                "OpenAI-compatible LLM network call failed",
                LlmProviderFailureType.CONNECTION_ERROR,
                true,
                null,
                exception,
                OpenAiCompatibleLlmProvider.PROVIDER_NAME,
                null,
                request.uri().toString(),
                Duration.ofNanos(System.nanoTime() - startedNanos).toMillis(),
                null,
                exception.getClass().getName(),
                exception.getMessage()
            );
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new OpenAiCompatibleLlmException(
                "OpenAI-compatible LLM network call was interrupted",
                LlmProviderFailureType.CONNECTION_ERROR,
                true,
                null,
                exception,
                OpenAiCompatibleLlmProvider.PROVIDER_NAME,
                null,
                request.uri().toString(),
                Duration.ofNanos(System.nanoTime() - startedNanos).toMillis(),
                null,
                exception.getClass().getName(),
                exception.getMessage()
            );
        }
    }
}
