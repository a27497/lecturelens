package com.example.courselingo.task;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.task.model.AnalysisTaskStatus;
import com.example.courselingo.task.service.AnalysisTaskStateMachine;
import org.junit.jupiter.api.Test;

class AnalysisTaskStateMachineTest {

    private final AnalysisTaskStateMachine stateMachine = new AnalysisTaskStateMachine();

    @Test
    void allowsConfiguredTransitions() {
        assertThat(stateMachine.canTransit(AnalysisTaskStatus.CREATED, AnalysisTaskStatus.QUEUED)).isTrue();
        assertThat(stateMachine.canTransit(AnalysisTaskStatus.QUEUED, AnalysisTaskStatus.RUNNING)).isTrue();
        assertThat(stateMachine.canTransit(AnalysisTaskStatus.RUNNING, AnalysisTaskStatus.SUCCEEDED)).isTrue();
        assertThat(stateMachine.canTransit(AnalysisTaskStatus.RUNNING, AnalysisTaskStatus.FAILED)).isTrue();
        assertThat(stateMachine.canTransit(AnalysisTaskStatus.RUNNING, AnalysisTaskStatus.RETRYING)).isTrue();
        assertThat(stateMachine.canTransit(AnalysisTaskStatus.FAILED, AnalysisTaskStatus.RETRYING)).isTrue();
        assertThat(stateMachine.canTransit(AnalysisTaskStatus.RETRYING, AnalysisTaskStatus.QUEUED)).isTrue();
        assertThat(stateMachine.canTransit(AnalysisTaskStatus.RETRYING, AnalysisTaskStatus.CANCELED)).isTrue();
        assertThat(stateMachine.canTransit(AnalysisTaskStatus.QUEUED, AnalysisTaskStatus.CANCELED)).isTrue();
        assertThat(stateMachine.canTransit(AnalysisTaskStatus.CREATED, AnalysisTaskStatus.CANCELED)).isTrue();
    }

    @Test
    void rejectsForbiddenTransitions() {
        assertThat(stateMachine.canTransit(AnalysisTaskStatus.SUCCEEDED, AnalysisTaskStatus.RUNNING)).isFalse();
        assertThat(stateMachine.canTransit(AnalysisTaskStatus.SUCCEEDED, AnalysisTaskStatus.FAILED)).isFalse();
        assertThat(stateMachine.canTransit(AnalysisTaskStatus.FAILED, AnalysisTaskStatus.RUNNING)).isFalse();
        assertThat(stateMachine.canTransit(AnalysisTaskStatus.FAILED, AnalysisTaskStatus.SUCCEEDED)).isFalse();
        assertThat(stateMachine.canTransit(AnalysisTaskStatus.CANCELED, AnalysisTaskStatus.RUNNING)).isFalse();
        assertThat(stateMachine.canTransit(AnalysisTaskStatus.CANCELED, AnalysisTaskStatus.SUCCEEDED)).isFalse();
        assertThat(stateMachine.canTransit(AnalysisTaskStatus.CREATED, AnalysisTaskStatus.SUCCEEDED)).isFalse();
        assertThat(stateMachine.canTransit(AnalysisTaskStatus.QUEUED, AnalysisTaskStatus.SUCCEEDED)).isFalse();
    }

    @Test
    void assertTransitionThrowsBusinessExceptionForIllegalTransition() {
        assertThatThrownBy(() -> stateMachine.assertTransition(AnalysisTaskStatus.CREATED, AnalysisTaskStatus.SUCCEEDED))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_INVALID_STATUS);
    }

    @Test
    void parsesKnownStatusAndRejectsIllegalStatusString() {
        assertThat(AnalysisTaskStatus.fromDatabaseValue("RUNNING")).isEqualTo(AnalysisTaskStatus.RUNNING);
        assertThat(AnalysisTaskStatus.fromDatabaseValue(" running ")).isEqualTo(AnalysisTaskStatus.RUNNING);

        assertThatThrownBy(() -> AnalysisTaskStatus.fromDatabaseValue("CLAIMED"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_INVALID_STATUS);
    }
}
