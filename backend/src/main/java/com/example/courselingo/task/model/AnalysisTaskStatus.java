package com.example.courselingo.task.model;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.util.Locale;

public enum AnalysisTaskStatus {
    CREATED,
    QUEUED,
    RUNNING,
    SUCCEEDED,
    FAILED,
    CANCELED,
    RETRYING;

    public static AnalysisTaskStatus fromDatabaseValue(String value) {
        if (value == null || value.isBlank()) {
            throw new BusinessException(ErrorCode.TASK_INVALID_STATUS);
        }
        try {
            return AnalysisTaskStatus.valueOf(value.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException ex) {
            throw new BusinessException(ErrorCode.TASK_INVALID_STATUS);
        }
    }
}
