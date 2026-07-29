package com.example.courselingo.media;

import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

/** Compatibility adapter for tests and integrations that still provide only the single-frame API. */
public final class SingleFrameVideoFrameBatchSampler implements VideoFrameBatchSampler {

    private final VideoFrameSampler delegate;

    public SingleFrameVideoFrameBatchSampler(VideoFrameSampler delegate) {
        this.delegate = delegate;
    }

    @Override
    public VideoFrameBatchResult sample(
        Path sourceVideo,
        List<VideoFrameSampleRequest> requests,
        int maxWidth,
        Duration timeout
    ) {
        List<VideoFrameSampleRequest> safeRequests = requests == null ? List.of() : List.copyOf(requests);
        List<VideoFrameSample> samples = new ArrayList<>();
        int attempted = 0;
        for (VideoFrameSampleRequest request : safeRequests) {
            if (Thread.currentThread().isInterrupted()) {
                break;
            }
            attempted++;
            try {
                Path sampled = delegate.sample(
                    sourceVideo,
                    request.timestampMillis(),
                    request.outputImage(),
                    maxWidth,
                    timeout
                );
                samples.add(new VideoFrameSample(request.timestampMillis(), sampled));
            } catch (RuntimeException failure) {
                if (Thread.currentThread().isInterrupted()) {
                    throw failure;
                }
            }
        }
        return new VideoFrameBatchResult(
            safeRequests.size(),
            samples,
            safeRequests.size() - samples.size(),
            attempted
        );
    }
}
