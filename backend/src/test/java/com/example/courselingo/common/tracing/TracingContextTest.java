package com.example.courselingo.common.tracing;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.courselingo.common.logging.StructuredLogFields;
import java.util.concurrent.Callable;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;

class TracingContextTest {

    @AfterEach
    void clearTracing() {
        TracingContextHolder.clear();
        MDC.clear();
    }

    @Test
    void generatesTraceAndRequestIdsWhenHeadersAreMissing() {
        TracingContext context = TracingContextFactory.fromHeaders(null, null);

        assertThat(context.traceId()).isNotBlank();
        assertThat(context.requestId()).isNotBlank();
        assertThat(context.traceId()).isNotEqualTo(context.requestId());
    }

    @Test
    void reusesSafeHeaderIdsAndReplacesUnsafeHeaderIds() {
        TracingContext safe = TracingContextFactory.fromHeaders("trace-abc_123", "req.abc:123");
        TracingContext unsafe = TracingContextFactory.fromHeaders(
            "../" + "x".repeat(140),
            "Authorization=Bearer raw-token"
        );

        assertThat(safe.traceId()).isEqualTo("trace-abc_123");
        assertThat(safe.requestId()).isEqualTo("req.abc:123");
        assertThat(unsafe.traceId()).isNotEqualTo("../" + "x".repeat(140));
        assertThat(unsafe.requestId()).isNotEqualTo("Authorization=Bearer raw-token");
        assertThat(unsafe.traceId()).doesNotContain("..");
        assertThat(unsafe.requestId()).doesNotContainIgnoringCase("authorization");
        assertThat(unsafe.requestId()).doesNotContainIgnoringCase("token");
    }

    @Test
    void scopeWritesContextIntoMdcAndClearsItAfterClose() {
        TracingContext context = new TracingContext("trace_1", "req_1");

        try (TracingScope ignored = TracingContextHolder.open(context)) {
            assertThat(TracingContextHolder.current()).contains(context);
            assertThat(MDC.get(StructuredLogFields.TRACE_ID)).isEqualTo("trace_1");
            assertThat(MDC.get(StructuredLogFields.REQUEST_ID)).isEqualTo("req_1");
        }

        assertThat(TracingContextHolder.current()).isEmpty();
        assertThat(MDC.get(StructuredLogFields.TRACE_ID)).isNull();
        assertThat(MDC.get(StructuredLogFields.REQUEST_ID)).isNull();
    }

    @Test
    void scopeRestoresPreviousContextAfterNestedClose() {
        TracingContext parent = new TracingContext("trace_parent", "req_parent");
        TracingContext child = new TracingContext("trace_child", "req_child");

        try (TracingScope ignored = TracingContextHolder.open(parent)) {
            try (TracingScope nested = TracingContextHolder.open(child)) {
                assertThat(TracingContextHolder.current()).contains(child);
            }

            assertThat(TracingContextHolder.current()).contains(parent);
            assertThat(MDC.get(StructuredLogFields.TRACE_ID)).isEqualTo("trace_parent");
            assertThat(MDC.get(StructuredLogFields.REQUEST_ID)).isEqualTo("req_parent");
        }
    }

    @Test
    void wrapsCallableWithCapturedContextWithoutLeakingAfterExecution() throws Exception {
        TracingContext context = new TracingContext("trace_worker", "req_worker");
        Callable<String> callable;

        try (TracingScope ignored = TracingContextHolder.open(context)) {
            callable = TracingContextHolder.wrapCurrent(() ->
                MDC.get(StructuredLogFields.TRACE_ID) + "/" + MDC.get(StructuredLogFields.REQUEST_ID)
            );
        }

        assertThat(callable.call()).isEqualTo("trace_worker/req_worker");
        assertThat(TracingContextHolder.current()).isEmpty();
        assertThat(MDC.get(StructuredLogFields.TRACE_ID)).isNull();
        assertThat(MDC.get(StructuredLogFields.REQUEST_ID)).isNull();
    }
}
