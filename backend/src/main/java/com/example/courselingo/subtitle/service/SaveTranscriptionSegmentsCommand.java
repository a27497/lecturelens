package com.example.courselingo.subtitle.service;

import com.example.courselingo.ai.asr.SpeechToTextResult;

public record SaveTranscriptionSegmentsCommand(
    String taskId,
    Long userId,
    SpeechToTextResult result
) {
}
