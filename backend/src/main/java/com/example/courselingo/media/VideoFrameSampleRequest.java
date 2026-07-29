package com.example.courselingo.media;

import java.nio.file.Path;
import java.util.Objects;

/** One exact video timestamp and its caller-owned output path. */
public record VideoFrameSampleRequest(long timestampMillis, Path outputImage) {

    public VideoFrameSampleRequest {
        timestampMillis = Math.max(0L, timestampMillis);
        Objects.requireNonNull(outputImage, "outputImage");
    }
}
