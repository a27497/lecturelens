package com.example.courselingo.ai.asr;

import java.net.URI;
import java.time.Duration;
import java.util.Map;

public record SiliconFlowHttpRequest(
    URI uri,
    Map<String, String> headers,
    String contentType,
    byte[] body,
    Duration timeout
) {

    public SiliconFlowHttpRequest {
        headers = headers == null ? Map.of() : Map.copyOf(headers);
        body = body == null ? new byte[0] : body.clone();
    }
}
