package com.example.courselingo.task.service;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.task.model.AnalysisTaskStatus;
import java.util.EnumMap;
import java.util.EnumSet;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Component;

@Component
public class AnalysisTaskStateMachine {

    private final Map<AnalysisTaskStatus, Set<AnalysisTaskStatus>> allowedTransitions =
        new EnumMap<>(AnalysisTaskStatus.class);

    public AnalysisTaskStateMachine() {
        allowedTransitions.put(AnalysisTaskStatus.CREATED, EnumSet.of(
            AnalysisTaskStatus.QUEUED,
            AnalysisTaskStatus.CANCELED
        ));
        allowedTransitions.put(AnalysisTaskStatus.QUEUED, EnumSet.of(
            AnalysisTaskStatus.RUNNING,
            AnalysisTaskStatus.CANCELED
        ));
        allowedTransitions.put(AnalysisTaskStatus.RUNNING, EnumSet.of(
            AnalysisTaskStatus.SUCCEEDED,
            AnalysisTaskStatus.FAILED,
            AnalysisTaskStatus.RETRYING,
            AnalysisTaskStatus.CANCELED
        ));
        allowedTransitions.put(AnalysisTaskStatus.RETRYING, EnumSet.of(
            AnalysisTaskStatus.QUEUED,
            AnalysisTaskStatus.CANCELED,
            AnalysisTaskStatus.FAILED
        ));
        allowedTransitions.put(AnalysisTaskStatus.FAILED, EnumSet.of(
            AnalysisTaskStatus.RETRYING
        ));
    }

    public boolean canTransit(AnalysisTaskStatus currentStatus, AnalysisTaskStatus targetStatus) {
        if (currentStatus == null || targetStatus == null) {
            return false;
        }
        return allowedTransitions.getOrDefault(currentStatus, Set.of()).contains(targetStatus);
    }

    public void assertTransition(AnalysisTaskStatus currentStatus, AnalysisTaskStatus targetStatus) {
        if (!canTransit(currentStatus, targetStatus)) {
            throw new BusinessException(ErrorCode.TASK_INVALID_STATUS);
        }
    }
}
