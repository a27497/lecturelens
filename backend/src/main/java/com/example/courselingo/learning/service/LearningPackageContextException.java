package com.example.courselingo.learning.service;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;

/** Bounded origin survives task diagnostics without retaining provider bodies or causes. */
public final class LearningPackageContextException extends BusinessException {
    public enum Origin { LOCAL_PREFLIGHT, PROVIDER }
    private final Origin origin;

    LearningPackageContextException(Origin origin, String safeReason) {
        super(ErrorCode.LEARNING_PACKAGE_CONTEXT_LIMIT_EXCEEDED,
            "Learning package context limit exceeded;origin=" + origin + ";reason=" + safeReason);
        this.origin = origin;
    }

    public Origin origin() { return origin; }
}
