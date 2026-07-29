package com.example.courselingo.vision.keyframe;

public record VideoKeyframeScanResult(
    int savedKeyframeCount,
    int candidateTimestampCount,
    int extractedSampleCount,
    int blurredRejectedCount,
    int blackRejectedCount,
    int duplicateRejectedCount,
    int ocrSucceededCount,
    int ocrEmptyCount,
    int ocrFailedCount,
    long durationMillis,
    int sampleBatchCount,
    int ffmpegProcessCount,
    int sampleRequestCount,
    int sampleSucceededCount,
    int sampleFailedCount,
    int stableFrameCount,
    int preOcrRejectedCount,
    int ocrPlannedCount,
    int ocrAttemptedCount,
    int finalKeyframeCount,
    int vlmPlannedCount
) {

    public VideoKeyframeScanResult(int savedKeyframeCount) {
        this(savedKeyframeCount, 0, 0, 0, 0, 0, 0, 0, 0, 0L, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            savedKeyframeCount, savedKeyframeCount);
    }
}
