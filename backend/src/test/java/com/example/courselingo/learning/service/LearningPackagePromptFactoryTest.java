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

    @Test void originalEvidenceModeKeepsIndependentVisualObservationsForGenerationAndRepair() {
        var command = new ValidatedLearningPackageCommand("task_1", 42L, "en", "zh-CN", "req_1", null, true);
        var visual = segment(0);
        visual.setFusedSummary("translation-dependent fused summary");
        var properties = new LearningPackageProperties();
        var first = LearningPackagePromptFactory.build(command, List.of(source()), List.of(), List.of(visual), Duration.ofSeconds(30), properties);
        var repair = LearningPackagePromptFactory.buildRetry(command, List.of(source()), List.of(), List.of(visual), Duration.ofSeconds(30), properties);
        for (var request : List.of(first, repair)) {
            assertThat(request.messages().get(1).content()).contains("source", "OCR frame 0", "visual frame 0")
                .doesNotContain("translated frame", "translation-dependent fused summary", "translated subtitles");
            assertThat(request.metadata()).containsEntry("promptSource", "sourceOnly").containsEntry("translationSegmentCount", 0);
        }
        assertThat(repair.metadata()).containsEntry("promptVariant", "retry");
    }

    @Test
    void addsBoundedMultimodalTimeline() {
        List<VideoSegment> timeline = IntStream.range(0, 45).mapToObj(this::segment).toList();

        LlmRequest request = LearningPackagePromptFactory.build(
            command(),
            List.of(source()),
            List.of(translation()),
            timeline,
            Duration.ofSeconds(30),
            new LearningPackageProperties()
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
            Duration.ofSeconds(30),
            new LearningPackageProperties()
        );

        assertThat(request.messages().get(1).content())
            .contains("\"mode\":\"TRANSCRIPT_ONLY\"")
            .contains("spoken frame 0")
            .doesNotContain("\"visualSummary\"");
    }

    @Test
    void translatedAndFullTextPromptsAttachChapterWindowsAndKeepCueText() {
        List<SubtitleSegment> sources = IntStream.range(0, 5).mapToObj(index -> source(index, index * 60_000L)).toList();
        List<SubtitleTranslationSegment> translations = IntStream.range(0, 5)
            .mapToObj(index -> translation(index, index * 60_000L)).toList();
        var properties = new LearningPackageProperties();

        var translated = LearningPackagePromptFactory.build(
            command(), sources, translations, List.of(), Duration.ofSeconds(30), properties
        );
        assertThat(translated.metadata()).containsEntry("learningChapterCount", 2);
        @SuppressWarnings("unchecked")
        List<LearningPackageSourceSection> chapters =
            (List<LearningPackageSourceSection>) translated.metadata().get("learningSourceSections");
        assertThat(chapters).hasSize(2);
        assertThat(chapters.get(0).memberIndexes()).containsExactly(0, 1, 2, 3);
        assertThat(chapters.get(1).memberIndexes()).containsExactly(4);
        assertThat(translated.messages().get(1).content())
            .contains("Chapter 1 [0,240000) ms:", "Chapter 2 [240000,300000) ms:")
            .contains("\"sourceText\":\"source 0\"", "\"translatedText\":\"translation 4\"", "\"index\":4");

        var fullText = LearningPackagePromptFactory.buildFromFullText(
            command(), "full source", "full translation", sources, translations, List.of(),
            Duration.ofSeconds(30), properties
        );
        assertThat(fullText.metadata()).containsEntry("promptSource", "fullText").containsEntry("learningChapterCount", 2);
        assertThat(fullText.messages().get(1).content())
            .contains("Chapter 1 [", "\"sourceText\":\"source 0\"", "\"translatedText\":\"translation 0\"");
    }

    @Test
    void promptUsesTheSameConfiguredCourseTierAsValidation() {
        LearningPackageProperties properties = new LearningPackageProperties();
        properties.setLongCourseMinutes(12);
        List<VideoSegment> timeline = IntStream.range(0, 6).mapToObj(this::segment).toList();
        timeline.getLast().setEndMillis(15 * 60_000L);

        LlmRequest request = LearningPackagePromptFactory.build(
            command(), List.of(source()), List.of(translation()), timeline,
            Duration.ofSeconds(30), properties
        );

        assertThat(request.messages().get(1).content()).contains("Quality requirements: tier=LONG");
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
        return source(0, 0L, "source", 1_000L);
    }

    private static SubtitleSegment source(int index, long startMillis) {
        return source(index, startMillis, "source " + index, startMillis + 60_000L);
    }

    private static SubtitleSegment source(int index, long startMillis, String text, long endMillis) {
        SubtitleSegment segment = new SubtitleSegment();
        segment.setSegmentIndex(index);
        segment.setStartMillis(startMillis);
        segment.setEndMillis(endMillis);
        segment.setText(text);
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

    private static SubtitleTranslationSegment translation(int index, long startMillis) {
        SubtitleTranslationSegment segment = new SubtitleTranslationSegment();
        segment.setSegmentIndex(index);
        segment.setStartMillis(startMillis);
        segment.setEndMillis(startMillis + 60_000L);
        segment.setTranslatedText("translation " + index);
        return segment;
    }
}
