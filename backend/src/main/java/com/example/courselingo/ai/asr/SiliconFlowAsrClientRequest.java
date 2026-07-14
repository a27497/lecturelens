package com.example.courselingo.ai.asr;

import java.net.URI;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Map;

public record SiliconFlowAsrClientRequest(
    URI uri,
    Map<String, String> headers,
    Path audioFile,
    String fileFieldName,
    Map<String, String> formFields,
    Duration timeout
) {

    public SiliconFlowAsrClientRequest {
        headers = headers == null ? Map.of() : Map.copyOf(headers);
        formFields = formFields == null ? Map.of() : Map.copyOf(formFields);
    }
}
