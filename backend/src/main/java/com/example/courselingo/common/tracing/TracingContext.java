package com.example.courselingo.common.tracing;

public record TracingContext(
    String traceId,
    String requestId
) {
}
