package com.example.courselingo.subtitle.service;

import com.example.courselingo.ai.asr.SpeechToTextResult;

public record SaveTranscriptionSegmentsCommand(
    String taskId,
    Long userId,
    SpeechToTextResult result,
    String executionEventId
) {
    public SaveTranscriptionSegmentsCommand(String taskId,Long userId,SpeechToTextResult result){this(taskId,userId,result,null);}
}
