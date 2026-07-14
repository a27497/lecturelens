package com.example.courselingo.mq;

import com.example.courselingo.common.error.ErrorCode;

public record ConsumerProcessResult(
    Status status,
    ErrorCode errorCode,
    String errorMessage
) {

    public static final ConsumerProcessResult SUCCESS = new ConsumerProcessResult(Status.SUCCESS, null, null);
    public static final ConsumerProcessResult FAIL = new ConsumerProcessResult(Status.FAIL, null, null);
    public static final ConsumerProcessResult RETRY = new ConsumerProcessResult(Status.RETRY, null, null);

    public static ConsumerProcessResult fail(ErrorCode errorCode, String message) {
        return new ConsumerProcessResult(Status.FAIL, errorCode, message);
    }

    public static ConsumerProcessResult retry(ErrorCode errorCode, String message) {
        return new ConsumerProcessResult(Status.RETRY, errorCode, message);
    }

    public enum Status {
        SUCCESS,
        FAIL,
        RETRY
    }
}
