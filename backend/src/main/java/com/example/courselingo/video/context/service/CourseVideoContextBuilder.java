package com.example.courselingo.video.context.service;

import com.example.courselingo.chapter.domain.CourseChapter;
import com.example.courselingo.chapter.mapper.CourseChapterMapper;
import com.example.courselingo.fusion.KeywordExtractor;
import com.example.courselingo.fusion.VideoSegment;
import com.example.courselingo.fusion.mapper.VideoSegmentMapper;
import com.example.courselingo.learning.domain.LearningPackage;
import com.example.courselingo.learning.mapper.LearningPackageMapper;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.subtitle.domain.SubtitleTranslationSegment;
import com.example.courselingo.subtitle.domain.TaskFullTextResult;
import com.example.courselingo.subtitle.mapper.SubtitleSegmentMapper;
import com.example.courselingo.subtitle.mapper.SubtitleTranslationSegmentMapper;
import com.example.courselingo.subtitle.mapper.TaskFullTextResultMapper;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.video.context.domain.CourseVideoChunk;
import com.example.courselingo.video.context.dto.CourseVideoContextChapterResponse;
import com.example.courselingo.video.context.dto.CourseVideoContextChunkResponse;
import com.example.courselingo.video.context.dto.CourseVideoContextEvidenceItem;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.springframework.stereotype.Service;

@Service
public class CourseVideoContextBuilder {

    private static final TypeReference<List<String>> STRING_LIST_TYPE = new TypeReference<>() {
    };

    private final SubtitleSegmentMapper subtitleSegmentMapper;
    private final SubtitleTranslationSegmentMapper translationSegmentMapper;
    private final CourseChapterMapper courseChapterMapper;
    private final LearningPackageMapper learningPackageMapper;
    private final VideoSegmentMapper videoSegmentMapper;
    private final TaskFullTextResultMapper taskFullTextResultMapper;
    private final CourseVideoContextProperties properties;
    private final ObjectMapper objectMapper;
    private final KeywordExtractor keywordExtractor = new KeywordExtractor();

    public CourseVideoContextBuilder(
        SubtitleSegmentMapper subtitleSegmentMapper,
        SubtitleTranslationSegmentMapper translationSegmentMapper,
        CourseChapterMapper courseChapterMapper,
        LearningPackageMapper learningPackageMapper,
        VideoSegmentMapper videoSegmentMapper,
        TaskFullTextResultMapper taskFullTextResultMapper,
        CourseVideoContextProperties properties,
        ObjectMapper objectMapper
    ) {
        this.subtitleSegmentMapper = Objects.requireNonNull(subtitleSegmentMapper, "subtitleSegmentMapper is required");
        this.translationSegmentMapper = Objects.requireNonNull(translationSegmentMapper, "translationSegmentMapper is required");
        this.courseChapterMapper = Objects.requireNonNull(courseChapterMapper, "courseChapterMapper is required");
        this.learningPackageMapper = Objects.requireNonNull(learningPackageMapper, "learningPackageMapper is required");
        this.videoSegmentMapper = Objects.requireNonNull(videoSegmentMapper, "videoSegmentMapper is required");
        this.taskFullTextResultMapper = Objects.requireNonNull(taskFullTextResultMapper, "taskFullTextResultMapper is required");
        this.properties = properties == null ? new CourseVideoContextProperties() : properties;
        this.objectMapper = objectMapper == null ? new ObjectMapper() : objectMapper;
    }

    public CourseVideoContextBuildResult build(AnalysisTask task) {
        SourceData source = loadSources(task);
        List<CourseVideoContextChunkResponse> chunks = buildChunks(source);
        List<CourseVideoContextChapterResponse> chapters = toChapterResponsesFromChunks(source.chapters(), chunks);
        String globalSummary = globalSummary(source);
        List<String> globalKeywords = globalKeywords(source);
        CourseVideoContextSourceSnapshot snapshot = snapshot(source, chunks.size(), chapters, globalSummary, globalKeywords);
        long durationMillis = Math.max(maxChunkEnd(chunks), maxChapterEnd(chapters));
        return new CourseVideoContextBuildResult(
            task.getId(),
            task.getTargetLanguage(),
            durationMillis,
            effectiveWindowSeconds(source.subtitles()),
            CourseVideoContextBuildVersion.VIDEO_CONTEXT_R1,
            snapshot,
            globalSummary,
            globalKeywords,
            chapters,
            chunks
        );
    }

