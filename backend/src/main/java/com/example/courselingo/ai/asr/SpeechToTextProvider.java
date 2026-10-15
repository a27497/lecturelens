package com.example.courselingo.ai.asr;

public interface SpeechToTextProvider {

    SpeechToTextResult transcribe(SpeechToTextRequest request);

    String providerName();

    default long maxAudioFileSizeBytes() { return Long.MAX_VALUE; }

    default Integer maxAttempts() { return null; }

    /** Pin the adapter once before any task work is submitted to chunk workers. */
    default SpeechToTextProvider forExecution(
        com.example.courselingo.systemmodel.SystemModelExecutionRef execution
    ) {
        return this;
    }
}
