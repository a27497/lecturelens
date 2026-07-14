package com.example.courselingo.ai.asr;

public interface SpeechToTextProvider {

    SpeechToTextResult transcribe(SpeechToTextRequest request);

    String providerName();
}
