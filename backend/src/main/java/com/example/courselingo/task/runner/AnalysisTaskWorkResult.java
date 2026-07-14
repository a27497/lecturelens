package com.example.courselingo.task.runner;

public record AnalysisTaskWorkResult(
    boolean success,
    String errorCode,
    String errorMessage
) {

    public static AnalysisTaskWorkResult failure(String errorCode, String errorMessage) {
        return new AnalysisTaskWorkResult(false, errorCode, errorMessage);
    }
}
