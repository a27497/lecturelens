package com.example.courselingo.media;

public record EmbeddedSubtitleFileResponse(
    byte[] bytes,
    String contentType,
    String filename
) {
}