    public CourseVideoContextSourceSnapshot snapshot(AnalysisTask task, List<CourseVideoChunk> chunks) {
        SourceData source = loadSources(task);
        List<CourseVideoContextChapterResponse> chapters = toChapterResponses(source.chapters(), chunkRanges(chunks));
        return snapshot(source, chunks == null ? 0 : chunks.size(), chapters, globalSummary(source), globalKeywords(source));
    }

    private SourceData loadSources(AnalysisTask task) {
        String targetLanguage = task.getTargetLanguage();
        List<SubtitleSegment> subtitles = safeList(subtitleSegmentMapper.selectByTaskIdAndUserId(task.getId(), task.getUserId()));
        List<SubtitleTranslationSegment> translations = safeList(
            translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage(task.getId(), task.getUserId(), targetLanguage)
        );
        List<CourseChapter> chapters = safeList(courseChapterMapper.selectByTaskIdAndUserId(task.getId(), task.getUserId()));
        LearningPackage learningPackage = learningPackageMapper.selectByTaskIdUserIdAndTargetLanguage(task.getId(), task.getUserId(), targetLanguage);
        List<VideoSegment> videoSegments = safeList(videoSegmentMapper.selectByTaskIdAndUserId(task.getId(), task.getUserId()));
        TaskFullTextResult fullText = taskFullTextResultMapper.selectByTaskIdUserIdAndTargetLanguage(
            task.getId(),
            task.getUserId(),
            targetLanguage
        );
        return new SourceData(subtitles, translations, chapters, learningPackage, videoSegments, fullText);
    }

    private List<CourseVideoContextChunkResponse> buildChunks(SourceData source) {
        if (source.subtitles().isEmpty()) {
            return List.of();
        }
        Map<Integer, SubtitleTranslationSegment> translationMap = translationMap(source.translations());
        int windowSeconds = effectiveWindowSeconds(source.subtitles());
        long windowMillis = windowSeconds * 1000L;
        long firstStart = source.subtitles().stream().mapToLong(row -> safeStart(row.getStartMillis())).min().orElse(0L);
        long lastEnd = source.subtitles().stream().mapToLong(row -> safeEnd(row.getStartMillis(), row.getEndMillis())).max().orElse(firstStart);
        List<CourseVideoContextChunkResponse> chunks = new ArrayList<>();
        int index = 0;
        for (long start = firstStart; start < lastEnd && chunks.size() < Math.max(1, properties.getMaxChunks()); start += windowMillis) {
            long end = Math.min(start + windowMillis, lastEnd);
            CourseVideoContextChunkResponse chunk = toChunk(index, start, end, source, translationMap);
            if (!isBlank(chunk.sourceTextPreview()) || !isBlank(chunk.translatedTextPreview())) {
                chunks.add(chunk);
                index++;
            }
        }
        return chunks;
    }

