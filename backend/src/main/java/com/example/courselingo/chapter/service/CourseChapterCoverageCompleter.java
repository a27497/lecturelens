package com.example.courselingo.chapter.service;

import com.example.courselingo.chapter.dto.CourseChapterEvidenceItem;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

final class CourseChapterCoverageCompleter {

    private CourseChapterCoverageCompleter() {
    }

    static List<CourseChapterResponseParser.ParsedCourseChapter> complete(
        List<CourseChapterResponseParser.ParsedCourseChapter> chapters,
        List<CourseChapterEvidenceItem> evidence,
        int maxChapters
    ) {
        if (chapters == null || chapters.isEmpty() || evidence == null || evidence.isEmpty()) {
            return List.of();
        }
        int safeLimit = Math.max(1, maxChapters);
        List<MutableChapter> mutable = new ArrayList<>();
        for (CourseChapterResponseParser.ParsedCourseChapter chapter : chapters.stream()
            .sorted(Comparator.comparingLong(CourseChapterResponseParser.ParsedCourseChapter::startTimeMillis)
                .thenComparingLong(CourseChapterResponseParser.ParsedCourseChapter::endTimeMillis))
            .limit(safeLimit)
            .toList()) {
            List<Integer> indexes = chapter.evidenceIndexes().stream()
                .filter(index -> index != null && index >= 0 && index < evidence.size())
                .distinct()
                .sorted()
                .toList();
            if (indexes.isEmpty()) return List.of();
            mutable.add(new MutableChapter(chapter, new LinkedHashSet<>(indexes)));
        }
        if (mutable.isEmpty()) return List.of();

        Set<Integer> referenced = new HashSet<>();
        mutable.forEach(chapter -> referenced.addAll(chapter.evidenceIndexes));
        for (int evidenceIndex = 0; evidenceIndex < evidence.size(); evidenceIndex++) {
            if (!referenced.contains(evidenceIndex)) {
                nearestChapter(mutable, evidenceIndex).evidenceIndexes.add(evidenceIndex);
            }
        }

        List<CourseChapterResponseParser.ParsedCourseChapter> completed = new ArrayList<>(mutable.size());
        for (MutableChapter chapter : mutable) {
            List<Integer> assignedEvidence = chapter.evidenceIndexes.stream().sorted().toList();
            CourseChapterEvidenceItem first = evidence.get(assignedEvidence.getFirst());
            CourseChapterEvidenceItem last = evidence.get(assignedEvidence.getLast());
            CourseChapterResponseParser.ParsedCourseChapter source = chapter.source;
            completed.add(new CourseChapterResponseParser.ParsedCourseChapter(
                source.title(),
                source.summary(),
                Math.min(source.startTimeMillis(), first.startTimeMillis()),
                Math.max(source.endTimeMillis(), last.endTimeMillis()),
                source.keywords(),
                assignedEvidence
            ));
        }
        return List.copyOf(completed);
    }

    private static MutableChapter nearestChapter(List<MutableChapter> chapters, int evidenceIndex) {
        MutableChapter nearest = chapters.getFirst();
        int nearestDistance = Integer.MAX_VALUE;
        for (MutableChapter chapter : chapters) {
            int distance = chapter.evidenceIndexes.stream()
                .mapToInt(index -> Math.abs(index - evidenceIndex))
                .min()
                .orElse(Integer.MAX_VALUE);
            if (distance < nearestDistance) {
                nearest = chapter;
                nearestDistance = distance;
            }
        }
        return nearest;
    }

    private static final class MutableChapter {
        private final CourseChapterResponseParser.ParsedCourseChapter source;
        private final Set<Integer> evidenceIndexes;

        private MutableChapter(
            CourseChapterResponseParser.ParsedCourseChapter source,
            Set<Integer> evidenceIndexes
        ) {
            this.source = source;
            this.evidenceIndexes = evidenceIndexes;
        }
    }
}
