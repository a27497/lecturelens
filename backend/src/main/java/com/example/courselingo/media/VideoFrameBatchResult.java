package com.example.courselingo.media;

import java.util.List;

/** Low-cardinality batch sampling result; individual failures do not discard successful outputs. */
public record VideoFrameBatchResult(
    int requestedCount,
    List<VideoFrameSample> samples,
    int failedCount,
    int ffmpegProcessCount
) {

    public VideoFrameBatchResult {
        requestedCount = Math.max(0, requestedCount);
        samples = samples == null ? List.of() : List.copyOf(samples);
        failedCount = Math.max(0, failedCount);
        ffmpegProcessCount = Math.max(0, ffmpegProcessCount);
    }

    public int succeededCount() {
        return samples.size();
    }
}
