package com.example.courselingo.chapter.service;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.courselingo.chapter.dto.CourseChapterEvidenceItem;
import java.util.List;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

class CourseChapterCoverageCompleterTest {

    @Test
    void fillsMissingEvidenceWindowWhileKeepingModelAuthoredContent() {
        List<CourseChapterEvidenceItem> evidence = evidence(4);
        var chapters = List.of(
            chapter("First topic", 0L, 240_000L, List.of(0)),
            chapter("Second topic", 480_000L, 960_000L, List.of(2, 3))
        );

        var completed = CourseChapterCoverageCompleter.complete(chapters, evidence, 20);
        var report = CourseChapterCoverageValidator.validate(completed, evidence, new CourseChapterProperties());

        assertThat(report.valid()).isTrue();
        assertThat(completed).extracting(CourseChapterResponseParser.ParsedCourseChapter::title)
            .containsExactly("First topic", "Second topic");
        assertThat(completed.getFirst().evidenceIndexes()).containsExactly(0, 1);
        assertThat(completed.getFirst().endTimeMillis()).isEqualTo(completed.getLast().startTimeMillis());
        assertThat(completed.getLast()).isEqualTo(chapters.getLast());
    }

    @Test
    void returnsInvalidCandidateForSparseEvidenceSoServiceCanUseSafeFallback() {
        List<CourseChapterEvidenceItem> evidence = List.of(
            new CourseChapterEvidenceItem(0, 0L, 240_000L, "first", "first"),
            new CourseChapterEvidenceItem(1, 600_000L, 840_000L, "second", "second")
        );
        var chapters = List.of(
            chapter("First topic", 0L, 240_000L, List.of(0)),
            chapter("Second topic", 600_000L, 840_000L, List.of(1))
        );

        var completed = CourseChapterCoverageCompleter.complete(chapters, evidence, 20);
        var report = CourseChapterCoverageValidator.validate(completed, evidence, new CourseChapterProperties());

        assertThat(report.valid()).isFalse();
        assertThat(report.violations()).contains("chapter timeline contains an uncovered gap");
    }

    private static List<CourseChapterEvidenceItem> evidence(int count) {
        return IntStream.range(0, count).mapToObj(index -> new CourseChapterEvidenceItem(
            index, index * 240_000L, (index + 1L) * 240_000L, "time", "evidence " + index
        )).toList();
    }

    private static CourseChapterResponseParser.ParsedCourseChapter chapter(
        String title,
        long start,
        long end,
        List<Integer> evidence
    ) {
        return new CourseChapterResponseParser.ParsedCourseChapter(
            title, title + " summary", start, end, List.of(title), evidence
        );
    }
}
