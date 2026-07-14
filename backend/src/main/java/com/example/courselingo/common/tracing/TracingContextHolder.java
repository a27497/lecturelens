package com.example.courselingo.common.tracing;

import com.example.courselingo.common.logging.StructuredLogFields;
import java.util.Optional;
import java.util.concurrent.Callable;
import org.slf4j.MDC;

public final class TracingContextHolder {

    private static final ThreadLocal<TracingContext> CURRENT = new ThreadLocal<>();

    private TracingContextHolder() {
    }

    public static Optional<TracingContext> current() {
        return Optional.ofNullable(CURRENT.get());
    }

    public static TracingContext currentOrCreate() {
        return current().orElseGet(TracingContextFactory::create);
    }

    public static TracingScope open(TracingContext context) {
        if (context == null) {
            throw new IllegalArgumentException("Tracing context is required");
        }
        TracingContext previous = CURRENT.get();
        set(context);
        return new TracingScope(previous);
    }

    public static <T> Callable<T> wrapCurrent(Callable<T> callable) {
        TracingContext captured = CURRENT.get();
        return () -> {
            try (TracingScope ignored = openNullable(captured)) {
                return callable.call();
            }
        };
    }

    public static Runnable wrapCurrent(Runnable runnable) {
        TracingContext captured = CURRENT.get();
        return () -> {
            try (TracingScope ignored = openNullable(captured)) {
                runnable.run();
            }
        };
    }

    public static void clear() {
        CURRENT.remove();
        MDC.remove(StructuredLogFields.TRACE_ID);
        MDC.remove(StructuredLogFields.REQUEST_ID);
    }

    static void restore(TracingContext context) {
        if (context == null) {
            clear();
            return;
        }
        set(context);
    }

    private static TracingScope openNullable(TracingContext context) {
        TracingContext previous = CURRENT.get();
        if (context == null) {
            clear();
        } else {
            set(context);
        }
        return new TracingScope(previous);
    }

    private static void set(TracingContext context) {
        CURRENT.set(context);
        MDC.put(StructuredLogFields.TRACE_ID, context.traceId());
        MDC.put(StructuredLogFields.REQUEST_ID, context.requestId());
    }
}
