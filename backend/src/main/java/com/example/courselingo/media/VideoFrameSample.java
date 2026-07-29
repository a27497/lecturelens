package com.example.courselingo.media;

import java.nio.file.Path;
import java.util.Objects;

/** A successfully materialized sample from a batch request. */
public record VideoFrameSample(long timestampMillis, Path imagePath) {

    public VideoFrameSample {
        timestampMillis = Math.max(0L, timestampMillis);
        Objects.requireNonNull(imagePath, "imagePath");
    }
}
