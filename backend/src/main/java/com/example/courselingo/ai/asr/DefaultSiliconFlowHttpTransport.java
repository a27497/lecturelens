package com.example.courselingo.ai.asr;

import java.io.IOException;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.time.Duration;

final class DefaultSiliconFlowHttpTransport implements SiliconFlowHttpTransport {

    private final HttpClient httpClient;

    DefaultSiliconFlowHttpTransport(Duration connectTimeout) {
        this.httpClient = HttpClient.newBuilder()
            .connectTimeout(connectTimeout)
            .build();
    }

    @Override
    public SiliconFlowAsrClientResponse send(SiliconFlowHttpRequest request) {
        HttpRequest.Builder builder = HttpRequest.newBuilder(request.uri())
            .timeout(request.timeout())
            .header("Content-Type", request.contentType())
            .POST(HttpRequest.BodyPublishers.ofByteArray(request.body()));
        request.headers().forEach(builder::header);
        try {
            HttpResponse<String> response = httpClient.send(builder.build(), HttpResponse.BodyHandlers.ofString());
            return new SiliconFlowAsrClientResponse(
                response.statusCode(),
                response.body(),
                response.headers().map(),
                Duration.ZERO
            );
        } catch (HttpTimeoutException exception) {
            throw new SiliconFlowAsrException("SiliconFlow ASR request timed out", true, exception);
        } catch (IOException exception) {
            throw new SiliconFlowAsrException("SiliconFlow ASR network call failed", true, exception);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new SiliconFlowAsrException("SiliconFlow ASR network call was interrupted", true, exception);
        }
    }
}
