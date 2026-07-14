package com.example.courselingo.common.tracing;

public final class TracingScope implements AutoCloseable {

    private final TracingContext previousContext;
    private boolean closed;

    TracingScope(TracingContext previousContext) {
        this.previousContext = previousContext;
    }

    @Override
    public void close() {
        if (closed) {
            return;
        }
        closed = true;
        TracingContextHolder.restore(previousContext);
    }
}
