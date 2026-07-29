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
    long durationMillis
) {

    public VideoKeyframeScanResult(int savedKeyframeCount) {
        this(savedKeyframeCount, 0, 0, 0, 0, 0, 0, 0, 0, 0L);
    }
}
