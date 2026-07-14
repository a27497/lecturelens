package com.example.courselingo.common.web;

import static org.assertj.core.api.Assertions.assertThat;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import com.example.courselingo.common.logging.StructuredLogFields;
import com.example.courselingo.common.tracing.TracingContextHolder;
import jakarta.servlet.ServletException;
import java.io.IOException;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

class StructuredRequestLoggingFilterTest {

    private final Logger logger = (Logger) LoggerFactory.getLogger(StructuredRequestLoggingFilter.class);

    @AfterEach
    void clearMdc() {
        TracingContextHolder.clear();
        MDC.clear();
    }

    @Test
    void generatesRequestAndTraceIdsAndClearsMdcAfterRequest() throws Exception {
        StructuredRequestLoggingFilter filter = new StructuredRequestLoggingFilter();
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/tasks/task_1");
        MockHttpServletResponse response = new MockHttpServletResponse();
        AtomicReference<String> requestIdDuringChain = new AtomicReference<>();
        AtomicReference<String> traceIdDuringChain = new AtomicReference<>();
        MockFilterChain chain = new CapturingFilterChain(requestIdDuringChain, traceIdDuringChain);

        filter.doFilter(request, response, chain);

        assertThat(requestIdDuringChain.get()).isNotBlank();
        assertThat(traceIdDuringChain.get()).isNotBlank();
        assertThat(response.getHeader(StructuredLogFields.REQUEST_ID_HEADER)).isEqualTo(requestIdDuringChain.get());
        assertThat(TracingContextHolder.current()).isEmpty();
        assertThat(MDC.get(StructuredLogFields.REQUEST_ID)).isNull();
        assertThat(MDC.get(StructuredLogFields.TRACE_ID)).isNull();
    }

    @Test
    void reusesValidRequestAndTraceIdsAndReplacesInvalidIds() throws Exception {
        StructuredRequestLoggingFilter filter = new StructuredRequestLoggingFilter();

        MockHttpServletResponse validResponse = new MockHttpServletResponse();
        MockHttpServletRequest validRequest = new MockHttpServletRequest("GET", "/api/tasks");
        validRequest.addHeader(StructuredLogFields.REQUEST_ID_HEADER, "req-abc_123");
        validRequest.addHeader(StructuredLogFields.TRACE_ID_HEADER, "trace-abc_123");
        filter.doFilter(validRequest, validResponse, new MockFilterChain());

        MockHttpServletResponse invalidResponse = new MockHttpServletResponse();
        MockHttpServletRequest invalidRequest = new MockHttpServletRequest("GET", "/api/tasks");
        invalidRequest.addHeader(StructuredLogFields.REQUEST_ID_HEADER, "../" + "x".repeat(140));
        invalidRequest.addHeader(StructuredLogFields.TRACE_ID_HEADER, "Authorization=Bearer raw-token");
        filter.doFilter(invalidRequest, invalidResponse, new MockFilterChain());

        assertThat(validResponse.getHeader(StructuredLogFields.REQUEST_ID_HEADER)).isEqualTo("req-abc_123");
        assertThat(validResponse.getHeader(StructuredLogFields.TRACE_ID_HEADER)).isEqualTo("trace-abc_123");
        assertThat(invalidResponse.getHeader(StructuredLogFields.REQUEST_ID_HEADER))
            .isNotBlank()
            .isNotEqualTo("../" + "x".repeat(140));
        assertThat(invalidResponse.getHeader(StructuredLogFields.TRACE_ID_HEADER))
            .isNotBlank()
            .doesNotContainIgnoringCase("authorization")
            .doesNotContainIgnoringCase("token");
    }

    @Test
    void completionLogDoesNotContainSensitiveHeadersQueryOrBody() throws Exception {
        StructuredRequestLoggingFilter filter = new StructuredRequestLoggingFilter();
        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);
        try {
            MockHttpServletRequest request = new MockHttpServletRequest("POST", "/api/tasks");
            request.setQueryString("token=secret&api_key=key");
            request.addHeader("Authorization", "Bearer access-token");
            request.addHeader("Cookie", "SESSION=abc");
            request.addHeader(StructuredLogFields.TRACE_ID_HEADER, "Authorization=Bearer raw-token");
            request.setContent("secret request body".getBytes());
            MockHttpServletResponse response = new MockHttpServletResponse();

            filter.doFilter(request, response, new MockFilterChain());

            assertThat(appender.list).hasSize(1);
            ILoggingEvent event = appender.list.getFirst();
            assertThat(event.getFormattedMessage())
                .contains("event=http_request_completed")
                .doesNotContain("Authorization")
                .doesNotContain("access-token")
                .doesNotContain("Cookie")
                .doesNotContain("SESSION=abc")
                .doesNotContain("secret request body")
                .doesNotContain("token=secret")
                .doesNotContain("api_key=key");
            assertThat(event.getMDCPropertyMap().get(StructuredLogFields.TRACE_ID))
                .doesNotContainIgnoringCase("authorization")
                .doesNotContainIgnoringCase("token");
            assertThat(event.getMDCPropertyMap()).containsKeys(
                StructuredLogFields.TRACE_ID,
                StructuredLogFields.REQUEST_ID
            );
        } finally {
            logger.detachAppender(appender);
        }
    }

    private static final class CapturingFilterChain extends MockFilterChain {

        private final AtomicReference<String> requestId;
        private final AtomicReference<String> traceId;

        private CapturingFilterChain(AtomicReference<String> requestId, AtomicReference<String> traceId) {
            this.requestId = requestId;
            this.traceId = traceId;
        }

        @Override
        public void doFilter(jakarta.servlet.ServletRequest request, jakarta.servlet.ServletResponse response)
            throws IOException, ServletException {
            requestId.set(MDC.get(StructuredLogFields.REQUEST_ID));
            traceId.set(MDC.get(StructuredLogFields.TRACE_ID));
            assertThat(TracingContextHolder.current()).isPresent();
            assertThat(TracingContextHolder.current().orElseThrow().requestId()).isEqualTo(requestId.get());
            assertThat(TracingContextHolder.current().orElseThrow().traceId()).isEqualTo(traceId.get());
            super.doFilter(request, response);
        }
    }
}
