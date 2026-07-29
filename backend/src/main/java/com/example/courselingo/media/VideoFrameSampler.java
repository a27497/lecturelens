package com.example.courselingo.media;

import java.nio.file.Path;
import java.time.Duration;

public interface VideoFrameSampler {

    Path sample(Path sourceVideo, long timestampMillis, Path outputImage, int maxWidth, Duration timeout);
}
