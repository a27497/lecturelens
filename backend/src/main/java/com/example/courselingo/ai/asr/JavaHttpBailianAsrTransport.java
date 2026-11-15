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
    private com.example.courselingo.ai.llm.ModelCallObserver observer=com.example.courselingo.ai.llm.ModelCallObserver.NOOP;
    JavaHttpBailianAsrTransport observed(com.example.courselingo.ai.llm.ModelCallObserver value){observer=value;return this;}

    JavaHttpBailianAsrTransport(Duration connectTimeout) {
        this(HttpClient.newBuilder().connectTimeout(connectTimeout)
            .followRedirects(HttpClient.Redirect.NEVER).build());
    }

    JavaHttpBailianAsrTransport(HttpClient client) { this.client = client; }

    @Override
    public Response send(URI endpoint, String credential, byte[] body, Duration timeout) {
        long[] retryAfterMillis={0};
        var result=com.example.courselingo.ai.llm.ObservedModelCall.execute(observer,endpoint,java.util.Map.of("Authorization","Bearer "+credential),body,true,()->{
            long started=System.nanoTime();var response=sendOnce(endpoint,credential,body,timeout);
            retryAfterMillis[0]=response.retryAfterMillis();
            return new com.example.courselingo.ai.llm.OpenAiCompatibleClientResponse(response.statusCode(),response.body(),java.util.Map.of(),Duration.ofNanos(System.nanoTime()-started));
        });
        return new Response(result.statusCode(),result.body(),retryAfterMillis[0]);
    }
    private Response sendOnce(URI endpoint,String credential,byte[] body,Duration timeout) {
        try {
            HttpRequest request = HttpRequest.newBuilder(endpoint).timeout(timeout)
                .header("Authorization", "Bearer " + credential)
                .header("Content-Type", "application/json")
                .header("X-DashScope-SSE", "disable")
                .POST(HttpRequest.BodyPublishers.ofByteArray(body)).build();
            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
            return new Response(response.statusCode(), response.body(),retryAfter(response.headers()==null?null:response.headers().firstValue("Retry-After").orElse(null)));
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
    private static long retryAfter(String value) {
        if(value==null)return 0;
        try {return Math.max(0,Math.min(300000,Math.multiplyExact(Long.parseLong(value.strip()),1000)));}
        catch(RuntimeException ignored) {
            try {return Math.max(0,Math.min(300000,java.time.Duration.between(java.time.Instant.now(),
                java.time.ZonedDateTime.parse(value,java.time.format.DateTimeFormatter.RFC_1123_DATE_TIME).toInstant()).toMillis()));}
            catch(RuntimeException invalid){return 0;}
        }
    }
}
