package com.example.courselingo.task.ratelimit;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;

public class NoopAnalysisRateLimitService implements AnalysisRateLimitService {

    private static final AnalysisRateLimitResult ALLOWED = AnalysisRateLimitResult.allowed(0, 0);

    @Override
    public AnalysisRateLimitResult checkAndConsume(Long userId) {
        if (userId == null || userId <= 0) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, "Invalid userId");
        }
        return ALLOWED;
    }
}
