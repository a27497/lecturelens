package com.example.courselingo.task.runner;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;

class PipelineVisionAnalysisExecutionOrderTest {

    @Test
    void visionAnalysisRunsAfterOcrAndBeforeAiCallRecord() {
        List<PipelineAnalysisTaskStepName> ordered = PipelineAnalysisTaskStepName.ordered();

        assertThat(ordered)
            .containsSubsequence(
                PipelineAnalysisTaskStepName.GENERATE_ARTIFACTS,
                PipelineAnalysisTaskStepName.OCR_KEYFRAMES,
                PipelineAnalysisTaskStepName.ANALYZE_KEYFRAMES,
                PipelineAnalysisTaskStepName.FUSE_VIDEO_SEGMENTS,
                PipelineAnalysisTaskStepName.WRITE_AI_CALL_RECORD
            );
    }
}
