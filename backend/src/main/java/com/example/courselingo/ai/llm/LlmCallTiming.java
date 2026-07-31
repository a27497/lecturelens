package com.example.courselingo.ai.llm;

import java.time.Duration;

public final class LlmCallTiming {

    private LlmCallTiming() {
    }

    public static long startedNanos() {
        return System.nanoTime();
    }

    public static Duration measuredDuration(long startedNanos, Duration providerDuration) {
        if (providerDuration != null && !providerDuration.isZero() && !providerDuration.isNegative()) {
            return providerDuration;
        }
        return Duration.ofNanos(Math.max(0L, System.nanoTime() - startedNanos));
    }
}
