package com.example.courselingo.qa.service;

public record CourseQaRateLimitResult(
    boolean allowed,
    int limit,
    int remaining,
    long retryAfterSeconds
) {

    public static CourseQaRateLimitResult allowed(int limit, int remaining) {
        return new CourseQaRateLimitResult(true, limit, Math.max(remaining, 0), 0);
    }

    public static CourseQaRateLimitResult blocked(int limit, long retryAfterSeconds) {
        return new CourseQaRateLimitResult(false, limit, 0, retryAfterSeconds);
    }
}