    private CourseVideoContextChunkResponse toChunk(
        int index,
        long start,
        long end,
        SourceData source,
        Map<Integer, SubtitleTranslationSegment> translationMap
    ) {
        List<SubtitleSegment> subtitles = source.subtitles().stream()
            .filter(segment -> overlaps(start, end, safeStart(segment.getStartMillis()), safeEnd(segment.getStartMillis(), segment.getEndMillis())))
            .sorted(Comparator.comparingInt(segment -> segment.getSegmentIndex() == null ? 0 : segment.getSegmentIndex()))
            .toList();
        String sourcePreview = truncate(joinTexts(subtitles.stream().map(SubtitleSegment::getText).toList()), properties.getSourcePreviewChars());
        String translatedPreview = truncate(joinTexts(subtitles.stream()
            .map(segment -> translationMap.get(segment.getSegmentIndex()))
            .filter(Objects::nonNull)
            .map(SubtitleTranslationSegment::getTranslatedText)
            .toList()), properties.getTranslatedPreviewChars());
        String asrPreview = truncate(asrForWindow(source.videoSegments(), start, end), properties.getSourcePreviewChars());
        String sourceWithAsr = appendLimited(sourcePreview, asrPreview, properties.getSourcePreviewChars());
        List<CourseVideoContextEvidenceItem> evidence = subtitles.stream()
            .limit(Math.max(1, properties.getEvidenceMaxItemsPerChunk()))
            .map(segment -> toEvidence(segment, translationMap.get(segment.getSegmentIndex())))
            .toList();
        CourseChapter chapter = coveringChapter(source.chapters(), start, end);
        String summary = summaryForChunk(chapter, translatedPreview, sourceWithAsr);
        List<String> keywords = keywordsForChunk(chapter, translatedPreview, sourceWithAsr);
        return new CourseVideoContextChunkResponse(
            index,
            start,
            end,
            formatRange(start, end),
            summary,
            keywords,
            sourceWithAsr,
            translatedPreview,
            evidence
        );
    }

    private CourseVideoContextEvidenceItem toEvidence(SubtitleSegment segment, SubtitleTranslationSegment translation) {
        long start = safeStart(segment.getStartMillis());
        long end = safeEnd(segment.getStartMillis(), segment.getEndMillis());
        return new CourseVideoContextEvidenceItem(
            "SUBTITLE",
            segment.getSegmentIndex(),
            start,
            end,
            formatRange(start, end),
            truncate(cleanText(segment.getText()), 500),
            truncate(cleanText(translation == null ? "" : translation.getTranslatedText()), 500)
        );
    }

    private CourseVideoContextSourceSnapshot snapshot(
        SourceData source,
        int chunkCount,
        List<CourseVideoContextChapterResponse> chapters,
        String globalSummary,
        List<String> globalKeywords
    ) {
        return new CourseVideoContextSourceSnapshot(
            source.subtitles().size(),
            source.translations().size(),
            source.chapters().size(),
            chunkCount,
            source.learningPackage() != null,
            source.videoSegments().stream().anyMatch(segment -> !isBlank(segment.getAsrText())),
            LocalDateTime.now(),
            chapters,
            globalSummary,
            globalKeywords
        );
    }

    private List<CourseVideoContextChapterResponse> toChapterResponses(
        List<CourseChapter> chapters,
        List<? extends ChunkRange> chunks
    ) {
        return safeList(chapters).stream()
            .sorted(Comparator.comparingInt(chapter -> chapter.getChapterIndex() == null ? 0 : chapter.getChapterIndex()))
            .map(chapter -> new CourseVideoContextChapterResponse(
                chapter.getChapterIndex(),
                cleanText(chapter.getTitle()),
                cleanText(chapter.getSummary()),
                readStringList(chapter.getKeywordsJson()),
                safeStart(chapter.getStartMillis()),
                safeEnd(chapter.getStartMillis(), chapter.getEndMillis()),
                coveredChunkIndexes(chapter, chunks)
            ))
            .toList();
    }

    private List<CourseVideoContextChapterResponse> toChapterResponsesFromChunks(
        List<CourseChapter> chapters,
        List<CourseVideoContextChunkResponse> chunks
    ) {
        return toChapterResponses(chapters, chunks.stream()
            .map(chunk -> new ChunkRange(chunk.chunkIndex(), chunk.startMillis(), chunk.endMillis()))
            .toList());
    }

    private List<ChunkRange> chunkRanges(List<CourseVideoChunk> chunks) {
        return safeList(chunks).stream()
            .map(chunk -> new ChunkRange(chunk.getChunkIndex(), chunk.getStartMillis(), chunk.getEndMillis()))
            .toList();
    }

