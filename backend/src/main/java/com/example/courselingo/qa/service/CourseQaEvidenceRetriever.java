package com.example.courselingo.qa.service;

import com.example.courselingo.fusion.VideoSegment;
import com.example.courselingo.fusion.mapper.VideoSegmentMapper;
import com.example.courselingo.qa.dto.CourseQaEvidenceItem;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.subtitle.domain.SubtitleTranslationSegment;
import com.example.courselingo.subtitle.mapper.SubtitleSegmentMapper;
import com.example.courselingo.subtitle.mapper.SubtitleTranslationSegmentMapper;
import com.example.courselingo.vision.ocr.OcrTextQualityEvaluator;
import com.example.courselingo.vision.ocr.mapper.VideoKeyframeOcrMapper;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class CourseQaEvidenceRetriever {

    private static final int MAX_CANDIDATES = 100;
    private static final int MAX_EVIDENCE = 8;
    private static final int MAX_OVERVIEW_EVIDENCE = 6;
    private static final int MAX_TIME_EVIDENCE = 4;
    private static final int MAX_SNIPPET = 500;
    private static final String SEGMENT_ASR_PREFIX = "\u672c\u6bb5\u4e3b\u8981\u8bb2\u89e3\uff1a";
    private static final String COURSE_QA_ASR_PREFIX = "\u672c\u6bb5\u8bed\u97f3\u539f\u6587\uff1a";
    private static final String SEGMENT_TRANSLATION_PREFIX = "\u5b57\u5e55\u8bd1\u6587\uff1a";
    private static final String SEGMENT_OCR_PREFIX = "\u753b\u9762\u6587\u5b57\u5305\u62ec\uff1a";
    private static final String SEGMENT_VISUAL_PREFIX = "\u753b\u9762\u663e\u793a\uff1a";
    private static final String SEGMENT_SUMMARY_DELIMITER = "\uff1b";
    private static final Pattern SEGMENT_SUMMARY_SPLITTER = Pattern.compile("[\uff1b;\\r\\n]+");
    private static final Pattern CLOCK_TIME = Pattern.compile("\\b(?:(\\d{1,2}):)?(\\d{1,2}):(\\d{2})\\b");
    private static final Pattern NATURAL_MINUTE = Pattern.compile(
        "(?<!\\d)(\\d{1,3})\\s*分钟(?:\\s*(?:附近|左右|前后))?"
    );
    private static final Pattern NATURAL_ENGLISH_TIME = Pattern.compile(
        "(?i)(?<!\\d)(\\d{1,5})\\s*(seconds?|secs?|minutes?|mins?)\\b"
    );
    private static final Pattern OVERVIEW_INTENT = Pattern.compile(
        "(?:主要讲了什么|主要内容|课程概述|课程总结|总结这节|概括这节|what\\s+is\\s+this\\s+(?:course|lesson)\\s+about)",
        Pattern.CASE_INSENSITIVE
    );
    private static final Pattern COMPARABLE_TOKEN = Pattern.compile("[\\p{IsHan}]{2}|[a-z0-9+#._-]{2,}");
    private static final Pattern DASH_SEPARATOR = Pattern.compile("[\\p{Pd}\\u2212]+");
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
        boolean overview = timeWindow.isEmpty() && tokens.isEmpty() && isOverviewQuestion(question);
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
        List<Candidate> ranked = candidates.stream()
            .filter(candidate -> overview || candidate.score() > 0.0d)
            .sorted(java.util.Comparator.comparingDouble(Candidate::score).reversed()
                .thenComparing(candidate -> nullableLong(candidate.item().startTimeMillis()))
                .thenComparing(candidate -> cleanText(candidate.item().sourceType()))
                .thenComparing(candidate -> cleanText(candidate.item().sourceId())))
            .limit(MAX_CANDIDATES)
            .toList();
        if (overview) {
            return evenlyDistributedOverview(ranked);
        }
        int limit = timeWindow.isPresent() ? MAX_TIME_EVIDENCE : MAX_EVIDENCE;
        return semanticallyDistinct(ranked.stream().map(Candidate::item).toList(), limit);
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
            String.join(" ", snippet, String.join(" ", parseKeywords(row.getKeywordsJson()))),
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
        String translatedText = cleanText(row.getTranslatedText());
        boolean hasStructuredTranslation = !translatedText.isBlank();
        if (hasStructuredTranslation) {
            parts.add(SEGMENT_TRANSLATION_PREFIX + translatedText);
        }
        String ocrText = cleanOcrText(row.getOcrText());
        boolean hasStructuredOcr = usefulOcr(ocrText);
        if (hasStructuredOcr) {
            parts.add(SEGMENT_OCR_PREFIX + ocrText);
        }
        String visualSummary = cleanText(row.getVisualSummary());
        boolean hasStructuredVisual = !visualSummary.isBlank();
        if (!visualSummary.isBlank()) {
            parts.add(SEGMENT_VISUAL_PREFIX + visualSummary);
        }
        cleanVideoSegmentFusedSummaryParts(
            row.getFusedSummary(),
            !hasStructuredAsr,
            !hasStructuredTranslation,
            !hasStructuredOcr,
            !hasStructuredVisual
        ).stream()
            .filter(part -> !parts.contains(part))
            .forEach(parts::add);
        return String.join(SEGMENT_SUMMARY_DELIMITER, parts);
    }

    private static List<String> cleanVideoSegmentFusedSummaryParts(
        String summary,
        boolean includeAsr,
        boolean includeTranslation,
        boolean includeOcr,
        boolean includeVisual
    ) {
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
            } else if (part.startsWith(SEGMENT_TRANSLATION_PREFIX)) {
                String translatedText = part.substring(SEGMENT_TRANSLATION_PREFIX.length()).strip();
                if (includeTranslation && !translatedText.isBlank()) {
                    parts.add(SEGMENT_TRANSLATION_PREFIX + translatedText);
                }
            } else if (part.startsWith(SEGMENT_OCR_PREFIX)) {
                String ocrText = part.substring(SEGMENT_OCR_PREFIX.length()).strip();
                if (includeOcr && usefulOcr(ocrText)) {
                    parts.add(SEGMENT_OCR_PREFIX + ocrText);
                }
            } else if (part.startsWith(SEGMENT_VISUAL_PREFIX)) {
                String visualText = part.substring(SEGMENT_VISUAL_PREFIX.length()).strip();
                if (includeVisual && !visualText.isBlank()) {
                    parts.add(SEGMENT_VISUAL_PREFIX + visualText);
                }
            } else {
                parts.add(part);
            }
        }
        return parts;
    }

    private static String cleanText(String value) {
        return value == null ? "" : value.replaceAll("\\s+", " ").strip();
    }

    private static boolean usefulOcr(String value) {
        String cleaned = cleanOcrText(value);
        return !cleaned.isBlank() && OcrTextQualityEvaluator.isUseful(cleaned, null);
    }

    private static String cleanOcrText(String value) {
        String cleaned = cleanText(value);
        for (String prefix : List.of(SEGMENT_OCR_PREFIX, "画面文字：")) {
            if (cleaned.startsWith(prefix)) {
                return cleanText(cleaned.substring(prefix.length()));
            }
        }
        return cleaned;
    }

    private static long nullableLong(Long value) {
        return value == null ? Long.MAX_VALUE : value;
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
        int matchedTerms = 0;
        boolean matchedExactPhrase = false;
        for (String token : tokens) {
            String normalizedToken = normalize(token);
            if (!normalizedToken.isBlank() && normalized.contains(normalizedToken)) {
                keywordScore += token.length() >= 4 ? 0.35d : 0.18d;
                matchedTerms++;
                matchedExactPhrase = matchedExactPhrase || normalizedToken.indexOf(' ') >= 0;
            }
        }
        if (tokens.size() > 1 && matchedTerms < 2 && !matchedExactPhrase) {
            keywordScore = 0.0d;
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
        String safeQuestion = question == null ? "" : question;
        Matcher matcher = CLOCK_TIME.matcher(safeQuestion);
        List<Long> times = new ArrayList<>();
        while (matcher.find()) {
            long hours = matcher.group(1) == null ? 0L : Long.parseLong(matcher.group(1));
            long minutes = Long.parseLong(matcher.group(2));
            long seconds = Long.parseLong(matcher.group(3));
            times.add((hours * 3600L + minutes * 60L + seconds) * 1000L);
        }
        if (!times.isEmpty()) {
            long start = times.getFirst();
            long end;
            if (times.size() > 1) {
                end = times.get(1);
            } else if (containsNearbyWord(safeQuestion)) {
                return Optional.of(new TimeWindow(Math.max(0L, start - 60_000L), start + 60_000L));
            } else {
                end = start + 60_000L;
            }
            return Optional.of(new TimeWindow(Math.min(start, end), Math.max(start, end)));
        }
        Matcher naturalMinute = NATURAL_MINUTE.matcher(safeQuestion);
        if (naturalMinute.find()) {
            long center = Long.parseLong(naturalMinute.group(1)) * 60_000L;
            return Optional.of(new TimeWindow(Math.max(0L, center - 60_000L), center + 60_000L));
        }
        Matcher naturalEnglishTime = NATURAL_ENGLISH_TIME.matcher(safeQuestion);
        if (!naturalEnglishTime.find()) {
            return Optional.empty();
        }
        long unitMillis = naturalEnglishTime.group(2).toLowerCase(java.util.Locale.ROOT).startsWith("m")
            ? 60_000L
            : 1_000L;
        long center = Long.parseLong(naturalEnglishTime.group(1)) * unitMillis;
        return Optional.of(new TimeWindow(Math.max(0L, center - 60_000L), center + 60_000L));
    }

    private static boolean containsNearbyWord(String question) {
        return question.contains("附近") || question.contains("左右") || question.contains("前后");
    }

    private static boolean isOverviewQuestion(String question) {
        return OVERVIEW_INTENT.matcher(question == null ? "" : question).find();
    }

    private static List<CourseQaEvidenceItem> evenlyDistributedOverview(List<Candidate> ranked) {
        List<CourseQaEvidenceItem> preferred = ranked.stream()
            .map(Candidate::item)
            .filter(CourseQaEvidenceRetriever::hasEvidenceText)
            .filter(item -> "VIDEO_SEGMENT".equals(item.sourceType()))
            .sorted(java.util.Comparator.comparingLong(item -> nullableLong(item.startTimeMillis())))
            .toList();
        if (preferred.isEmpty()) {
            preferred = ranked.stream()
                .map(Candidate::item)
                .filter(CourseQaEvidenceRetriever::hasEvidenceText)
                .sorted(java.util.Comparator.comparingLong(item -> nullableLong(item.startTimeMillis())))
                .toList();
        }
        List<CourseQaEvidenceItem> sampled = new ArrayList<>();
        int target = Math.min(MAX_OVERVIEW_EVIDENCE, preferred.size());
        for (int index = 0; index < target; index++) {
            int sourceIndex = target == 1
                ? 0
                : (int) Math.round(index * (preferred.size() - 1.0d) / (target - 1.0d));
            CourseQaEvidenceItem item = preferred.get(sourceIndex);
            if (sampled.stream().noneMatch(existing -> semanticallySimilar(existing, item))) {
                sampled.add(item);
            }
        }
        return List.copyOf(sampled);
    }

    private static List<CourseQaEvidenceItem> semanticallyDistinct(
        List<CourseQaEvidenceItem> ranked,
        int limit
    ) {
        List<CourseQaEvidenceItem> selected = new ArrayList<>();
        for (CourseQaEvidenceItem item : ranked) {
            if (!hasEvidenceText(item) || selected.stream().anyMatch(existing -> semanticallySimilar(existing, item))) {
                continue;
            }
            selected.add(item);
            if (selected.size() >= limit) {
                break;
            }
        }
        return List.copyOf(selected);
    }

    private static boolean semanticallySimilar(CourseQaEvidenceItem left, CourseQaEvidenceItem right) {
        if (!overlaps(
            left.startTimeMillis(),
            left.endTimeMillis(),
            right.startTimeMillis() == null ? 0L : right.startTimeMillis(),
            right.endTimeMillis() == null
                ? (right.startTimeMillis() == null ? 0L : right.startTimeMillis())
                : right.endTimeMillis()
        )) {
            return false;
        }
        String leftText = comparableText(left);
        String rightText = comparableText(right);
        if (leftText.isBlank() || rightText.isBlank()) {
            return false;
        }
        int shorter = Math.min(leftText.length(), rightText.length());
        if (shorter >= 20 && (leftText.contains(rightText) || rightText.contains(leftText))) {
            return true;
        }
        Set<String> leftTokens = comparableTokens(leftText);
        Set<String> rightTokens = comparableTokens(rightText);
        if (leftTokens.isEmpty() || rightTokens.isEmpty()) {
            return leftText.equals(rightText);
        }
        long intersection = leftTokens.stream().filter(rightTokens::contains).count();
        double containment = intersection / (double) Math.min(leftTokens.size(), rightTokens.size());
        return containment >= 0.8d;
    }

    private static String comparableText(CourseQaEvidenceItem item) {
        return normalize(firstNonBlank(item.translatedSnippet(), item.snippet()))
            .replaceAll("(?:本段语音原文|字幕译文|画面文字包括|画面显示)[:：]", " ")
            .replaceAll("[^\\p{IsHan}a-z0-9+#._-]+", " ")
            .strip();
    }

    private static Set<String> comparableTokens(String text) {
        LinkedHashSet<String> tokens = new LinkedHashSet<>();
        Matcher matcher = COMPARABLE_TOKEN.matcher(text);
        while (matcher.find()) {
            tokens.add(matcher.group());
        }
        return tokens;
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
        if (value == null) {
            return "";
        }
        return DASH_SEPARATOR.matcher(Normalizer.normalize(value, Normalizer.Form.NFKC)
                .toLowerCase(java.util.Locale.ROOT))
            .replaceAll(" ")
            .replaceAll("\\s+", " ")
            .strip();
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
