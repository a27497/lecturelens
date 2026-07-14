package com.example.courselingo.ai.asr;

import java.nio.file.Path;
import java.time.Duration;

public record SpeechToTextRequest(
    Path audioFile,
    String language,
    String requestId,
    String taskId,
    Duration timeout
) {
}
