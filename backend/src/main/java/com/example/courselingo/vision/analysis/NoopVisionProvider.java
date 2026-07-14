package com.example.courselingo.vision.analysis;

import java.util.List;

public class NoopVisionProvider implements VisionModelProvider {

    @Override
    public String providerName() {
        return "noop-vision";
    }

    @Override
    public VisionAnalysisResult analyze(VisionAnalysisRequest request) {
        return new VisionAnalysisResult(
            VisionAnalysisStatus.SKIPPED,
            "",
            "",
            List.of(),
            providerName(),
            "",
            0L,
            null,
            null
        );
    }
}
