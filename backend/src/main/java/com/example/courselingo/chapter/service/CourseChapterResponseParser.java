package com.example.courselingo.chapter.service;

import com.example.courselingo.chapter.dto.CourseChapterEvidenceItem;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import org.springframework.stereotype.Component;

@Component
public class CourseChapterResponseParser {

    private final ObjectMapper objectMapper = new ObjectMapper();

    public List<ParsedCourseChapter> parse(String content, List<CourseChapterEvidenceItem> evidence, int maxChapters) {
        try {
            JsonNode root = objectMapper.readTree(content == null ? "" : content);
            JsonNode chaptersNode = root.path("chapters");
            if (!chaptersNode.isArray()) {
                throw new IllegalArgumentException("chapters must be an array");
            }
            List<ParsedCourseChapter> chapters = new ArrayList<>();
            for (JsonNode chapterNode : chaptersNode) {
                toChapter(chapterNode, evidence).ifPresent(chapters::add);
                if (chapters.size() >= maxChapters) {
                    break;
                }
            }
            return normalize(chapters, maxChapters);
        } catch (BusinessException exception) {
            throw exception;
        } catch (Exception exception) {
            throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "Course chapter response is not valid JSON");
        }
    }

    private java.util.Optional<ParsedCourseChapter> toChapter(JsonNode node, List<CourseChapterEvidenceItem> evidence) {
        List<Integer> indexes = validEvidenceIndexes(node.path("evidenceIndexes"), evidence.size());
        long minStart = evidence.stream().mapToLong(CourseChapterEvidenceItem::startTimeMillis).min().orElse(0L);
        long maxEnd = evidence.stream().mapToLong(CourseChapterEvidenceItem::endTimeMillis).max().orElse(minStart);
        if (!indexes.isEmpty()) {
            minStart = indexes.stream().map(evidence::get).mapToLong(CourseChapterEvidenceItem::startTimeMillis).min().orElse(minStart);
            maxEnd = indexes.stream().map(evidence::get).mapToLong(CourseChapterEvidenceItem::endTimeMillis).max().orElse(maxEnd);
        }
        long start = clamp(node.path("startTimeMillis").asLong(minStart), minStart, maxEnd);
        long end = clamp(node.path("endTimeMillis").asLong(maxEnd), minStart, maxEnd);
        if (end <= start) {
            return java.util.Optional.empty();
        }
        String title = clean(node.path("title").asText(""));
        String summary = clean(node.path("summary").asText(""));
        List<String> keywords = stringArray(node.path("keywords"));
        return java.util.Optional.of(new ParsedCourseChapter(
            title.isBlank() ? "未命名章节" : title,
            summary.isBlank() ? "本章根据课程转写内容生成。" : summary,
            start,
            end,
            keywords,
            indexes
        ));
    }

    private List<ParsedCourseChapter> normalize(List<ParsedCourseChapter> chapters, int maxChapters) {
        List<ParsedCourseChapter> sorted = chapters.stream()
            .sorted(java.util.Comparator.comparingLong(ParsedCourseChapter::startTimeMillis)
                .thenComparingLong(ParsedCourseChapter::endTimeMillis))
            .toList();
        List<ParsedCourseChapter> result = new ArrayList<>();
        Set<String> seen = new LinkedHashSet<>();
        long previousEnd = -1L;
        for (ParsedCourseChapter chapter : sorted) {
            long start = chapter.startTimeMillis();
            long end = chapter.endTimeMillis();
            if (start < previousEnd) {
                start = previousEnd;
            }
            if (end <= start) {
                continue;
            }
            String key = start + ":" + end + ":" + chapter.title();
            if (!seen.add(key)) {
                continue;
            }
            result.add(new ParsedCourseChapter(
                chapter.title(),
                chapter.summary(),
                start,
                end,
                chapter.keywords(),
                chapter.evidenceIndexes()
            ));
            previousEnd = end;
            if (result.size() >= maxChapters) {
                break;
            }
        }
        return result;
    }

    private static List<Integer> validEvidenceIndexes(JsonNode node, int evidenceSize) {
        if (!node.isArray()) {
            return List.of();
        }
        Set<Integer> indexes = new LinkedHashSet<>();
        for (JsonNode value : node) {
            int index = value.asInt(-1);
            if (index >= 0 && index < evidenceSize) {
                indexes.add(index);
            }
        }
        return List.copyOf(indexes);
    }

    private static List<String> stringArray(JsonNode node) {
        if (!node.isArray()) {
            return List.of();
        }
        List<String> values = new ArrayList<>();
        for (JsonNode item : node) {
            String value = clean(item.asText(""));
            if (!value.isBlank() && !values.contains(value)) {
                values.add(value);
            }
        }
        return values;
    }

    private static long clamp(long value, long min, long max) {
        return Math.max(min, Math.min(value, max));
    }

    private static String clean(String value) {
        return value == null ? "" : value.replaceAll("\\s+", " ").strip();
    }

    public record ParsedCourseChapter(
        String title,
        String summary,
        long startTimeMillis,
        long endTimeMillis,
        List<String> keywords,
        List<Integer> evidenceIndexes
    ) {
        public ParsedCourseChapter {
            keywords = keywords == null ? List.of() : List.copyOf(keywords);
            evidenceIndexes = evidenceIndexes == null ? List.of() : List.copyOf(evidenceIndexes);
        }
    }
}
