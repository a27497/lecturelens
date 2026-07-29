package com.example.courselingo.task.runner;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;

class PipelineOcrExecutionOrderTest {

    @Test
    void ocrRunsAfterTranslationAndBeforeVisionAnalysis() {
        List<PipelineAnalysisTaskStepName> ordered = PipelineAnalysisTaskStepName.ordered();

        assertThat(ordered)
            .containsSubsequence(
                PipelineAnalysisTaskStepName.TRANSLATE_SUBTITLES,
                PipelineAnalysisTaskStepName.OCR_KEYFRAMES,
                PipelineAnalysisTaskStepName.ANALYZE_KEYFRAMES,
                PipelineAnalysisTaskStepName.FUSE_VIDEO_SEGMENTS,
                PipelineAnalysisTaskStepName.GENERATE_LEARNING_PACKAGE,
                PipelineAnalysisTaskStepName.GENERATE_ARTIFACTS,
                PipelineAnalysisTaskStepName.WRITE_AI_CALL_RECORD
            );
        assertThat(ordered.indexOf(PipelineAnalysisTaskStepName.OCR_KEYFRAMES))
            .isGreaterThan(ordered.indexOf(PipelineAnalysisTaskStepName.TRANSLATE_SUBTITLES));
        assertThat(ordered.indexOf(PipelineAnalysisTaskStepName.OCR_KEYFRAMES))
            .isLessThan(ordered.indexOf(PipelineAnalysisTaskStepName.WRITE_AI_CALL_RECORD));
    }
}
