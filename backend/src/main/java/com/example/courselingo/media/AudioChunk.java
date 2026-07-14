package com.example.courselingo.media;

import java.nio.file.Path;

public record AudioChunk(
    int index,
    long offsetMillis,
    Path audioFile
) {

    public AudioChunk {
        if (index < 0) {
            throw new IllegalArgumentException("audio chunk index must not be negative");
        }
        if (offsetMillis < 0) {
            throw new IllegalArgumentException("audio chunk offset must not be negative");
        }
        if (audioFile == null) {
            throw new IllegalArgumentException("audio chunk file is required");
        }
    }
}
