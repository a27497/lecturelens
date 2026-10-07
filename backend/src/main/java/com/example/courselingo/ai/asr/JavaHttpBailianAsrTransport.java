package com.example.courselingo.ai.asr;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.time.Duration;

final class JavaHttpBailianAsrTransport implements BailianAsrTransport {
    private final HttpClient client;

    JavaHttpBailianAsrTransport(Duration connectTimeout) {
        this(HttpClient.newBuilder().connectTimeout(connectTimeout)
            .followRedirects(HttpClient.Redirect.NEVER).build());
    }

    JavaHttpBailianAsrTransport(HttpClient client) { this.client = client; }

    @Override
    public Response send(URI endpoint, String credential, byte[] body, Duration timeout) {
        try {
            HttpRequest request = HttpRequest.newBuilder(endpoint).timeout(timeout)
                .header("Authorization", "Bearer " + credential)
                .header("Content-Type", "application/json")
                .header("X-DashScope-SSE", "disable")
                .POST(HttpRequest.BodyPublishers.ofByteArray(body)).build();
            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
            return new Response(response.statusCode(), response.body());
        } catch (HttpTimeoutException exception) {
            throw new AsrProviderException("Bailian ASR request timed out", true);
        } catch (IOException exception) {
            throw new AsrProviderException("Bailian ASR network call failed", true);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new AsrProviderException("Bailian ASR request interrupted", true);
        } catch (RuntimeException exception) {
            // Header/URI validation failures must not expose the rejected value.
            throw new AsrProviderException("Bailian ASR transport configuration is invalid", false);
        }
    }
}
