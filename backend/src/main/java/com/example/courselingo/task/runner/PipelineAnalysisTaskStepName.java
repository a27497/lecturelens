package com.example.courselingo.task.runner;

import java.util.List;

public enum PipelineAnalysisTaskStepName {
    VALIDATE_TASK,
    RESOLVE_UPLOADED_SOURCE,
    EXTRACT_KEYFRAMES,
    EXTRACT_AUDIO,
    TRANSCRIBE,
    PERSIST_SUBTITLES,
    TRANSLATE_SUBTITLES,
    GENERATE_LEARNING_PACKAGE,
    GENERATE_ARTIFACTS,
    OCR_KEYFRAMES,
    ANALYZE_KEYFRAMES,
    FUSE_VIDEO_SEGMENTS,
    WRITE_AI_CALL_RECORD,
    UPDATE_TASK_PROGRESS_STATUS;

    public static List<PipelineAnalysisTaskStepName> ordered() {
        return List.of(values());
    }
}
