package com.example.courselingo.media;

import java.nio.file.Path;

public record AudioChunk(
    int index,
    long offsetMillis,
    Path audioFile,
    long endMillis,
    com.example.courselingo.ai.asr.TranscriptTimingSource timingSource,
    String timingReason
) {

    public AudioChunk(int index,long offsetMillis,Path audioFile) {
        this(index,offsetMillis,audioFile,-1,com.example.courselingo.ai.asr.TranscriptTimingSource.ESTIMATED,null);
    }

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
        if (endMillis != -1 && endMillis <= offsetMillis) throw new IllegalArgumentException("Audio clip end must follow its start");
    }
}
