package com.example.courselingo.vision.analysis;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDateTime;
import java.util.List;

import org.junit.jupiter.api.Test;

class VideoKeyframeAnalysisViewsTest {

    @Test
    void existingAnalysisRowWinsEvenWhenVisionAnalysisIsDisabled() {
        VideoKeyframeAnalysis row = row(9L, VisionAnalysisStatus.SUCCEEDED, "PPT", "Course title slide");

        VideoKeyframeAnalysisView view = VideoKeyframeAnalysisViews.resolver(
            VideoKeyframeAnalysisViews.byKeyframeId(List.of(row)),
            false
        ).apply(9L);

        assertThat(view.status()).isEqualTo("SUCCEEDED");
        assertThat(view.screenType()).isEqualTo("PPT");
        assertThat(view.summary()).isEqualTo("Course title slide");
        assertThat(view.detectedElements()).containsExactly("title", "bullet");
        assertThat(view.provider()).isEqualTo("openai-compatible-vision");
        assertThat(view.model()).isEqualTo("qwen-vl");
        assertThat(view.toString())
            .doesNotContain("objectKey")
            .doesNotContain("localPath")
            .doesNotContain("raw request")
            .doesNotContain("raw response")
            .doesNotContain("api-key");
    }

    @Test
    void missingRowReturnsDisabledOrPendingFromCurrentConfiguration() {
        assertThat(VideoKeyframeAnalysisViews.missing(false).status()).isEqualTo("DISABLED");
        assertThat(VideoKeyframeAnalysisViews.missing(false).message()).isEqualTo("视觉分析暂未启用");
        assertThat(VideoKeyframeAnalysisViews.missing(true).status()).isEqualTo("PENDING");
        assertThat(VideoKeyframeAnalysisViews.missing(true).message()).isEqualTo("视觉分析待生成");
    }

    @Test
    void failedRowReturnsFriendlyMessageWithoutProviderDetails() {
        VideoKeyframeAnalysis row = row(9L, VisionAnalysisStatus.FAILED, "", "");
        row.setErrorMessage("provider stderr objectKey=keyframes/42/task_1/frame.jpg token=abc raw response=bad");

        VideoKeyframeAnalysisView view = VideoKeyframeAnalysisViews.byKeyframeId(List.of(row)).get(9L);

        assertThat(view.status()).isEqualTo("FAILED");
        assertThat(view.summary()).isEmpty();
        assertThat(view.message())
            .doesNotContain("stderr")
            .doesNotContain("keyframes/42")
            .doesNotContain("token")
            .doesNotContain("raw response");
    }

    private static VideoKeyframeAnalysis row(
        Long keyframeId,
        VisionAnalysisStatus status,
        String screenType,
        String summary
    ) {
        VideoKeyframeAnalysis row = new VideoKeyframeAnalysis();
        row.setId(100L + keyframeId);
        row.setTaskId("task_1");
        row.setUserId(42L);
        row.setKeyframeId(keyframeId);
        row.setTimestampMillis(12_345L);
        row.setProvider("openai-compatible-vision");
        row.setModel("qwen-vl");
        row.setScreenType(screenType);
        row.setVisualSummary(summary);
        row.setDetectedElementsJson("[\"title\",\"bullet\"]");
        row.setStatus(status.name());
        row.setDurationMillis(123L);
        row.setCreatedAt(LocalDateTime.of(2026, 7, 6, 10, 1));
        row.setUpdatedAt(LocalDateTime.of(2026, 7, 6, 10, 1));
        return row;
    }
}