    private List<Integer> coveredChunkIndexes(CourseChapter chapter, List<? extends ChunkRange> chunks) {
        long start = safeStart(chapter.getStartMillis());
        long end = safeEnd(chapter.getStartMillis(), chapter.getEndMillis());
        return chunks.stream()
            .filter(chunk -> overlaps(start, end, safeStart(chunk.startMillis()), safeEnd(chunk.startMillis(), chunk.endMillis())))
            .map(ChunkRange::chunkIndex)
            .filter(Objects::nonNull)
            .toList();
    }

    private String summaryForChunk(CourseChapter chapter, String translatedPreview, String sourcePreview) {
        String base = !isBlank(translatedPreview) ? translatedPreview : sourcePreview;
        if (chapter != null) {
            String chapterText = String.join("：", cleanText(chapter.getTitle()), cleanText(chapter.getSummary()));
            base = appendLimited(chapterText, base, properties.getSummaryMaxChars());
        }
        return truncate(base, properties.getSummaryMaxChars());
    }

    private List<String> keywordsForChunk(CourseChapter chapter, String translatedPreview, String sourcePreview) {
        LinkedHashSet<String> result = new LinkedHashSet<>();
        if (chapter != null) {
            result.addAll(readStringList(chapter.getKeywordsJson()));
        }
        result.addAll(keywordExtractor.extract(translatedPreview + " " + sourcePreview, properties.getKeywordMaxCount()));
        return result.stream()
            .filter(keyword -> !isBlank(keyword))
            .limit(Math.max(1, properties.getKeywordMaxCount()))
            .toList();
    }

    private List<String> globalKeywords(SourceData source) {
        Set<String> result = new LinkedHashSet<>();
        LearningPackage learningPackage = source.learningPackage();
        if (learningPackage != null) {
            result.addAll(readGlossaryTerms(learningPackage.getGlossaryJson()));
            result.addAll(keywordExtractor.extract(learningPackage.getSummary(), properties.getKeywordMaxCount()));
        }
        if (result.isEmpty()) {
            result.addAll(keywordExtractor.extract(source.fullTextText(), properties.getKeywordMaxCount()));
        }
        return result.stream().limit(Math.max(1, properties.getKeywordMaxCount())).toList();
    }

    private String globalSummary(SourceData source) {
        LearningPackage learningPackage = source.learningPackage();
        if (learningPackage != null && !isBlank(learningPackage.getSummary())) {
            return truncate(learningPackage.getSummary(), properties.getSummaryMaxChars());
        }
        return truncate(source.fullTextText(), properties.getSummaryMaxChars());
    }

    private CourseChapter coveringChapter(List<CourseChapter> chapters, long start, long end) {
        return safeList(chapters).stream()
            .filter(chapter -> overlaps(start, end, safeStart(chapter.getStartMillis()), safeEnd(chapter.getStartMillis(), chapter.getEndMillis())))
            .findFirst()
            .orElse(null);
    }

    private int effectiveWindowSeconds(List<SubtitleSegment> subtitles) {
        int configured = Math.max(1, properties.getChunkWindowSeconds());
        int maxChunks = Math.max(1, properties.getMaxChunks());
        if (subtitles == null || subtitles.isEmpty()) {
            return configured;
        }
        long first = subtitles.stream().mapToLong(row -> safeStart(row.getStartMillis())).min().orElse(0L);
        long last = subtitles.stream().mapToLong(row -> safeEnd(row.getStartMillis(), row.getEndMillis())).max().orElse(first);
        long durationMillis = Math.max(1L, last - first);
        long configuredMillis = configured * 1000L;
        long estimatedChunks = (durationMillis + configuredMillis - 1L) / configuredMillis;
        if (estimatedChunks <= maxChunks) {
            return configured;
        }
        return (int) Math.max(configured, (durationMillis + maxChunks * 1000L - 1L) / (maxChunks * 1000L));
    }

    private String asrForWindow(List<VideoSegment> segments, long start, long end) {
        return joinTexts(safeList(segments).stream()
            .filter(segment -> overlaps(start, end, safeStart(segment.getStartMillis()), safeEnd(segment.getStartMillis(), segment.getEndMillis())))
            .map(VideoSegment::getAsrText)
            .toList());
    }

