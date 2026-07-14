package com.example.courselingo.task.ratelimit;

public record AnalysisRateLimitResult(
    boolean allowed,
    int limit,
    int remaining,
    long retryAfterSeconds
) {

    public static AnalysisRateLimitResult allowed(int limit, int remaining) {
        return new AnalysisRateLimitResult(true, limit, Math.max(remaining, 0), 0);
    }

    public static AnalysisRateLimitResult blocked(int limit, long retryAfterSeconds) {
        return new AnalysisRateLimitResult(false, limit, 0, retryAfterSeconds);
    }
}
