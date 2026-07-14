package com.example.courselingo.mq;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoMoreInteractions;

import com.example.courselingo.task.runner.AnalysisTaskRunner;
import java.time.Instant;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class AnalysisTaskRunnerMessageHandlerTest {

    @Mock
    private AnalysisTaskRunner runner;

    private AnalysisTaskRunnerMessageHandler handler;

    @BeforeEach
    void setUp() {
        handler = new AnalysisTaskRunnerMessageHandler(runner);
    }

    @Test
    void analysisCreatedCallsRunnerRun() {
        AnalysisTaskMessage message = message();

        handler.handle(AnalysisTaskMessageTag.ANALYSIS_CREATED, message);

        verify(runner).run(message);
        verifyNoMoreInteractions(runner);
    }

    @Test
    void analysisRetryCallsRunnerRetry() {
        AnalysisTaskMessage message = message();

        handler.handle(AnalysisTaskMessageTag.ANALYSIS_RETRY, message);

        verify(runner).retry(message);
        verifyNoMoreInteractions(runner);
    }

    @Test
    void analysisCancelCallsRunnerCancel() {
        AnalysisTaskMessage message = message();

        handler.handle(AnalysisTaskMessageTag.ANALYSIS_CANCEL, message);

        verify(runner).cancel(message);
        verifyNoMoreInteractions(runner);
    }

    private static AnalysisTaskMessage message() {
        return new AnalysisTaskMessage(
            "task_1",
            "up_1",
            7L,
            "zh-CN",
            "req_1",
            "trace_1",
            Instant.parse("2026-06-27T10:00:00Z")
        );
    }
}
