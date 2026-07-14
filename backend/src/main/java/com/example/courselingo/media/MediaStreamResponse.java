package com.example.courselingo.media;

import java.io.InputStream;

public record MediaStreamResponse(
    int status,
    String contentType,
    long contentLength,
    String contentRange,
    InputStream inputStream
) {
}
