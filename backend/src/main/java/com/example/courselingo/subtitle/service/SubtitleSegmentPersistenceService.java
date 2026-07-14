package com.example.courselingo.subtitle.service;

public interface SubtitleSegmentPersistenceService {

    int saveTranscriptionResult(SaveTranscriptionSegmentsCommand command);

    int deleteByTaskId(String taskId, Long userId);
}
