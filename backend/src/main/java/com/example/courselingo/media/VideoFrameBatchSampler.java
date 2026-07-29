package com.example.courselingo.media;

import java.nio.file.Path;
import java.time.Duration;
import java.util.List;

/** Samples a bounded group of exact timestamps with one underlying media operation where supported. */
public interface VideoFrameBatchSampler {

    VideoFrameBatchResult sample(
        Path sourceVideo,
        List<VideoFrameSampleRequest> requests,
        int maxWidth,
        Duration timeout
    );
}