    private Map<Integer, SubtitleTranslationSegment> translationMap(List<SubtitleTranslationSegment> translations) {
        Map<Integer, SubtitleTranslationSegment> map = new LinkedHashMap<>();
        for (SubtitleTranslationSegment translation : safeList(translations)) {
            if (translation.getSegmentIndex() != null) {
                map.putIfAbsent(translation.getSegmentIndex(), translation);
            }
        }
        return map;
    }

    private List<String> readStringList(String json) {
        try {
            return isBlank(json) ? List.of() : objectMapper.readValue(json, STRING_LIST_TYPE);
        } catch (Exception ignored) {
            return List.of();
        }
    }

    private List<String> readGlossaryTerms(String json) {
        if (isBlank(json)) {
            return List.of();
        }
        try {
            JsonNode node = objectMapper.readTree(json);
            List<String> terms = new ArrayList<>();
            if (node.isArray()) {
                for (JsonNode item : node) {
                    String term = item.hasNonNull("term") ? item.get("term").asText("") : item.asText("");
                    if (!isBlank(term)) {
                        terms.add(term);
                    }
                }
            }
            return terms;
        } catch (Exception ignored) {
            return List.of();
        }
    }

    private static String joinTexts(List<String> values) {
        return cleanText(String.join(" ", safeList(values).stream().map(CourseVideoContextBuilder::cleanText).toList()));
    }

    private static String appendLimited(String current, String next, int limit) {
        String left = cleanText(current);
        String right = cleanText(next);
        if (right.isBlank()) {
            return truncate(left, limit);
        }
        if (left.isBlank()) {
            return truncate(right, limit);
        }
        return truncate(left + " " + right, limit);
    }

    private static boolean overlaps(long leftStart, long leftEnd, long rightStart, long rightEnd) {
        return leftEnd > rightStart && rightEnd > leftStart;
    }

    private static long maxChunkEnd(List<CourseVideoContextChunkResponse> chunks) {
        return safeList(chunks).stream().mapToLong(chunk -> safeStart(chunk.endMillis())).max().orElse(0L);
    }

    private static long maxChapterEnd(List<CourseVideoContextChapterResponse> chapters) {
        return safeList(chapters).stream().mapToLong(chapter -> safeStart(chapter.endMillis())).max().orElse(0L);
    }

    private static long safeStart(Long value) {
        return Math.max(0L, value == null ? 0L : value);
    }

    private static long safeEnd(Long start, Long end) {
        long safeStart = safeStart(start);
        return end == null ? safeStart + 1000L : Math.max(safeStart + 1L, end);
    }

    private static String cleanText(String value) {
        return value == null ? "" : value.replaceAll("\\s+", " ").strip();
    }

    private static String truncate(String value, int limit) {
        String cleaned = cleanText(value);
        int safeLimit = Math.max(0, limit);
        return cleaned.length() <= safeLimit ? cleaned : cleaned.substring(0, safeLimit);
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private static String formatRange(long start, long end) {
        return formatTime(start) + " - " + formatTime(end);
    }

    private static String formatTime(long millis) {
        long totalSeconds = Math.max(0L, millis / 1000L);
        long hours = totalSeconds / 3600L;
        long minutes = (totalSeconds % 3600L) / 60L;
        long seconds = totalSeconds % 60L;
        return "%02d:%02d:%02d".formatted(hours, minutes, seconds);
    }

    private static <T> List<T> safeList(List<T> rows) {
        return rows == null ? List.of() : rows;
    }

    private record SourceData(
        List<SubtitleSegment> subtitles,
        List<SubtitleTranslationSegment> translations,
        List<CourseChapter> chapters,
        LearningPackage learningPackage,
        List<VideoSegment> videoSegments,
        TaskFullTextResult fullText
    ) {
        private String fullTextText() {
            if (fullText == null) {
                return "";
            }
            return String.join(" ", cleanText(fullText.getTranslatedFullText()), cleanText(fullText.getSourceFullText()));
        }
    }

    private record ChunkRange(Integer chunkIndex, Long startMillis, Long endMillis) {
    }
}
