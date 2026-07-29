package com.example.courselingo.learning.service;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.courselingo.ai.llm.LlmRequest;
import com.example.courselingo.fusion.VideoSegment;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.subtitle.domain.SubtitleTranslationSegment;
import java.time.Duration;
import java.util.List;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

class LearningPackagePromptFactoryTest {

    @Test
    void addsBoundedMultimodalTimeline() {
        List<VideoSegment> timeline = IntStream.range(0, 45).mapToObj(this::segment).toList();

        LlmRequest request = LearningPackagePromptFactory.build(
            command(),
            List.of(source()),
            List.of(translation()),
            timeline,
            Duration.ofSeconds(30)
        );

        String prompt = request.messages().get(1).content();
        assertThat(prompt)
            .contains("Bounded multimodal timeline JSON")
            .contains("\"mode\":\"MULTIMODAL\"")
            .contains("OCR frame 0")
            .contains("visual frame 39")
            .doesNotContain("visual frame 40");
        assertThat(request.metadata()).containsEntry("multimodalSegmentCount", 40);
    }

    @Test
    void degradesToTranscriptOnlyWhenVisualEvidenceIsAbsent() {
        VideoSegment segment = segment(0);
        segment.setOcrText("");
        segment.setVisualSummary("");

        LlmRequest request = LearningPackagePromptFactory.build(
            command(),
            List.of(source()),
            List.of(translation()),
            List.of(segment),
            Duration.ofSeconds(30)
        );

        assertThat(request.messages().get(1).content())
            .contains("\"mode\":\"TRANSCRIPT_ONLY\"")
            .contains("spoken frame 0")
            .doesNotContain("\"visualSummary\"");
    }

    private VideoSegment segment(int index) {
        VideoSegment segment = new VideoSegment();
        segment.setId((long) index + 1L);
        segment.setSegmentIndex(index);
        segment.setStartMillis(index * 60_000L);
        segment.setEndMillis((index + 1L) * 60_000L);
        segment.setAsrText("spoken frame " + index);
        segment.setTranslatedText("translated frame " + index);
        segment.setOcrText("OCR frame " + index);
        segment.setVisualSummary("visual frame " + index);
        segment.setConfidence(0.8d);
        return segment;
    }

    private static ValidatedLearningPackageCommand command() {
        return new ValidatedLearningPackageCommand("task_1", 42L, "en", "zh-CN", "req_1");
    }

    private static SubtitleSegment source() {
        SubtitleSegment segment = new SubtitleSegment();
        segment.setSegmentIndex(0);
        segment.setStartMillis(0L);
        segment.setEndMillis(1_000L);
        segment.setText("source");
        return segment;
    }

    private static SubtitleTranslationSegment translation() {
        SubtitleTranslationSegment segment = new SubtitleTranslationSegment();
        segment.setSegmentIndex(0);
        segment.setStartMillis(0L);
        segment.setEndMillis(1_000L);
        segment.setTranslatedText("translation");
        return segment;
    }
}
