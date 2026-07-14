package com.example.courselingo.task.model;

public enum AnalysisTaskStage {
    CREATED,
    QUEUED,
    EXTRACT_AUDIO,
    ASR,
    TRANSLATE,
    GENERATE_LEARNING_PACKAGE,
    GENERATE_ARTIFACTS,
    DONE,
    FAILED
}
