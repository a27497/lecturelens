package com.example.courselingo.media;

import java.nio.file.Path;
import java.time.Duration;

public record VideoFrameExtractionRequest(
    Path inputVideo,
    Path outputDirectory,
    int scanIntervalSeconds,
    int thumbnailWidth,
    String outputFormat,
    int maxFrames,
    Duration timeout
) {
}
