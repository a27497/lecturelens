package com.example.courselingo.result.dto;

/** Status of a feature produced after subtitles (learning package, download files). */
public enum BackgroundStageStatus {
    NOT_STARTED,
    RUNNING,
    SUCCEEDED,
    FAILED,
    SKIPPED,
    CANCELED
}
