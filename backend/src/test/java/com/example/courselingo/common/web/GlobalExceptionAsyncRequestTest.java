package com.example.courselingo.common.web;

import static org.assertj.core.api.Assertions.assertThatCode;

import org.junit.jupiter.api.Test;
import org.springframework.web.context.request.async.AsyncRequestNotUsableException;

class GlobalExceptionAsyncRequestTest {

    @Test
    void clientDisconnectHandlerDoesNotAttemptToWriteASecondResponse() {
        GlobalExceptionHandler handler = new GlobalExceptionHandler();

        assertThatCode(() -> handler.handleAsyncRequestNotUsable(
            new AsyncRequestNotUsableException("fictional client disconnected")
        )).doesNotThrowAnyException();
    }
}
