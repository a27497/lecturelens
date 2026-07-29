package com.example.courselingo.vision.adaptive;

import java.util.ArrayList;
import java.util.List;

/** Removes only temporally close images whose 64-bit perceptual hashes are near-identical. */
public final class PerceptualHashDeduplicator {

    public record HashedFrame<T>(T value, double timestampSeconds, long perceptualHash) {

        public HashedFrame {
            if (!Double.isFinite(timestampSeconds) || timestampSeconds < 0.0) {
                throw new IllegalArgumentException("timestampSeconds must be finite and non-negative");
            }
        }
    }

    private final int maximumHammingDistance;
    private final double maximumTimeDistanceSeconds;

    public PerceptualHashDeduplicator(int maximumHammingDistance) {
        this(maximumHammingDistance, 120.0);
    }

    public PerceptualHashDeduplicator(int maximumHammingDistance, double maximumTimeDistanceSeconds) {
        if (maximumHammingDistance < 0 || maximumHammingDistance > 64) {
            throw new IllegalArgumentException("maximumHammingDistance must be between 0 and 64");
        }
        if (!Double.isFinite(maximumTimeDistanceSeconds) || maximumTimeDistanceSeconds < 0.0) {
            throw new IllegalArgumentException("maximumTimeDistanceSeconds must be non-negative");
        }
        this.maximumHammingDistance = maximumHammingDistance;
        this.maximumTimeDistanceSeconds = maximumTimeDistanceSeconds;
    }

    public static int hammingDistance(long first, long second) {
        return Long.bitCount(first ^ second);
    }

    public boolean isNearDuplicate(long first, long second) {
        return hammingDistance(first, second) <= maximumHammingDistance;
    }

    public boolean isDuplicate(long first, double firstTimestamp, long second, double secondTimestamp) {
        return Math.abs(secondTimestamp - firstTimestamp) <= maximumTimeDistanceSeconds
            && isNearDuplicate(first, second);
    }

    public <T> List<HashedFrame<T>> deduplicate(List<HashedFrame<T>> frames) {
        if (frames == null || frames.isEmpty()) {
            return List.of();
        }
        List<HashedFrame<T>> kept = new ArrayList<>();
        for (HashedFrame<T> candidate : frames) {
            if (candidate == null) {
                continue;
            }
            boolean duplicate = kept.stream().anyMatch(previous -> isDuplicate(
                previous.perceptualHash(), previous.timestampSeconds(),
                candidate.perceptualHash(), candidate.timestampSeconds()
            ));
            if (!duplicate) {
                kept.add(candidate);
            }
        }
        return List.copyOf(kept);
    }
}
