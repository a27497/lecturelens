package com.example.courselingo.chapter.service;

import com.example.courselingo.chapter.dto.CourseChapterEvidenceItem;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public final class CourseChapterCoverageValidator {

    private CourseChapterCoverageValidator() {
    }

    public static CourseChapterCoverageReport validate(
        List<CourseChapterResponseParser.ParsedCourseChapter> chapters,
        List<CourseChapterEvidenceItem> evidence,
        CourseChapterProperties properties
    ) {
        List<CourseChapterResponseParser.ParsedCourseChapter> safeChapters = chapters == null ? List.of() : chapters;
        List<CourseChapterEvidenceItem> safeEvidence = evidence == null ? List.of() : evidence;
        CourseChapterProperties rules = properties == null ? new CourseChapterProperties() : properties;
        List<String> violations = new ArrayList<>();
        List<Integer> emptyChapters = new ArrayList<>();
        Set<Integer> referenced = new HashSet<>();

        if (safeChapters.isEmpty()) violations.add("chapters must not be empty");
        if (safeEvidence.isEmpty()) violations.add("evidence must not be empty");

        long previousEvidenceStart = -1L;
        long previousEvidenceEnd = -1L;
        for (CourseChapterEvidenceItem item : safeEvidence) {
            if (item == null || item.startTimeMillis() < 0L || item.endTimeMillis() <= item.startTimeMillis()) {
                violations.add("evidence contains an invalid time range");
                continue;
            }
            if (item.startTimeMillis() < previousEvidenceStart) violations.add("evidence is not sorted");
            if (previousEvidenceEnd >= 0L && item.startTimeMillis() < previousEvidenceEnd) {
                violations.add("evidence overlaps");
            }
            previousEvidenceStart = item.startTimeMillis();
            previousEvidenceEnd = item.endTimeMillis();
        }

        long previousStart = -1L;
        long previousEnd = -1L;
        for (int chapterIndex = 0; chapterIndex < safeChapters.size(); chapterIndex++) {
            CourseChapterResponseParser.ParsedCourseChapter chapter = safeChapters.get(chapterIndex);
            if (chapter.startTimeMillis() < 0L || chapter.endTimeMillis() <= chapter.startTimeMillis()) {
                violations.add("chapter contains an invalid time range");
            }
            if (chapter.startTimeMillis() < previousStart) violations.add("chapters are not sorted");
            if (previousEnd >= 0L && chapter.startTimeMillis() < previousEnd) violations.add("chapters overlap");
            previousStart = chapter.startTimeMillis();
            previousEnd = Math.max(previousEnd, chapter.endTimeMillis());
            if (chapter.evidenceIndexes().isEmpty()) {
                emptyChapters.add(chapterIndex);
                continue;
            }
            long citedStart = Long.MAX_VALUE;
            long citedEnd = Long.MIN_VALUE;
            for (Integer evidenceIndex : chapter.evidenceIndexes()) {
                if (evidenceIndex == null || evidenceIndex < 0 || evidenceIndex >= safeEvidence.size()) {
                    violations.add("chapter contains an unknown evidence index");
                    continue;
                }
                referenced.add(evidenceIndex);
                CourseChapterEvidenceItem item = safeEvidence.get(evidenceIndex);
                citedStart = Math.min(citedStart, item.startTimeMillis());
                citedEnd = Math.max(citedEnd, item.endTimeMillis());
            }
            if (citedStart != Long.MAX_VALUE
                && (chapter.startTimeMillis() < citedStart || chapter.endTimeMillis() > citedEnd)) {
                violations.add("chapter time is outside its cited evidence");
            }
        }
        if (!emptyChapters.isEmpty()) violations.add("every chapter must cite evidence");

        List<Integer> missingEvidence = new ArrayList<>();
        for (int index = 0; index < safeEvidence.size(); index++) {
            if (!referenced.contains(index)) missingEvidence.add(index);
        }
        if (!missingEvidence.isEmpty()) violations.add("every evidence window must be cited");
        double evidenceCoverage = safeEvidence.isEmpty() ? 0.0d : (double) referenced.size() / safeEvidence.size();
        long timelineStart = safeEvidence.stream().mapToLong(CourseChapterEvidenceItem::startTimeMillis).min().orElse(0L);
        long timelineEnd = safeEvidence.stream().mapToLong(CourseChapterEvidenceItem::endTimeMillis).max().orElse(timelineStart);
        List<String> missingRanges = new ArrayList<>();
        long cursor = timelineStart;
        long coveredMillis = 0L;
        long maxGap = 0L;
        for (CourseChapterResponseParser.ParsedCourseChapter chapter : safeChapters) {
            long start = Math.max(timelineStart, chapter.startTimeMillis());
            long end = Math.min(timelineEnd, chapter.endTimeMillis());
            if (end <= start) continue;
            if (start > cursor) {
                maxGap = Math.max(maxGap, start - cursor);
                missingRanges.add(formatRange(cursor, start));
            }
            long effectiveStart = Math.max(start, cursor);
            if (end > effectiveStart) coveredMillis += end - effectiveStart;
            cursor = Math.max(cursor, end);
        }
        if (cursor < timelineEnd) {
            maxGap = Math.max(maxGap, timelineEnd - cursor);
            missingRanges.add(formatRange(cursor, timelineEnd));
        }
        long timelineMillis = Math.max(0L, timelineEnd - timelineStart);
        double timelineCoverage = timelineMillis == 0L ? (safeChapters.isEmpty() ? 0.0d : 1.0d)
            : Math.min(1.0d, (double) coveredMillis / timelineMillis);

        if (!safeEvidence.isEmpty() && !referenced.contains(0)) violations.add("first evidence is not cited");
        if (!safeEvidence.isEmpty() && !referenced.contains(safeEvidence.size() - 1)) violations.add("last evidence is not cited");
        if (timelineMillis >= rules.getLongTimelineSeconds() * 1000L
            && timelineCoverage + 0.000001d < rules.getMinTimelineCoverage()) {
            violations.add("timeline coverage is below the configured minimum");
        }
        if (!safeEvidence.isEmpty() && evidenceCoverage + 0.000001d < rules.getMinEvidenceCoverage()) {
            violations.add("evidence coverage is below the configured minimum");
        }
        if (maxGap > 0L) violations.add("chapter timeline contains an uncovered gap");
        long tailGap = safeChapters.isEmpty() ? timelineMillis
            : Math.max(0L, timelineEnd - safeChapters.get(safeChapters.size() - 1).endTimeMillis());
        if (tailGap > 20L * 60L * 1000L) violations.add("course tail is missing for more than twenty minutes");

        return new CourseChapterCoverageReport(
            violations.isEmpty(), timelineCoverage, evidenceCoverage, maxGap, missingEvidence,
            missingRanges, emptyChapters, violations.stream().distinct().toList()
        );
    }

    private static String formatRange(long start, long end) {
        return String.format(Locale.ROOT, "%d-%d", Math.max(0L, start), Math.max(0L, end));
    }
}
