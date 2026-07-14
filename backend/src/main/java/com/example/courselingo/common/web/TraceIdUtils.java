package com.example.courselingo.common.web;

import com.example.courselingo.common.tracing.TracingContextFactory;
import com.example.courselingo.common.tracing.TracingContextHolder;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

public final class TraceIdUtils {

    public static final String TRACE_ID_HEADER = "X-Trace-Id";

    private TraceIdUtils() {
    }

    public static String currentTraceId() {
        return TracingContextHolder.current()
            .map(context -> context.traceId())
            .orElseGet(TraceIdUtils::requestOrNewTraceId);
    }

    private static String requestOrNewTraceId() {
        if (RequestContextHolder.getRequestAttributes() instanceof ServletRequestAttributes attributes) {
            return resolveTraceId(attributes.getRequest());
        }
        return TracingContextFactory.create().traceId();
    }

    public static String resolveTraceId(HttpServletRequest request) {
        return TracingContextFactory.resolveId(request.getHeader(TRACE_ID_HEADER));
    }
}
