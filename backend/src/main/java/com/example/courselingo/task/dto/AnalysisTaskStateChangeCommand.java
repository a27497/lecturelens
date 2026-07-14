package com.example.courselingo.task.dto;

import com.example.courselingo.task.model.AnalysisTaskStage;
import com.example.courselingo.task.model.AnalysisTaskStatus;

public class AnalysisTaskStateChangeCommand {

    private String taskId;
    private Long userId;
    private AnalysisTaskStatus targetStatus;
    private Integer progressPercent;
    private AnalysisTaskStage stage;
    private String errorCode;
    private String errorMessage;

    public static Builder builder() {
        return new Builder();
    }

    public String getTaskId() {
        return taskId;
    }

    public Long getUserId() {
        return userId;
    }

    public AnalysisTaskStatus getTargetStatus() {
        return targetStatus;
    }

    public Integer getProgressPercent() {
        return progressPercent;
    }

    public AnalysisTaskStage getStage() {
        return stage;
    }

    public String getErrorCode() {
        return errorCode;
    }

    public String getErrorMessage() {
        return errorMessage;
    }

    public static class Builder {

        private final AnalysisTaskStateChangeCommand command = new AnalysisTaskStateChangeCommand();

        public Builder taskId(String taskId) {
            command.taskId = taskId;
            return this;
        }

        public Builder userId(Long userId) {
            command.userId = userId;
            return this;
        }

        public Builder targetStatus(AnalysisTaskStatus targetStatus) {
            command.targetStatus = targetStatus;
            return this;
        }

        public Builder progressPercent(Integer progressPercent) {
            command.progressPercent = progressPercent;
            return this;
        }

        public Builder stage(AnalysisTaskStage stage) {
            command.stage = stage;
            return this;
        }

        public Builder errorCode(String errorCode) {
            command.errorCode = errorCode;
            return this;
        }

        public Builder errorMessage(String errorMessage) {
            command.errorMessage = errorMessage;
            return this;
        }

        public AnalysisTaskStateChangeCommand build() {
            return command;
        }
    }
}
