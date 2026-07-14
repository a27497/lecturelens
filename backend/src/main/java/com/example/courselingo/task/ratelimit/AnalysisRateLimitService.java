package com.example.courselingo.task.ratelimit;

public interface AnalysisRateLimitService {

    AnalysisRateLimitResult checkAndConsume(Long userId);
}
