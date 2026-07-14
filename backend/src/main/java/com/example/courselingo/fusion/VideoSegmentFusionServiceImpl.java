package com.example.courselingo.fusion;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.fusion.mapper.VideoSegmentMapper;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.subtitle.mapper.SubtitleSegmentMapper;
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
            ? subtitleSegmentMapper.selectByTaskIdAndUserId(normalizedTaskId, userId)
            : List.of();
        List<VideoKeyframe> keyframes = keyframeMapper.selectByTaskIdAndUserId(normalizedTaskId, userId);
        List<Long> keyframeIds = keyframes.stream().map(VideoKeyframe::getId).toList();
        List<VideoKeyframeOcr> ocrRows = properties.isIncludeOcr() && ocrMapper != null
            ? ocrMapper.selectByKeyframeIds(normalizedTaskId, userId, keyframeIds)
            : List.of();
        List<VideoKeyframeAnalysis> analysisRows = properties.isIncludeVision() && analysisMapper != null
            ? analysisMapper.selectByKeyframeIds(normalizedTaskId, userId, keyframeIds)
            : List.of();
        long windowMillis = Math.max(1L, properties.getWindowSeconds()) * 1000L;
        long durationMillis = durationMillis(subtitles, keyframes, ocrRows, analysisRows, windowMillis);
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
                keyframes,
                ocrRows,
                analysisRows
            );
            if (data.isEmpty()) {
                empty++;
                continue;
            }
            videoSegmentMapper.insert(toEntity(normalizedTaskId, userId, index, start, end, data, now));
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
        segment.setOcrText(data.ocrText());
        segment.setVisualSummary(data.visualSummary());
        segment.setFusedSummary(fusedSummary(data));
        segment.setKeywordsJson(toJson(keywordExtractor.extract(data.combinedText(), properties.getMaxKeywords()), "[]"));
        segment.setEvidenceJson(toJson(data.evidence(), "{}"));
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
        List<VideoKeyframe> keyframes,
        List<VideoKeyframeOcr> ocrRows,
        List<VideoKeyframeAnalysis> analysisRows
    ) {
        List<SubtitleSegment> subtitleHits = subtitles.stream()
            .filter(segment -> overlaps(segment.getStartMillis(), segment.getEndMillis(), start, end))
            .toList();
        List<VideoKeyframe> keyframeHits = keyframes.stream()
            .filter(keyframe -> inWindow(keyframe.getTimestampMillis(), start, end, finalWindow))
            .toList();
        Set<Long> keyframeIds = new LinkedHashSet<>();
        keyframeHits.stream().map(VideoKeyframe::getId).forEach(keyframeIds::add);
        List<VideoKeyframeOcr> ocrHits = ocrRows.stream()
            .filter(row -> inWindow(row.getTimestampMillis(), start, end, finalWindow))
            .filter(row -> OcrStatus.SUCCEEDED.name().equals(row.getStatus()))
            .filter(row -> row.getOcrText() != null && !row.getOcrText().isBlank())
            .filter(row -> OcrTextQualityEvaluator.isUseful(row.getOcrText(), row.getConfidence()))
            .toList();
        ocrHits.stream().map(VideoKeyframeOcr::getKeyframeId).forEach(keyframeIds::add);
        List<VideoKeyframeAnalysis> analysisHits = analysisRows.stream()
            .filter(row -> inWindow(row.getTimestampMillis(), start, end, finalWindow))
            .filter(row -> VisionAnalysisStatus.SUCCEEDED.name().equals(row.getStatus()))
            .filter(row -> row.getVisualSummary() != null && !row.getVisualSummary().isBlank())
            .toList();
        analysisHits.stream().map(VideoKeyframeAnalysis::getKeyframeId).forEach(keyframeIds::add);

        String asrText = truncate(
            joinDistinct(subtitleHits.stream().map(SubtitleSegment::getText).toList()),
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
        VideoSegmentEvidence evidence = new VideoSegmentEvidence(
            subtitleHits.stream().map(SubtitleSegment::getId).filter(Objects::nonNull).toList(),
            keyframeIds.stream().filter(Objects::nonNull).toList(),
            ocrHits.stream().map(VideoKeyframeOcr::getId).filter(Objects::nonNull).toList(),
            analysisHits.stream().map(VideoKeyframeAnalysis::getId).filter(Objects::nonNull).toList(),
            Map.of("asr", subtitleHits.size(), "ocr", ocrHits.size(), "visual", analysisHits.size())
        );
        return new WindowData(asrText, ocrText, visualSummary, evidence);
    }

    private VideoSegmentResponse toResponse(VideoSegment row) {
        return new VideoSegmentResponse(
            row.getId(),
            row.getSegmentIndex(),
            row.getStartMillis(),
            row.getEndMillis(),
            row.getTimeText(),
            nullToEmpty(row.getAsrText()),
            nullToEmpty(row.getOcrText()),
            nullToEmpty(row.getVisualSummary()),
            nullToEmpty(row.getFusedSummary()),
            parseKeywords(row.getKeywordsJson()),
            parseEvidence(row.getEvidenceJson()),
            nullToEmpty(row.getStatus()),
            row.getConfidence()
        );
    }

    private static boolean matchesKeyword(VideoSegmentResponse view, String keyword) {
        return contains(view.asrText(), keyword)
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
        if (!data.ocrText().isBlank()) {
            parts.add("\u753b\u9762\u6587\u5b57\u5305\u62ec\uff1a" + snippet(data.ocrText(), 120));
        }
        if (!data.visualSummary().isBlank()) {
            parts.add("\u753b\u9762\u663e\u793a\uff1a" + snippet(data.visualSummary(), 140));
        }
        return String.join("\uff1b", parts);
    }

    private static double confidence(WindowData data) {
        int sources = 0;
        if (!data.asrText().isBlank()) {
            sources++;
        }
        if (!data.ocrText().isBlank()) {
            sources++;
        }
        if (!data.visualSummary().isBlank()) {
            sources++;
        }
        return Math.min(0.9d, 0.5d + sources * 0.1d);
    }

    private static long durationMillis(
        List<SubtitleSegment> subtitles,
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
        long max = Math.max(Math.max(subtitleMax, keyframeMax), Math.max(ocrMax, analysisMax));
        if (max > 0) {
            return max;
        }
        return hasAnyEvidence(subtitles, keyframes, ocrRows, analysisRows) ? minimumEvidenceDurationMillis : 0L;
    }

    private static boolean hasAnyEvidence(
        List<SubtitleSegment> subtitles,
        List<VideoKeyframe> keyframes,
        List<VideoKeyframeOcr> ocrRows,
        List<VideoKeyframeAnalysis> analysisRows
    ) {
        return subtitles.stream().anyMatch(segment -> segment.getText() != null && !segment.getText().isBlank())
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
        String ocrText,
        String visualSummary,
        VideoSegmentEvidence evidence
    ) {
        boolean isEmpty() {
            return asrText.isBlank() && ocrText.isBlank() && visualSummary.isBlank();
        }

        String combinedText() {
            return String.join("\n", asrText, ocrText, visualSummary);
        }
    }
}
