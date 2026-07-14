package com.example.courselingo.common.web;

import com.example.courselingo.common.logging.SafeLogSanitizer;
import com.example.courselingo.common.logging.StructuredLogFields;
import com.example.courselingo.common.tracing.TracingContext;
import com.example.courselingo.common.tracing.TracingContextFactory;
import com.example.courselingo.common.tracing.TracingContextHolder;
import com.example.courselingo.common.tracing.TracingScope;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class StructuredRequestLoggingFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger(StructuredRequestLoggingFilter.class);

    @Override
    protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain filterChain
    ) throws ServletException, IOException {
        long startedAt = System.nanoTime();
        TracingContext context = TracingContextFactory.fromHeaders(
            request.getHeader(StructuredLogFields.TRACE_ID_HEADER),
            request.getHeader(StructuredLogFields.REQUEST_ID_HEADER)
        );
        response.setHeader(StructuredLogFields.REQUEST_ID_HEADER, context.requestId());
        response.setHeader(StructuredLogFields.TRACE_ID_HEADER, context.traceId());
        try (TracingScope ignored = TracingContextHolder.open(context)) {
            try {
                filterChain.doFilter(request, response);
            } finally {
                logCompletion(request, response, startedAt);
            }
        }
    }

    private static void logCompletion(HttpServletRequest request, HttpServletResponse response, long startedAt) {
        long durationMs = (System.nanoTime() - startedAt) / 1_000_000;
        int status = response.getStatus();
        String outcome = status >= 500 ? "error" : status >= 400 ? "rejected" : "success";
        log.info(
            "event=http_request_completed method={} path={} status={} durationMs={} clientIp={} userAgentHash={} outcome={}",
            SafeLogSanitizer.sanitize(request.getMethod()),
            SafeLogSanitizer.sanitize(request.getRequestURI()),
            status,
            durationMs,
            SafeLogSanitizer.sanitize(request.getRemoteAddr()),
            hashUserAgent(request.getHeader("User-Agent")),
            outcome
        );
    }

    private static String hashUserAgent(String userAgent) {
        if (userAgent == null || userAgent.isBlank()) {
            return "";
        }
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(userAgent.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest, 0, 8);
        } catch (NoSuchAlgorithmException exception) {
            return "unavailable";
        }
    }
}
