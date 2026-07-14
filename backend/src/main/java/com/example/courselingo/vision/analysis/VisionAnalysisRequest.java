package com.example.courselingo.vision.analysis;

import com.example.courselingo.modelrouting.AiModelRoute;
import java.nio.file.Path;

public record VisionAnalysisRequest(
    String taskId,
    Long keyframeId,
    Long timestampMillis,
    Path imagePath,
    String ocrText,
    String promptContext,
    AiModelRoute route
) {
}
