package com.example.courselingo.vision.analysis;

import java.util.List;

public record VideoKeyframeAnalysisView(
    String status,
    String screenType,
    String summary,
    List<String> detectedElements,
    String provider,
    String model,
    String message
) {
    public VideoKeyframeAnalysisView {
        detectedElements = detectedElements == null ? List.of() : List.copyOf(detectedElements);
    }
}
