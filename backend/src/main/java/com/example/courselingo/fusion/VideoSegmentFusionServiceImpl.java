package com.example.courselingo.fusion;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.fusion.mapper.VideoSegmentMapper;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.subtitle.domain.SubtitleTranslationSegment;
import com.example.courselingo.subtitle.mapper.SubtitleSegmentMapper;
import com.example.courselingo.subtitle.mapper.SubtitleTranslationSegmentMapper;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.task.model.AnalysisTaskStatus;
import com.example.courselingo.vision.analysis.VideoKeyframeAnalysis;
import com.example.courselingo.vision.analysis.VisionAnalysisStatus;
import com.example.courselingo.vision.analysis.mapper.VideoKeyframeAnalysisMapper;
import com.example.courselingo.vision.keyframe.VideoKeyframe;
import com.example.courselingo.vision.keyframe.mapper.VideoKeyframeMapper;
import com.example.courselingo.vision.ocr.OcrStatus;
import com.example.courselingo.vision.ocr.OcrTextQualityEvaluator;
import com.example.courselingo.vision.ocr.VideoKeyframeOcr;
import com.example.courselingo.vision.ocr.mapper.VideoKeyframeOcrMapper;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class VideoSegmentFusionServiceImpl implements VideoSegmentService {

    private static final TypeReference<List<String>> STRING_LIST_TYPE = new TypeReference<>() {
    };
    private static final TypeReference<VideoSegmentEvidence> EVIDENCE_TYPE = new TypeReference<>() {
    };

    private final VideoSegmentMapper videoSegmentMapper;
    private final SubtitleSegmentMapper subtitleSegmentMapper;
    private final SubtitleTranslationSegmentMapper translationSegmentMapper;
    private final VideoKeyframeMapper keyframeMapper;
    private final VideoKeyframeOcrMapper ocrMapper;
    private final VideoKeyframeAnalysisMapper analysisMapper;
    private final VideoSegmentProperties properties;
    private final ObjectMapper objectMapper;
    private final Clock clock;
    private final CurrentUserService currentUserService;
    private final AnalysisTaskMapper analysisTaskMapper;
    private final KeywordExtractor keywordExtractor;

    @Autowired
    public VideoSegmentFusionServiceImpl(
        VideoSegmentMapper videoSegmentMapper,
        SubtitleSegmentMapper subtitleSegmentMapper,
        SubtitleTranslationSegmentMapper translationSegmentMapper,
        VideoKeyframeMapper keyframeMapper,
        VideoKeyframeOcrMapper ocrMapper,
        VideoKeyframeAnalysisMapper analysisMapper,
        VideoSegmentProperties properties,
        ObjectMapper objectMapper,
        CurrentUserService currentUserService,
        AnalysisTaskMapper analysisTaskMapper
    ) {
        this(
            videoSegmentMapper,
            subtitleSegmentMapper,
            translationSegmentMapper,
            keyframeMapper,
            ocrMapper,
            analysisMapper,
            properties,
            objectMapper,
            Clock.systemUTC(),
            currentUserService,
            analysisTaskMapper
        );
    }

    public VideoSegmentFusionServiceImpl(
        VideoSegmentMapper videoSegmentMapper,
        SubtitleSegmentMapper subtitleSegmentMapper,
        SubtitleTranslationSegmentMapper translationSegmentMapper,
        VideoKeyframeMapper keyframeMapper,
        VideoKeyframeOcrMapper ocrMapper,
        VideoKeyframeAnalysisMapper analysisMapper,
        VideoSegmentProperties properties,
        ObjectMapper objectMapper,
        Clock clock
    ) {
        this(
            videoSegmentMapper,
            subtitleSegmentMapper,
            translationSegmentMapper,
            keyframeMapper,
            ocrMapper,
            analysisMapper,
            properties,
            objectMapper,
            clock,
            null,
            null
        );
    }

    public VideoSegmentFusionServiceImpl(
        VideoSegmentMapper videoSegmentMapper,
        SubtitleSegmentMapper subtitleSegmentMapper,
        VideoKeyframeMapper keyframeMapper,
        VideoKeyframeOcrMapper ocrMapper,
        VideoKeyframeAnalysisMapper analysisMapper,
        VideoSegmentProperties properties,
        ObjectMapper objectMapper,
        CurrentUserService currentUserService,
        AnalysisTaskMapper analysisTaskMapper
    ) {
        this(
            videoSegmentMapper,
            subtitleSegmentMapper,
            null,
            keyframeMapper,
            ocrMapper,
            analysisMapper,
            properties,
            objectMapper,
            Clock.systemUTC(),
            currentUserService,
            analysisTaskMapper
        );
    }

    public VideoSegmentFusionServiceImpl(
        VideoSegmentMapper videoSegmentMapper,
        SubtitleSegmentMapper subtitleSegmentMapper,
        VideoKeyframeMapper keyframeMapper,
        VideoKeyframeOcrMapper ocrMapper,
        VideoKeyframeAnalysisMapper analysisMapper,
        VideoSegmentProperties properties,
        ObjectMapper objectMapper,
        Clock clock
    ) {
        this(
            videoSegmentMapper,
            subtitleSegmentMapper,
            null,
            keyframeMapper,
            ocrMapper,
            analysisMapper,
            properties,
            objectMapper,
            clock,
            null,
            null
        );
    }

    private VideoSegmentFusionServiceImpl(
        VideoSegmentMapper videoSegmentMapper,
        SubtitleSegmentMapper subtitleSegmentMapper,
        SubtitleTranslationSegmentMapper translationSegmentMapper,
        VideoKeyframeMapper keyframeMapper,
        VideoKeyframeOcrMapper ocrMapper,
        VideoKeyframeAnalysisMapper analysisMapper,
        VideoSegmentProperties properties,
        ObjectMapper objectMapper,
        Clock clock,
        CurrentUserService currentUserService,
        AnalysisTaskMapper analysisTaskMapper
    ) {
        this.videoSegmentMapper = Objects.requireNonNull(videoSegmentMapper, "videoSegmentMapper is required");
        this.subtitleSegmentMapper = Objects.requireNonNull(subtitleSegmentMapper, "subtitleSegmentMapper is required");
        this.translationSegmentMapper = translationSegmentMapper;
        this.keyframeMapper = Objects.requireNonNull(keyframeMapper, "keyframeMapper is required");
        this.ocrMapper = ocrMapper;
        this.analysisMapper = analysisMapper;
        this.properties = properties == null ? new VideoSegmentProperties() : properties;
        this.objectMapper = objectMapper == null ? new ObjectMapper() : objectMapper;
        this.clock = clock == null ? Clock.systemUTC() : clock;
        this.currentUserService = currentUserService;
        this.analysisTaskMapper = analysisTaskMapper;
        this.keywordExtractor = new KeywordExtractor();
    }

    @Override
    @Transactional
    public VideoSegmentFusionResult fuse(String taskId, Long userId) {
        return fuseInternal(taskId, userId, false);
    }

    private VideoSegmentFusionResult fuseInternal(String taskId, Long userId, boolean forceRebuild) {
        if (!forceRebuild && !properties.isEnabled()) {
            return new VideoSegmentFusionResult(0, 0, 0, 0);
        }
        String normalizedTaskId = normalizeTaskId(taskId);
        if (userId == null) {
            throw new IllegalArgumentException("userId is required");
        }
        List<SubtitleSegment> subtitles = properties.isIncludeAsr()
            ? sortedSubtitles(subtitleSegmentMapper.selectByTaskIdAndUserId(normalizedTaskId, userId))
            : List.of();
        List<SubtitleTranslationSegment> translations = sortedTranslations(loadTranslations(normalizedTaskId, userId));
        List<VideoKeyframe> keyframes = sortedKeyframes(keyframeMapper.selectByTaskIdAndUserId(normalizedTaskId, userId));
        List<Long> keyframeIds = keyframes.stream().map(VideoKeyframe::getId).filter(Objects::nonNull).toList();
        List<VideoKeyframeOcr> ocrRows = properties.isIncludeOcr() && ocrMapper != null
            ? sortedOcrRows(ocrMapper.selectByKeyframeIds(normalizedTaskId, userId, keyframeIds))
            : List.of();
        List<VideoKeyframeAnalysis> analysisRows = properties.isIncludeVision() && analysisMapper != null
            ? sortedAnalysisRows(analysisMapper.selectByKeyframeIds(normalizedTaskId, userId, keyframeIds))
            : List.of();
        long windowMillis = Math.max(1L, properties.getWindowSeconds()) * 1000L;
        long durationMillis = durationMillis(subtitles, translations, keyframes, ocrRows, analysisRows, windowMillis);
        videoSegmentMapper.deleteByTaskIdAndUserId(normalizedTaskId, userId);
        if (durationMillis <= 0) {
            return new VideoSegmentFusionResult(0, 0, 0, 0);
        }

        int windows = (int) Math.ceil(durationMillis / (double) windowMillis);
        int boundedWindows = Math.min(windows, properties.getMaxSegments());
        int saved = 0;
        int empty = 0;
        LocalDateTime now = LocalDateTime.ofInstant(clock.instant(), clock.getZone());
        for (int index = 0; index < boundedWindows; index++) {
            long start = index * windowMillis;
            long end = Math.min(start + windowMillis, durationMillis);
            if (start < 0 || end <= start) {
                continue;
            }
            WindowData data = windowData(
                start,
                end,
                end == durationMillis,
                subtitles,
                translations,
                keyframes,
                ocrRows,
                analysisRows
            );
            if (data.isEmpty()) {
                empty++;
                continue;
            }
            if (videoSegmentMapper.insert(toEntity(normalizedTaskId, userId, index, start, end, data, now)) != 1) {
                throw new BusinessException(ErrorCode.COMMON_INTERNAL_ERROR, "Video segment persistence failed");
            }
            saved++;
        }
        int skipped = Math.max(0, windows - boundedWindows);
        return new VideoSegmentFusionResult(windows, saved, empty, skipped);
    }

    @Override
    public List<VideoSegmentResponse> listForCurrentUser(
        String authorizationHeader,
        String taskId,
        Integer limit,
        Integer offset,
        String keyword
    ) {
        if (currentUserService == null || analysisTaskMapper == null) {
            throw new UnsupportedOperationException("owner-scoped video segment query is not available");
        }
        CurrentUserResponse currentUser = currentUserService.currentUser(authorizationHeader);
        String normalizedTaskId = normalizeTaskId(taskId);
        AnalysisTask task = analysisTaskMapper.selectByIdAndUserId(normalizedTaskId, currentUser.userId());
        if (task == null) {
            throw new BusinessException(ErrorCode.TASK_NOT_FOUND);
        }
        return listByTaskId(normalizedTaskId, currentUser.userId(), limit, offset, keyword);
    }

    @Override
    @Transactional
    public VideoSegmentFusionResult rebuildForCurrentUser(String authorizationHeader, String taskId) {
        if (currentUserService == null || analysisTaskMapper == null) {
            throw new UnsupportedOperationException("owner-scoped video segment rebuild is not available");
        }
        CurrentUserResponse currentUser = currentUserService.currentUser(authorizationHeader);
        String normalizedTaskId = normalizeTaskId(taskId);
        AnalysisTask task = analysisTaskMapper.selectByIdAndUserId(normalizedTaskId, currentUser.userId());
        if (task == null) {
            throw new BusinessException(ErrorCode.TASK_NOT_FOUND);
        }
        if (!AnalysisTaskStatus.SUCCEEDED.name().equals(task.getStatus())) {
            throw new BusinessException(ErrorCode.TASK_INVALID_STATUS);
        }
        return fuseInternal(normalizedTaskId, currentUser.userId(), true);
    }

    @Override
    public List<VideoSegmentResponse> listByTaskId(String taskId, Long userId, Integer limit, Integer offset, String keyword) {
        String normalizedTaskId = normalizeTaskId(taskId);
        int safeLimit = Math.max(1, Math.min(limit == null ? 100 : limit, 300));
        int safeOffset = Math.max(0, offset == null ? 0 : offset);
        String normalizedKeyword = keyword == null ? "" : keyword.strip().toLowerCase(Locale.ROOT);
        return videoSegmentMapper.selectByTaskIdAndUserId(normalizedTaskId, userId).stream()
            .map(this::toResponse)
            .filter(view -> normalizedKeyword.isBlank() || matchesKeyword(view, normalizedKeyword))
            .skip(safeOffset)
            .limit(safeLimit)
            .toList();
    }

    private List<SubtitleTranslationSegment> loadTranslations(String taskId, Long userId) {
        if (translationSegmentMapper == null || analysisTaskMapper == null) {
            return List.of();
        }
        AnalysisTask task = analysisTaskMapper.selectByIdAndUserId(taskId, userId);
        if (task == null || task.getTargetLanguage() == null || task.getTargetLanguage().isBlank()) {
            return List.of();
        }
        List<SubtitleTranslationSegment> rows = translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage(
            taskId,
            userId,
            task.getTargetLanguage()
        );
        return rows == null ? List.of() : rows;
    }

    private static List<SubtitleSegment> sortedSubtitles(List<SubtitleSegment> rows) {
        return safeList(rows).stream()
            .filter(Objects::nonNull)
            .sorted(Comparator
                .comparing(SubtitleSegment::getStartMillis, Comparator.nullsLast(Long::compareTo))
                .thenComparing(SubtitleSegment::getSegmentIndex, Comparator.nullsLast(Integer::compareTo))
                .thenComparing(SubtitleSegment::getId, Comparator.nullsLast(Long::compareTo)))
            .toList();
    }

    private static List<SubtitleTranslationSegment> sortedTranslations(List<SubtitleTranslationSegment> rows) {
        return safeList(rows).stream()
            .filter(Objects::nonNull)
            .sorted(Comparator
                .comparing(SubtitleTranslationSegment::getStartMillis, Comparator.nullsLast(Long::compareTo))
                .thenComparing(SubtitleTranslationSegment::getSegmentIndex, Comparator.nullsLast(Integer::compareTo))
                .thenComparing(SubtitleTranslationSegment::getId, Comparator.nullsLast(Long::compareTo)))
            .toList();
    }

    private static List<VideoKeyframe> sortedKeyframes(List<VideoKeyframe> rows) {
        return safeList(rows).stream()
            .filter(Objects::nonNull)
            .sorted(Comparator
                .comparing(VideoKeyframe::getTimestampMillis, Comparator.nullsLast(Long::compareTo))
                .thenComparing(VideoKeyframe::getId, Comparator.nullsLast(Long::compareTo)))
            .toList();
    }

    private static List<VideoKeyframeOcr> sortedOcrRows(List<VideoKeyframeOcr> rows) {
        return safeList(rows).stream()
            .filter(Objects::nonNull)
            .sorted(Comparator
                .comparing(VideoKeyframeOcr::getTimestampMillis, Comparator.nullsLast(Long::compareTo))
                .thenComparing(VideoKeyframeOcr::getKeyframeId, Comparator.nullsLast(Long::compareTo))
                .thenComparing(VideoKeyframeOcr::getId, Comparator.nullsLast(Long::compareTo)))
            .toList();
    }

    private static List<VideoKeyframeAnalysis> sortedAnalysisRows(List<VideoKeyframeAnalysis> rows) {
        return safeList(rows).stream()
            .filter(Objects::nonNull)
            .sorted(Comparator
                .comparing(VideoKeyframeAnalysis::getTimestampMillis, Comparator.nullsLast(Long::compareTo))
                .thenComparing(VideoKeyframeAnalysis::getKeyframeId, Comparator.nullsLast(Long::compareTo))
                .thenComparing(VideoKeyframeAnalysis::getId, Comparator.nullsLast(Long::compareTo)))
            .toList();
    }

    private static <T> List<T> safeList(List<T> rows) {
        return rows == null ? List.of() : rows;
    }

    private static List<Long> distinctSortedIds(List<Long> ids) {
        return safeList(ids).stream().filter(Objects::nonNull).distinct().sorted().toList();
    }

    private VideoSegment toEntity(
        String taskId,
        Long userId,
        int index,
        long start,
        long end,
        WindowData data,
        LocalDateTime now
    ) {
        VideoSegment segment = new VideoSegment();
        segment.setTaskId(taskId);
        segment.setUserId(userId);
        segment.setSegmentIndex(index);
        segment.setStartMillis(start);
        segment.setEndMillis(end);
        segment.setTimeText(formatWindow(start, end));
        segment.setAsrText(data.asrText());
        segment.setTranslatedText(data.translatedText());
        segment.setOcrText(data.ocrText());
        segment.setVisualSummary(data.visualSummary());
        segment.setFusedSummary(fusedSummary(data));
        segment.setKeywordsJson(toJson(keywordExtractor.extract(data.combinedText(), properties.getMaxKeywords()), "[]"));
        segment.setEvidenceJson(toJson(data.evidence(), "{}"));
        segment.setSourceStatusJson(toJson(data.sourceStatus(), "{}"));
        segment.setConfidence(confidence(data));
        segment.setStatus(VideoSegmentStatus.SUCCEEDED.name());
        segment.setCreatedAt(now);
        segment.setUpdatedAt(now);
        return segment;
    }

    private WindowData windowData(
        long start,
        long end,
        boolean finalWindow,
        List<SubtitleSegment> subtitles,
        List<SubtitleTranslationSegment> translations,
        List<VideoKeyframe> keyframes,
        List<VideoKeyframeOcr> ocrRows,
        List<VideoKeyframeAnalysis> analysisRows
    ) {
        List<SubtitleSegment> subtitleHits = subtitles.stream()
            .filter(segment -> overlaps(segment.getStartMillis(), segment.getEndMillis(), start, end))
            .toList();
        List<SubtitleTranslationSegment> translationHits = translations.stream()
            .filter(segment -> overlaps(segment.getStartMillis(), segment.getEndMillis(), start, end))
            .toList();
        List<VideoKeyframe> keyframeHits = keyframes.stream()
            .filter(keyframe -> inWindow(keyframe.getTimestampMillis(), start, end, finalWindow))
            .toList();
        Set<Long> keyframeIds = new LinkedHashSet<>();
        keyframeHits.stream().map(VideoKeyframe::getId).forEach(keyframeIds::add);
        List<VideoKeyframeOcr> ocrWindowRows = ocrRows.stream()
            .filter(row -> inWindow(row.getTimestampMillis(), start, end, finalWindow))
            .toList();
        List<VideoKeyframeOcr> ocrHits = ocrWindowRows.stream()
            .filter(row -> OcrStatus.SUCCEEDED.name().equals(row.getStatus()))
            .filter(row -> row.getOcrText() != null && !row.getOcrText().isBlank())
            .filter(row -> OcrTextQualityEvaluator.isUseful(row.getOcrText(), row.getConfidence()))
            .toList();
        ocrHits.stream().map(VideoKeyframeOcr::getKeyframeId).forEach(keyframeIds::add);
        List<VideoKeyframeAnalysis> analysisWindowRows = analysisRows.stream()
            .filter(row -> inWindow(row.getTimestampMillis(), start, end, finalWindow))
            .toList();
        List<VideoKeyframeAnalysis> analysisHits = analysisWindowRows.stream()
            .filter(row -> VisionAnalysisStatus.SUCCEEDED.name().equals(row.getStatus()))
            .filter(row -> row.getVisualSummary() != null && !row.getVisualSummary().isBlank())
            .toList();
        analysisHits.stream().map(VideoKeyframeAnalysis::getKeyframeId).forEach(keyframeIds::add);

        String asrText = truncate(
            joinDistinct(subtitleHits.stream().map(SubtitleSegment::getText).toList()),
            properties.getMaxAsrCharsPerWindow()
        );
        String translatedText = truncate(
            joinDistinct(translationHits.stream().map(SubtitleTranslationSegment::getTranslatedText).toList()),
            properties.getMaxAsrCharsPerWindow()
        );
        String ocrText = truncate(
            joinDistinct(ocrHits.stream().map(VideoKeyframeOcr::getOcrText).toList()),
            properties.getMaxOcrCharsPerWindow()
        );
        String visualSummary = truncate(
            joinDistinct(analysisHits.stream().map(VideoKeyframeAnalysis::getVisualSummary).toList()),
            properties.getMaxVisualCharsPerWindow()
        );
        Map<String, Integer> sourceCounts = new LinkedHashMap<>();
        sourceCounts.put("asr", subtitleHits.size());
        sourceCounts.put("translation", translationHits.size());
        sourceCounts.put("ocr", ocrHits.size());
        sourceCounts.put("visual", analysisHits.size());
        VideoSegmentEvidence evidence = new VideoSegmentEvidence(
            distinctSortedIds(subtitleHits.stream().map(SubtitleSegment::getId).toList()),
            distinctSortedIds(keyframeIds.stream().toList()),
            distinctSortedIds(ocrHits.stream().map(VideoKeyframeOcr::getId).toList()),
            distinctSortedIds(analysisHits.stream().map(VideoKeyframeAnalysis::getId).toList()),
            sourceCounts,
            distinctSortedIds(translationHits.stream().map(SubtitleTranslationSegment::getId).toList())
        );
        VideoSegmentSourceStatus sourceStatus = sourceStatus(
            start,
            end,
            subtitleHits,
            translationHits,
            keyframeHits,
            ocrWindowRows,
            ocrHits,
            analysisWindowRows,
            analysisHits
        );
        return new WindowData(asrText, translatedText, ocrText, visualSummary, evidence, sourceStatus);
    }

    private VideoSegmentResponse toResponse(VideoSegment row) {
        return new VideoSegmentResponse(
            row.getId(),
            row.getSegmentIndex(),
            row.getStartMillis(),
            row.getEndMillis(),
            row.getTimeText(),
            nullToEmpty(row.getAsrText()),
            nullToEmpty(row.getTranslatedText()),
            nullToEmpty(row.getOcrText()),
            nullToEmpty(row.getVisualSummary()),
            nullToEmpty(row.getFusedSummary()),
            parseKeywords(row.getKeywordsJson()),
            parseEvidence(row.getEvidenceJson()),
            parseSourceStatus(row.getSourceStatusJson()),
            nullToEmpty(row.getStatus()),
            row.getConfidence()
        );
    }

    private static boolean matchesKeyword(VideoSegmentResponse view, String keyword) {
        return contains(view.asrText(), keyword)
            || contains(view.translatedText(), keyword)
            || contains(view.ocrText(), keyword)
            || contains(view.visualSummary(), keyword)
            || contains(view.fusedSummary(), keyword)
            || view.keywords().stream().anyMatch(item -> contains(item, keyword));
    }

    private static boolean contains(String text, String keyword) {
        return text != null && text.toLowerCase(Locale.ROOT).contains(keyword);
    }

    private List<String> parseKeywords(String json) {
        try {
            return json == null || json.isBlank() ? List.of() : objectMapper.readValue(json, STRING_LIST_TYPE);
        } catch (JsonProcessingException ignored) {
            return List.of();
        }
    }

    private VideoSegmentEvidence parseEvidence(String json) {
        try {
            return json == null || json.isBlank()
                ? emptyEvidence()
                : objectMapper.readValue(json, EVIDENCE_TYPE);
        } catch (JsonProcessingException ignored) {
            return emptyEvidence();
        }
    }

    private VideoSegmentSourceStatus parseSourceStatus(String json) {
        try {
            return json == null || json.isBlank()
                ? VideoSegmentSourceStatus.empty()
                : objectMapper.readValue(json, VideoSegmentSourceStatus.class);
        } catch (JsonProcessingException ignored) {
            return VideoSegmentSourceStatus.empty();
        }
    }

    private static VideoSegmentEvidence emptyEvidence() {
        return new VideoSegmentEvidence(List.of(), List.of(), List.of(), List.of(), Map.of());
    }

    private String toJson(Object value, String fallback) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException ignored) {
            return fallback;
        }
    }

    private static String fusedSummary(WindowData data) {
        List<String> parts = new ArrayList<>();
        if (!data.asrText().isBlank()) {
            parts.add("\u672c\u6bb5\u4e3b\u8981\u8bb2\u89e3\uff1a" + snippet(data.asrText(), 180));
        }
        if (!data.translatedText().isBlank()) {
            parts.add("\u5b57\u5e55\u8bd1\u6587\uff1a" + snippet(data.translatedText(), 180));
        }
        if (!data.ocrText().isBlank()) {
            parts.add("\u753b\u9762\u6587\u5b57\u5305\u62ec\uff1a" + snippet(data.ocrText(), 120));
        }
        if (!data.visualSummary().isBlank()) {
            parts.add("\u753b\u9762\u663e\u793a\uff1a" + snippet(data.visualSummary(), 140));
        }
        return String.join("\uff1b", parts);
    }

    private static double confidence(WindowData data) {
        Map<String, Double> components = data.sourceStatus().confidenceComponents();
        double weighted = 0.0d;
        double weights = 0.0d;
        weighted += component(components, "asr", 0.30d);
        weights += components.containsKey("asr") ? 0.30d : 0.0d;
        weighted += component(components, "translation", 0.10d);
        weights += components.containsKey("translation") ? 0.10d : 0.0d;
        weighted += component(components, "ocr", 0.20d);
        weights += components.containsKey("ocr") ? 0.20d : 0.0d;
        weighted += component(components, "keyframeQuality", 0.15d);
        weights += components.containsKey("keyframeQuality") ? 0.15d : 0.0d;
        weighted += component(components, "vlm", 0.15d);
        weights += components.containsKey("vlm") ? 0.15d : 0.0d;
        weighted += component(components, "timestamp", 0.10d);
        weights += components.containsKey("timestamp") ? 0.10d : 0.0d;
        double score = weights <= 0.0d ? 0.0d : weighted / weights;
        if (data.sourceStatus().degraded()) {
            score *= 0.85d;
        }
        return Math.round(clamp(score) * 10_000.0d) / 10_000.0d;
    }

    private static double component(Map<String, Double> components, String key, double weight) {
        Double value = components.get(key);
        return value == null ? 0.0d : clamp(value) * weight;
    }

    private VideoSegmentSourceStatus sourceStatus(
        long start,
        long end,
        List<SubtitleSegment> subtitleHits,
        List<SubtitleTranslationSegment> translationHits,
        List<VideoKeyframe> keyframeHits,
        List<VideoKeyframeOcr> ocrWindowRows,
        List<VideoKeyframeOcr> ocrHits,
        List<VideoKeyframeAnalysis> analysisWindowRows,
        List<VideoKeyframeAnalysis> analysisHits
    ) {
        Map<String, String> sources = new LinkedHashMap<>();
        sources.put("asr", availability(properties.isIncludeAsr(), subtitleHits, subtitleHits));
        sources.put("translation", translationSegmentMapper == null
            ? "UNAVAILABLE"
            : availability(true, translationHits, translationHits));
        sources.put("ocr", rowAvailability(
            properties.isIncludeOcr() && ocrMapper != null,
            ocrWindowRows.stream().map(VideoKeyframeOcr::getStatus).toList(),
            ocrHits
        ));
        sources.put("visual", rowAvailability(
            properties.isIncludeVision() && analysisMapper != null,
            analysisWindowRows.stream().map(VideoKeyframeAnalysis::getStatus).toList(),
            analysisHits
        ));
        sources.put("keyframe", keyframeHits.isEmpty() ? "MISSING" : "AVAILABLE");

        boolean timestampValid = end > start
            && subtitleHits.stream().allMatch(row -> validRange(row.getStartMillis(), row.getEndMillis()))
            && translationHits.stream().allMatch(row -> validRange(row.getStartMillis(), row.getEndMillis()))
            && keyframeHits.stream().allMatch(row -> row.getTimestampMillis() != null && row.getTimestampMillis() >= 0L)
            && ocrWindowRows.stream().allMatch(row -> row.getTimestampMillis() != null && row.getTimestampMillis() >= 0L)
            && analysisWindowRows.stream().allMatch(row -> row.getTimestampMillis() != null && row.getTimestampMillis() >= 0L);
        sources.put("timestamp", timestampValid ? "VALID" : "DEGRADED");
        String keyframeSourceTypes = keyframeHits.stream()
            .map(VideoKeyframe::getSourceType)
            .map(VideoSegmentFusionServiceImpl::clean)
            .filter(value -> !value.isBlank())
            .distinct()
            .sorted()
            .reduce((left, right) -> left + "," + right)
            .orElse("");
        if (!keyframeSourceTypes.isBlank()) {
            sources.put("keyframeSourceTypes", keyframeSourceTypes);
        }

        Map<String, Double> components = new LinkedHashMap<>();
        if (properties.isIncludeAsr()) {
            components.put("asr", subtitleHits.isEmpty() ? 0.0d : 1.0d);
        }
        if (translationSegmentMapper != null) {
            components.put("translation", translationHits.isEmpty() ? 0.0d : 1.0d);
        }
        if (properties.isIncludeOcr() && ocrMapper != null) {
            components.put("ocr", averageOcrConfidence(ocrHits));
        }
        List<Double> qualityScores = keyframeHits.stream()
            .map(VideoKeyframe::getQualityScore)
            .filter(Objects::nonNull)
            .toList();
        if (!qualityScores.isEmpty()) {
            components.put("keyframeQuality", average(qualityScores));
        }
        if (properties.isIncludeVision() && analysisMapper != null) {
            components.put("vlm", analysisWindowRows.isEmpty()
                ? 0.0d
                : analysisHits.size() / (double) analysisWindowRows.size());
        }
        components.put("timestamp", timestampValid ? 1.0d : 0.25d);

        boolean degraded = !timestampValid
            || keyframeHits.stream().anyMatch(row -> Boolean.TRUE.equals(row.getDegraded()))
            || ocrWindowRows.stream().anyMatch(row -> failed(row.getStatus()))
            || analysisWindowRows.stream().anyMatch(row -> failed(row.getStatus()));
        return new VideoSegmentSourceStatus(sources, components, degraded);
    }

    private static String availability(boolean enabled, List<?> attempted, List<?> succeeded) {
        if (!enabled) {
            return "DISABLED";
        }
        if (!succeeded.isEmpty()) {
            return "AVAILABLE";
        }
        return attempted.isEmpty() ? "MISSING" : "FAILED";
    }

    private static String rowAvailability(boolean enabled, List<String> statuses, List<?> succeeded) {
        if (!enabled) {
            return "DISABLED";
        }
        if (!succeeded.isEmpty()) {
            return "AVAILABLE";
        }
        if (statuses == null || statuses.isEmpty()) {
            return "MISSING";
        }
        if (statuses.stream().filter(Objects::nonNull).allMatch(status -> status.equalsIgnoreCase("DISABLED"))) {
            return "DISABLED";
        }
        if (statuses.stream().anyMatch(VideoSegmentFusionServiceImpl::failed)) {
            return "FAILED";
        }
        if (statuses.stream().anyMatch(status -> status != null && status.equalsIgnoreCase("SKIPPED"))) {
            return "SKIPPED";
        }
        return "EMPTY";
    }

    private static boolean failed(String status) {
        return status != null && (status.equalsIgnoreCase("FAILED") || status.equalsIgnoreCase("ERROR"));
    }

    private static boolean validRange(Long start, Long end) {
        return start != null && end != null && start >= 0L && end >= start;
    }

    private static double averageOcrConfidence(List<VideoKeyframeOcr> rows) {
        if (rows.isEmpty()) {
            return 0.0d;
        }
        List<Double> scores = rows.stream()
            .map(VideoKeyframeOcr::getConfidence)
            .filter(Objects::nonNull)
            .toList();
        return scores.isEmpty() ? 0.65d : average(scores);
    }

    private static double average(List<Double> values) {
        return clamp(values.stream().mapToDouble(Double::doubleValue).average().orElse(0.0d));
    }

    private static double clamp(double value) {
        if (!Double.isFinite(value)) {
            return 0.0d;
        }
        return Math.max(0.0d, Math.min(value, 1.0d));
    }

    private static long durationMillis(
        List<SubtitleSegment> subtitles,
        List<SubtitleTranslationSegment> translations,
        List<VideoKeyframe> keyframes,
        List<VideoKeyframeOcr> ocrRows,
        List<VideoKeyframeAnalysis> analysisRows,
        long minimumEvidenceDurationMillis
    ) {
        long subtitleMax = subtitles.stream()
            .map(SubtitleSegment::getEndMillis)
            .filter(Objects::nonNull)
            .mapToLong(Long::longValue)
            .max()
            .orElse(0L);
        long translationMax = translations.stream()
            .map(SubtitleTranslationSegment::getEndMillis)
            .filter(Objects::nonNull)
            .mapToLong(Long::longValue)
            .max()
            .orElse(0L);
        long keyframeMax = keyframes.stream()
            .map(VideoKeyframe::getTimestampMillis)
            .filter(Objects::nonNull)
            .mapToLong(Long::longValue)
            .max()
            .orElse(0L);
        long ocrMax = ocrRows.stream()
            .map(VideoKeyframeOcr::getTimestampMillis)
            .filter(Objects::nonNull)
            .mapToLong(Long::longValue)
            .max()
            .orElse(0L);
        long analysisMax = analysisRows.stream()
            .map(VideoKeyframeAnalysis::getTimestampMillis)
            .filter(Objects::nonNull)
            .mapToLong(Long::longValue)
            .max()
            .orElse(0L);
        long max = Math.max(Math.max(Math.max(subtitleMax, translationMax), keyframeMax), Math.max(ocrMax, analysisMax));
        if (max > 0) {
            return max;
        }
        return hasAnyEvidence(subtitles, translations, keyframes, ocrRows, analysisRows) ? minimumEvidenceDurationMillis : 0L;
    }

    private static boolean hasAnyEvidence(
        List<SubtitleSegment> subtitles,
        List<SubtitleTranslationSegment> translations,
        List<VideoKeyframe> keyframes,
        List<VideoKeyframeOcr> ocrRows,
        List<VideoKeyframeAnalysis> analysisRows
    ) {
        return subtitles.stream().anyMatch(segment -> segment.getText() != null && !segment.getText().isBlank())
            || translations.stream().anyMatch(segment -> segment.getTranslatedText() != null && !segment.getTranslatedText().isBlank())
            || !keyframes.isEmpty()
            || ocrRows.stream().anyMatch(row -> row.getOcrText() != null && !row.getOcrText().isBlank())
            || analysisRows.stream().anyMatch(row -> row.getVisualSummary() != null && !row.getVisualSummary().isBlank());
    }

    private static boolean overlaps(Long segmentStart, Long segmentEnd, long windowStart, long windowEnd) {
        long start = segmentStart == null ? 0L : segmentStart;
        long end = segmentEnd == null ? start : segmentEnd;
        if (end <= start) {
            return start >= windowStart && start < windowEnd;
        }
        return end > windowStart && start < windowEnd;
    }

    private static boolean inWindow(Long timestampMillis, long start, long end, boolean includeEnd) {
        if (timestampMillis == null) {
            return false;
        }
        return timestampMillis >= start && (timestampMillis < end || includeEnd && timestampMillis == end);
    }

    private static String joinDistinct(List<String> values) {
        LinkedHashSet<String> unique = new LinkedHashSet<>();
        for (String value : values) {
            String cleaned = clean(value);
            if (!cleaned.isBlank()) {
                unique.add(cleaned);
            }
        }
        return String.join("\n", unique);
    }

    private static String clean(String value) {
        return value == null ? "" : value.replaceAll("\\s+", " ").strip();
    }

    private static String truncate(String value, int maxLength) {
        String cleaned = clean(value);
        return cleaned.length() <= maxLength ? cleaned : cleaned.substring(0, maxLength);
    }

    private static String snippet(String value, int maxLength) {
        return truncate(value, maxLength);
    }

    private static String formatWindow(long startMillis, long endMillis) {
        return formatTime(startMillis) + " - " + formatTime(endMillis);
    }

    private static String formatTime(long millis) {
        long totalSeconds = Math.max(0L, millis / 1000L);
        long hours = totalSeconds / 3600L;
        long minutes = (totalSeconds % 3600L) / 60L;
        long seconds = totalSeconds % 60L;
        return String.format("%02d:%02d:%02d", hours, minutes, seconds);
    }

    private static String normalizeTaskId(String taskId) {
        if (taskId == null || taskId.isBlank()) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, "Task id is required");
        }
        return taskId.strip();
    }

    private static String nullToEmpty(String value) {
        return value == null ? "" : value;
    }

    private record WindowData(
        String asrText,
        String translatedText,
        String ocrText,
        String visualSummary,
        VideoSegmentEvidence evidence,
        VideoSegmentSourceStatus sourceStatus
    ) {
        boolean isEmpty() {
            return asrText.isBlank() && translatedText.isBlank() && ocrText.isBlank() && visualSummary.isBlank();
        }

        String combinedText() {
            return String.join("\n", asrText, translatedText, ocrText, visualSummary);
        }
    }
}
