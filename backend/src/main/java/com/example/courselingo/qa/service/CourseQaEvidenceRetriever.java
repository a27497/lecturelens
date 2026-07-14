package com.example.courselingo.qa.service;

import com.example.courselingo.fusion.VideoSegment;
import com.example.courselingo.fusion.mapper.VideoSegmentMapper;
import com.example.courselingo.qa.dto.CourseQaEvidenceItem;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.subtitle.domain.SubtitleTranslationSegment;
import com.example.courselingo.subtitle.mapper.SubtitleSegmentMapper;
import com.example.courselingo.subtitle.mapper.SubtitleTranslationSegmentMapper;
import com.example.courselingo.vision.ocr.mapper.VideoKeyframeOcrMapper;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class CourseQaEvidenceRetriever {

    private static final int MAX_CANDIDATES = 100;
    private static final int MAX_EVIDENCE = 8;
    private static final int MAX_SNIPPET = 500;
    private static final String SEGMENT_ASR_PREFIX = "\u672c\u6bb5\u4e3b\u8981\u8bb2\u89e3\uff1a";
    private static final String COURSE_QA_ASR_PREFIX = "\u672c\u6bb5\u8bed\u97f3\u539f\u6587\uff1a";
    private static final String SEGMENT_OCR_PREFIX = "\u753b\u9762\u6587\u5b57\u5305\u62ec\uff1a";
    private static final String SEGMENT_VISUAL_PREFIX = "\u753b\u9762\u663e\u793a\uff1a";
    private static final String SEGMENT_SUMMARY_DELIMITER = "\uff1b";
    private static final Pattern SEGMENT_SUMMARY_SPLITTER = Pattern.compile("[\uff1b;\\r\\n]+");
    private static final Pattern CLOCK_TIME = Pattern.compile("\\b(?:(\\d{1,2}):)?(\\d{1,2}):(\\d{2})\\b");
    private static final TypeReference<List<String>> STRING_LIST_TYPE = new TypeReference<>() {
    };

    private final VideoSegmentMapper videoSegmentMapper;
    private final SubtitleSegmentMapper subtitleSegmentMapper;
    private final SubtitleTranslationSegmentMapper translationSegmentMapper;
    private final VideoKeyframeOcrMapper ocrMapper;
    private final CourseQaQueryTermExtractor queryTermExtractor;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public CourseQaEvidenceRetriever(
        VideoSegmentMapper videoSegmentMapper,
        SubtitleSegmentMapper subtitleSegmentMapper,
        SubtitleTranslationSegmentMapper translationSegmentMapper,
        VideoKeyframeOcrMapper ocrMapper
    ) {
        this(
            videoSegmentMapper,
            subtitleSegmentMapper,
            translationSegmentMapper,
            ocrMapper,
            new CourseQaQueryTermExtractor()
        );
    }

    @Autowired
    public CourseQaEvidenceRetriever(
        VideoSegmentMapper videoSegmentMapper,
        SubtitleSegmentMapper subtitleSegmentMapper,
        SubtitleTranslationSegmentMapper translationSegmentMapper,
        VideoKeyframeOcrMapper ocrMapper,
        CourseQaQueryTermExtractor queryTermExtractor
    ) {
        this.videoSegmentMapper = Objects.requireNonNull(videoSegmentMapper, "videoSegmentMapper is required");
        this.subtitleSegmentMapper = Objects.requireNonNull(subtitleSegmentMapper, "subtitleSegmentMapper is required");
        this.translationSegmentMapper = Objects.requireNonNull(translationSegmentMapper, "translationSegmentMapper is required");
        this.ocrMapper = Objects.requireNonNull(ocrMapper, "ocrMapper is required");
        this.queryTermExtractor = Objects.requireNonNull(queryTermExtractor, "queryTermExtractor is required");
    }

    public List<CourseQaEvidenceItem> retrieve(String taskId, Long userId, String targetLanguage, String question) {
        List<String> tokens = queryTermExtractor.extract(question);
        Optional<TimeWindow> timeWindow = parseTimeWindow(question);
        List<Candidate> candidates = new ArrayList<>();
        for (VideoSegment row : videoSegmentMapper.selectByTaskIdAndUserId(taskId, userId)) {
            candidates.add(videoSegmentCandidate(row, tokens, timeWindow));
        }
        Map<Integer, SubtitleTranslationSegment> translations = translationMap(
            translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage(taskId, userId, targetLanguage)
        );
        for (SubtitleSegment row : subtitleSegmentMapper.selectByTaskIdAndUserId(taskId, userId)) {
            candidates.add(subtitleCandidate(row, translations.get(row.getSegmentIndex()), tokens, timeWindow));
        }
        return candidates.stream()
            .filter(candidate -> candidate.score() > 0.0d)
            .sorted((left, right) -> Double.compare(right.score(), left.score()))
            .limit(MAX_CANDIDATES)
            .map(Candidate::item)
            .filter(CourseQaEvidenceRetriever::hasEvidenceText)
            .filter(new LinkedHashSet<>()::add)
            .limit(MAX_EVIDENCE)
            .toList();
    }

    private static boolean hasEvidenceText(CourseQaEvidenceItem item) {
        return item != null
            && (!cleanText(item.snippet()).isBlank() || !cleanText(item.translatedSnippet()).isBlank());
    }

    private Candidate videoSegmentCandidate(
        VideoSegment row,
        List<String> tokens,
        Optional<TimeWindow> timeWindow
    ) {
        String snippet = videoSegmentSnippet(row);
        double score = score(
            String.join(" ", snippet, row.getAsrText(), row.getVisualSummary(), String.join(" ", parseKeywords(row.getKeywordsJson()))),
            tokens,
            row.getStartMillis(),
            row.getEndMillis(),
            timeWindow,
            1.0d,
            row.getConfidence()
        );
        return new Candidate(score, new CourseQaEvidenceItem(
            "VIDEO_SEGMENT",
            String.valueOf(row.getId()),
            row.getStartMillis(),
            row.getEndMillis(),
            firstNonBlank(row.getTimeText(), formatRange(row.getStartMillis(), row.getEndMillis())),
            truncate(snippet),
            "",
            row.getConfidence()
        ));
    }

    private static String videoSegmentSnippet(VideoSegment row) {
        List<String> parts = new ArrayList<>();
        String asrText = cleanText(row.getAsrText());
        boolean hasStructuredAsr = !asrText.isBlank();
        if (hasStructuredAsr) {
            parts.add(COURSE_QA_ASR_PREFIX + asrText);
        }
        String visualSummary = cleanText(row.getVisualSummary());
        if (!visualSummary.isBlank()) {
            parts.add(SEGMENT_VISUAL_PREFIX + visualSummary);
        }
        cleanVideoSegmentFusedSummaryParts(row.getFusedSummary(), !hasStructuredAsr).stream()
            .filter(part -> !parts.contains(part))
            .forEach(parts::add);
        return String.join(SEGMENT_SUMMARY_DELIMITER, parts);
    }

    private static List<String> cleanVideoSegmentFusedSummaryParts(String summary, boolean includeAsr) {
        if (summary == null || summary.isBlank()) {
            return List.of();
        }
        List<String> parts = new ArrayList<>();
        for (String rawPart : SEGMENT_SUMMARY_SPLITTER.split(summary)) {
            String part = rawPart.strip();
            if (part.isBlank()) {
                continue;
            }
            if (part.startsWith(SEGMENT_ASR_PREFIX)) {
                String asrText = part.substring(SEGMENT_ASR_PREFIX.length()).strip();
                if (includeAsr && !asrText.isBlank()) {
                    parts.add(COURSE_QA_ASR_PREFIX + asrText);
                }
            } else if (part.startsWith(COURSE_QA_ASR_PREFIX)) {
                String asrText = part.substring(COURSE_QA_ASR_PREFIX.length()).strip();
                if (includeAsr && !asrText.isBlank()) {
                    parts.add(COURSE_QA_ASR_PREFIX + asrText);
                }
            } else if (part.startsWith(SEGMENT_OCR_PREFIX)) {
                continue;
            } else {
                parts.add(part);
            }
        }
        return parts;
    }

    private static String cleanText(String value) {
        return value == null ? "" : value.replaceAll("\\s+", " ").strip();
    }

    private Candidate subtitleCandidate(
        SubtitleSegment row,
        SubtitleTranslationSegment translation,
        List<String> tokens,
        Optional<TimeWindow> timeWindow
    ) {
        String translated = translation == null ? "" : translation.getTranslatedText();
        double score = score(
            String.join(" ", row.getText(), translated),
            tokens,
            row.getStartMillis(),
            row.getEndMillis(),
            timeWindow,
            translated.isBlank() ? 0.85d : 0.95d,
            null
        );
        return new Candidate(score, new CourseQaEvidenceItem(
            translated.isBlank() ? "SUBTITLE" : "SUBTITLE_TRANSLATION",
            String.valueOf(row.getId()),
            row.getStartMillis(),
            row.getEndMillis(),
            formatRange(row.getStartMillis(), row.getEndMillis()),
            truncate(row.getText()),
            truncate(translated),
            null
        ));
    }

    private double score(
        String text,
        List<String> tokens,
        Long startMillis,
        Long endMillis,
        Optional<TimeWindow> timeWindow,
        double sourceWeight,
        Double confidence
    ) {
        String normalized = normalize(text);
        double keywordScore = 0.0d;
        for (String token : tokens) {
            if (normalized.contains(token)) {
                keywordScore += token.length() >= 4 ? 0.35d : 0.18d;
            }
        }
        double timeBoost = timeWindow
            .map(window -> overlaps(startMillis, endMillis, window.startMillis(), window.endMillis()) ? 0.8d : 0.0d)
            .orElse(0.0d);
        double relevanceScore = keywordScore + timeBoost;
        if (relevanceScore <= 0.0d) {
            return 0.0d;
        }
        double confidenceBoost = confidence == null ? 0.0d : Math.max(0.0d, Math.min(confidence, 1.0d)) * 0.15d;
        return relevanceScore * sourceWeight + confidenceBoost;
    }

    private Optional<TimeWindow> parseTimeWindow(String question) {
        Matcher matcher = CLOCK_TIME.matcher(question == null ? "" : question);
        List<Long> times = new ArrayList<>();
        while (matcher.find()) {
            long hours = matcher.group(1) == null ? 0L : Long.parseLong(matcher.group(1));
            long minutes = Long.parseLong(matcher.group(2));
            long seconds = Long.parseLong(matcher.group(3));
            times.add((hours * 3600L + minutes * 60L + seconds) * 1000L);
        }
        if (times.isEmpty()) {
            return Optional.empty();
        }
        long start = times.getFirst();
        long end = times.size() > 1 ? times.get(1) : start + 60000L;
        return Optional.of(new TimeWindow(Math.min(start, end), Math.max(start, end)));
    }

    private List<String> parseKeywords(String json) {
        try {
            return json == null || json.isBlank() ? List.of() : objectMapper.readValue(json, STRING_LIST_TYPE);
        } catch (Exception ignored) {
            return List.of();
        }
    }

    private static Map<Integer, SubtitleTranslationSegment> translationMap(List<SubtitleTranslationSegment> rows) {
        return rows.stream()
            .filter(row -> row.getSegmentIndex() != null)
            .collect(java.util.stream.Collectors.toMap(
                SubtitleTranslationSegment::getSegmentIndex,
                row -> row,
                (left, right) -> left,
                java.util.LinkedHashMap::new
            ));
    }

    private static boolean overlaps(Long segmentStart, Long segmentEnd, long windowStart, long windowEnd) {
        long start = segmentStart == null ? 0L : segmentStart;
        long end = segmentEnd == null ? start : segmentEnd;
        return end > windowStart && start < windowEnd;
    }

    private static String normalize(String value) {
        return value == null ? "" : value.toLowerCase(java.util.Locale.ROOT).replaceAll("\\s+", " ").strip();
    }

    private static String firstNonBlank(String... values) {
        for (String value : values) {
            if (value != null && !value.isBlank()) {
                return value.strip();
            }
        }
        return "";
    }

    private static String truncate(String value) {
        String cleaned = value == null ? "" : value.replaceAll("\\s+", " ").strip();
        return cleaned.length() <= MAX_SNIPPET ? cleaned : cleaned.substring(0, MAX_SNIPPET);
    }

    private static String formatRange(Long start, Long end) {
        return formatTime(start == null ? 0L : start) + " - " + formatTime(end == null ? 0L : end);
    }

    private static String formatTime(long millis) {
        long totalSeconds = Math.max(0L, millis / 1000L);
        long hours = totalSeconds / 3600L;
        long minutes = (totalSeconds % 3600L) / 60L;
        long seconds = totalSeconds % 60L;
        return "%02d:%02d:%02d".formatted(hours, minutes, seconds);
    }

    private record TimeWindow(long startMillis, long endMillis) {
    }

    private record Candidate(double score, CourseQaEvidenceItem item) {
    }
}
