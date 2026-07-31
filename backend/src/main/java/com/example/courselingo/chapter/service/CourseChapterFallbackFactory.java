package com.example.courselingo.chapter.service;

import com.example.courselingo.chapter.dto.CourseChapterEvidenceItem;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.stream.IntStream;

final class CourseChapterFallbackFactory {
    private CourseChapterFallbackFactory() {
    }

    static List<CourseChapterResponseParser.ParsedCourseChapter> build(
        List<CourseChapterEvidenceItem> evidence,
        String targetLanguage,
        CourseChapterProperties properties
    ) {
        if (evidence == null || evidence.isEmpty()) return List.of();
        int targetGroupSize = Math.max(1, (int) Math.round(8.0d * 60.0d / properties.getWindowSeconds()));
        int minimumForLimit = Math.max(1, (int) Math.ceil((double) evidence.size() / properties.getMaxChapters()));
        int groupSize = Math.max(targetGroupSize, minimumForLimit);
        List<CourseChapterResponseParser.ParsedCourseChapter> chapters = new ArrayList<>();
        boolean chinese = targetLanguage != null && targetLanguage.toLowerCase(Locale.ROOT).startsWith("zh");
        for (int from = 0; from < evidence.size(); from += groupSize) {
            int to = Math.min(evidence.size(), from + groupSize);
            int number = chapters.size() + 1;
            CourseChapterEvidenceItem first = evidence.get(from);
            CourseChapterEvidenceItem last = evidence.get(to - 1);
            List<Integer> indexes = IntStream.range(from, to).boxed().toList();
            String title = chinese ? "第 " + number + " 章：课程内容" : "Chapter " + number + ": Course content";
            String summary = chinese
                ? "本章整理课程第 " + (from + 1) + " 至第 " + to + " 个证据窗口中呈现的内容。"
                : "This chapter organizes the course content presented in evidence windows " + (from + 1) + " through " + to + ".";
            chapters.add(new CourseChapterResponseParser.ParsedCourseChapter(
                title, summary, first.startTimeMillis(), last.endTimeMillis(), List.of(), indexes
            ));
        }
        return List.copyOf(chapters);
    }
}
