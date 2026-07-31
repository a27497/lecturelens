package com.example.courselingo.chapter.service;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.courselingo.chapter.dto.CourseChapterEvidenceItem;
import java.util.List;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

class CourseChapterCoverageValidatorTest {

    private final CourseChapterProperties properties = new CourseChapterProperties();

    @Test
    void acceptsCompleteLongTimelineWithoutGapsAndWithEvidenceOnEveryChapter() {
        List<CourseChapterEvidenceItem> evidence = evidence(18);
        var chapters = CourseChapterFallbackFactory.build(evidence, "zh-CN", properties);

        CourseChapterCoverageReport report = CourseChapterCoverageValidator.validate(chapters, evidence, properties);

        assertThat(report.valid()).isTrue();
        assertThat(report.timelineCoverageRatio()).isGreaterThanOrEqualTo(0.90d);
        assertThat(report.evidenceCoverageRatio()).isEqualTo(1.0d);
        assertThat(report.maxGapMillis()).isZero();
        assertThat(chapters).allSatisfy(chapter -> assertThat(chapter.evidenceIndexes()).isNotEmpty());
    }

    @Test
    void rejectsMissingTailEmptyEvidenceAndLongInternalGap() {
        List<CourseChapterEvidenceItem> evidence = evidence(18);
        var chapters = List.of(
            chapter(0L, 240_000L, List.of(0)),
            chapter(480_000L, 720_000L, List.of())
        );

        CourseChapterCoverageReport report = CourseChapterCoverageValidator.validate(chapters, evidence, properties);

        assertThat(report.valid()).isFalse();
        assertThat(report.chaptersWithoutEvidence()).containsExactly(1);
        assertThat(report.missingEvidenceIndexes()).contains(1, 17);
        assertThat(report.maxGapMillis()).isGreaterThan(properties.getWindowSeconds() * 1000L);
        assertThat(report.violations()).contains("last evidence is not cited", "every chapter must cite evidence");
    }

    @Test
    void deterministicFallbackCoversEveryEvidenceWindowInFiveToTwelveMinuteGroups() {
        List<CourseChapterEvidenceItem> evidence = evidence(18);
        var chapters = CourseChapterFallbackFactory.build(evidence, "zh-CN", properties);

        assertThat(chapters).hasSizeBetween(6, 16);
        assertThat(chapters.getFirst().startTimeMillis()).isEqualTo(0L);
        assertThat(chapters.getLast().endTimeMillis()).isEqualTo(18L * 240_000L);
        assertThat(chapters.stream().flatMap(chapter -> chapter.evidenceIndexes().stream()).distinct()).hasSize(18);
    }

    @Test
    void sparseTimelineStartingAfterZeroUsesItsRealEvidenceBounds() {
        List<CourseChapterEvidenceItem> evidence = List.of(
            new CourseChapterEvidenceItem(0, 1_200_000L, 1_440_000L, "20:00-24:00", "fictional start"),
            new CourseChapterEvidenceItem(1, 3_840_000L, 4_080_000L, "64:00-68:00", "fictional end")
        );
        CourseChapterProperties sparseRules = new CourseChapterProperties();

        var chapters = CourseChapterFallbackFactory.build(evidence, "zh-CN", sparseRules);
        CourseChapterCoverageReport report = CourseChapterCoverageValidator.validate(chapters, evidence, sparseRules);

        assertThat(report.valid()).isTrue();
        assertThat(chapters.getFirst().startTimeMillis()).isEqualTo(1_200_000L);
        assertThat(chapters.getLast().endTimeMillis()).isEqualTo(4_080_000L);
        assertThat(chapters).allSatisfy(chapter -> assertThat(chapter.evidenceIndexes()).isNotEmpty());
    }

    @Test
    void rejectsOverlappingOrNonPositiveChapterAndEvidenceRanges() {
        List<CourseChapterEvidenceItem> invalidEvidence = List.of(
            new CourseChapterEvidenceItem(0, 0L, 240_000L, "first", "first"),
            new CourseChapterEvidenceItem(1, 120_000L, 360_000L, "overlap", "overlap"),
            new CourseChapterEvidenceItem(2, 360_000L, 360_000L, "invalid", "invalid")
        );
        var overlapping = List.of(
            chapter(0L, 180_000L, List.of(0)),
            chapter(120_000L, 300_000L, List.of(1)),
            chapter(360_000L, 360_000L, List.of(2))
        );

        CourseChapterCoverageReport report = CourseChapterCoverageValidator.validate(
            overlapping, invalidEvidence, properties
        );

        assertThat(report.valid()).isFalse();
        assertThat(report.violations()).contains(
            "evidence contains an invalid time range",
            "evidence overlaps",
            "chapters overlap",
            "chapter contains an invalid time range"
        );
    }

    private static List<CourseChapterEvidenceItem> evidence(int count) {
        return IntStream.range(0, count).mapToObj(index -> new CourseChapterEvidenceItem(
            index, index * 240_000L, (index + 1L) * 240_000L, "time", "fictional evidence " + index
        )).toList();
    }

    private static CourseChapterResponseParser.ParsedCourseChapter chapter(long start, long end, List<Integer> evidence) {
        return new CourseChapterResponseParser.ParsedCourseChapter("chapter", "summary", start, end, List.of(), evidence);
    }
}
