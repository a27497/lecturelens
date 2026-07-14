package com.example.courselingo.common.response;

import com.example.courselingo.common.web.TraceIdUtils;
import com.fasterxml.jackson.annotation.JsonInclude;
import java.time.Instant;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record ApiResponse<T>(
    String code,
    String message,
    T data,
    Instant timestamp,
    String traceId
) {

    public static final String SUCCESS_CODE = "0";
    public static final String SUCCESS_MESSAGE = "ok";

    public static <T> ApiResponse<T> success(T data) {
        return new ApiResponse<>(SUCCESS_CODE, SUCCESS_MESSAGE, data, Instant.now(), TraceIdUtils.currentTraceId());
    }

    public static ApiResponse<Void> success() {
        return new ApiResponse<>(SUCCESS_CODE, SUCCESS_MESSAGE, null, Instant.now(), TraceIdUtils.currentTraceId());
    }

    public static ApiResponse<Void> failure(String code, String message) {
        return failure(code, message, null);
    }

    public static <T> ApiResponse<T> failure(String code, String message, T data) {
        return new ApiResponse<>(code, message, data, Instant.now(), TraceIdUtils.currentTraceId());
    }
}
