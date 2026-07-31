package com.example.courselingo.result.service;

import com.example.courselingo.ai.record.dto.AiCallRecordView;
import com.example.courselingo.ai.record.service.AiCallRecordService;
import com.example.courselingo.artifact.dto.ArtifactFileView;
import com.example.courselingo.artifact.service.ArtifactFileQueryService;
import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.fusion.VideoSegmentResponse;
import com.example.courselingo.fusion.VideoSegmentService;
import com.example.courselingo.learning.dto.GlossaryItem;
import com.example.courselingo.learning.dto.KeyPointItem;
import com.example.courselingo.learning.dto.LearningPackageView;
import com.example.courselingo.learning.dto.QaItem;
import com.example.courselingo.learning.service.LearningPackageQueryService;
import com.example.courselingo.result.dto.ResultAiCallRecord;
import com.example.courselingo.result.dto.ResultArtifactFile;
import com.example.courselingo.result.dto.ResultLearningPackage;
import com.example.courselingo.result.dto.ResultSubtitleSegment;
import com.example.courselingo.result.dto.ResultTranslationSegment;
import com.example.courselingo.result.dto.TaskResultResponse;
import com.example.courselingo.result.dto.TranslationStatus;
import com.example.courselingo.subtitle.dto.SubtitleSegmentView;
import com.example.courselingo.subtitle.dto.TaskFullTextResultView;
import com.example.courselingo.subtitle.dto.SubtitleTranslationSegmentView;
import com.example.courselingo.subtitle.service.SubtitleSegmentQueryService;
import com.example.courselingo.subtitle.service.TaskFullTextResultQueryService;
import com.example.courselingo.subtitle.service.SubtitleTranslationQueryService;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.vision.keyframe.VideoKeyframe;
import com.example.courselingo.vision.keyframe.VideoKeyframeView;
import com.example.courselingo.vision.keyframe.VideoKeyframeViews;
import com.example.courselingo.vision.keyframe.mapper.VideoKeyframeMapper;
import com.example.courselingo.vision.analysis.VisionAnalysisProperties;
import com.example.courselingo.vision.analysis.VideoKeyframeAnalysis;
import com.example.courselingo.vision.analysis.mapper.VideoKeyframeAnalysisMapper;
import com.example.courselingo.vision.ocr.VisionOcrProperties;
import com.example.courselingo.vision.ocr.mapper.VideoKeyframeOcrMapper;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class TaskResultServiceImpl implements TaskResultService {

    private static final TypeReference<List<KeyPointItem>> KEY_POINTS_TYPE = new TypeReference<>() {
    };
    private static final TypeReference<List<GlossaryItem>> GLOSSARY_TYPE = new TypeReference<>() {
    };
    private static final TypeReference<List<QaItem>> QA_TYPE = new TypeReference<>() {
    };

    private final CurrentUserService currentUserService;
    private final AnalysisTaskMapper analysisTaskMapper;
    private final SubtitleSegmentQueryService subtitleSegmentQueryService;
    private final SubtitleTranslationQueryService subtitleTranslationQueryService;
    private final TaskFullTextResultQueryService fullTextResultQueryService;
    private final LearningPackageQueryService learningPackageQueryService;
    private final ArtifactFileQueryService artifactFileQueryService;
    private final AiCallRecordService aiCallRecordService;
    private final VideoKeyframeMapper videoKeyframeMapper;
    private final VideoKeyframeOcrMapper ocrMapper;
    private final VisionOcrProperties ocrProperties;
    private final VideoKeyframeAnalysisMapper keyframeAnalysisMapper;
    private final VisionAnalysisProperties visionAnalysisProperties;
    private final VideoSegmentService videoSegmentService;
    private final ObjectMapper objectMapper;

    public TaskResultServiceImpl(
        CurrentUserService currentUserService,
        AnalysisTaskMapper analysisTaskMapper,
        SubtitleSegmentQueryService subtitleSegmentQueryService,
        SubtitleTranslationQueryService subtitleTranslationQueryService,
        LearningPackageQueryService learningPackageQueryService,
        ArtifactFileQueryService artifactFileQueryService,
        AiCallRecordService aiCallRecordService,
        ObjectMapper objectMapper
    ) {
        this(
            currentUserService,
            analysisTaskMapper,
            subtitleSegmentQueryService,
            subtitleTranslationQueryService,
            null,
            learningPackageQueryService,
            artifactFileQueryService,
            aiCallRecordService,
            null,
            null,
            null,
            null,
            null,
            null,
            objectMapper
        );
    }

    @Autowired
    public TaskResultServiceImpl(
        CurrentUserService currentUserService,
        AnalysisTaskMapper analysisTaskMapper,
        SubtitleSegmentQueryService subtitleSegmentQueryService,
        SubtitleTranslationQueryService subtitleTranslationQueryService,
        TaskFullTextResultQueryService fullTextResultQueryService,
        LearningPackageQueryService learningPackageQueryService,
        ArtifactFileQueryService artifactFileQueryService,
        AiCallRecordService aiCallRecordService,
        VideoKeyframeMapper videoKeyframeMapper,
        VideoKeyframeOcrMapper ocrMapper,
        VisionOcrProperties ocrProperties,
        VideoKeyframeAnalysisMapper keyframeAnalysisMapper,
        VisionAnalysisProperties visionAnalysisProperties,
        VideoSegmentService videoSegmentService,
        ObjectMapper objectMapper
    ) {
        this.currentUserService = currentUserService;
        this.analysisTaskMapper = analysisTaskMapper;
        this.subtitleSegmentQueryService = subtitleSegmentQueryService;
        this.subtitleTranslationQueryService = subtitleTranslationQueryService;
        this.fullTextResultQueryService = fullTextResultQueryService;
        this.learningPackageQueryService = learningPackageQueryService;
        this.artifactFileQueryService = artifactFileQueryService;
        this.aiCallRecordService = aiCallRecordService;
        this.videoKeyframeMapper = videoKeyframeMapper;
        this.ocrMapper = ocrMapper;
        this.ocrProperties = ocrProperties == null ? new VisionOcrProperties() : ocrProperties;
        this.keyframeAnalysisMapper = keyframeAnalysisMapper;
        this.visionAnalysisProperties = visionAnalysisProperties == null
            ? new VisionAnalysisProperties()
            : visionAnalysisProperties;
        this.videoSegmentService = videoSegmentService;
        this.objectMapper = objectMapper;
    }

    public TaskResultServiceImpl(
        CurrentUserService currentUserService,
        AnalysisTaskMapper analysisTaskMapper,
        SubtitleSegmentQueryService subtitleSegmentQueryService,
        SubtitleTranslationQueryService subtitleTranslationQueryService,
        TaskFullTextResultQueryService fullTextResultQueryService,
        LearningPackageQueryService learningPackageQueryService,
        ArtifactFileQueryService artifactFileQueryService,
        AiCallRecordService aiCallRecordService,
        VideoKeyframeMapper videoKeyframeMapper,
        VideoKeyframeOcrMapper ocrMapper,
        VisionOcrProperties ocrProperties,
        ObjectMapper objectMapper
    ) {
        this(
            currentUserService,
            analysisTaskMapper,
            subtitleSegmentQueryService,
            subtitleTranslationQueryService,
            fullTextResultQueryService,
            learningPackageQueryService,
            artifactFileQueryService,
            aiCallRecordService,
            videoKeyframeMapper,
            ocrMapper,
            ocrProperties,
            null,
            null,
            null,
            objectMapper
        );
    }

    @Override
    public TaskResultResponse getResult(String taskId, String authorizationHeader) {
        CurrentUserResponse currentUser = currentUserService.currentUser(authorizationHeader);
        if (taskId == null || taskId.isBlank()) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED);
        }
        String normalizedTaskId = taskId.strip();
        AnalysisTask task = analysisTaskMapper.selectByIdAndUserId(normalizedTaskId, currentUser.userId());
        if (task == null) {
            throw new BusinessException(ErrorCode.TASK_NOT_FOUND);
        }
        String targetLanguage = task.getTargetLanguage();
        Long userId = currentUser.userId();
        List<SubtitleSegmentView> subtitles = subtitleSegmentQueryService.listByTaskId(normalizedTaskId, userId);
        TaskFullTextResultView fullText = fullTextResultQueryService == null
            ? null
            : fullTextResultQueryService.getByTaskAndLanguage(normalizedTaskId, userId, targetLanguage).orElse(null);
        String sourceFullText = firstNonBlank(fullText == null ? null : fullText.sourceFullText(), buildSourceFullText(subtitles));
        List<SubtitleTranslationSegmentView> translations = subtitleTranslationQueryService
            .listTranslations(normalizedTaskId, userId, targetLanguage);
        List<AiCallRecordView> aiCalls = aiCallRecordService.listByTask(normalizedTaskId, userId);
        List<ResultAiCallRecord> resultAiCalls = new java.util.ArrayList<>(aiCalls.stream()
            .map(TaskResultServiceImpl::toAiCallRecord)
            .toList());
        appendHistoricalVisionRecord(resultAiCalls, aiCalls, normalizedTaskId, userId);
        TranslationStatus translationStatus = translationStatus(task, fullText, translations, aiCalls);
        return new TaskResultResponse(
            normalizedTaskId,
            targetLanguage,
            translationStatus,
            translationErrorSummary(translationStatus, aiCalls),
            sourceFullText,
            sourceParagraphs(sourceFullText),
            fullText == null ? "" : nullToEmpty(fullText.translatedFullText()),
            subtitles.stream()
                .map(TaskResultServiceImpl::toSubtitle)
                .toList(),
            translations.stream()
                .map(TaskResultServiceImpl::toTranslation)
                .toList(),
            learningPackageQueryService.getByTaskAndLanguage(normalizedTaskId, userId, targetLanguage)
                .map(this::toLearningPackage)
                .orElse(null),
            artifactFileQueryService.listByTaskId(normalizedTaskId, userId).stream()
                .map(TaskResultServiceImpl::toArtifact)
                .toList(),
            keyframes(normalizedTaskId, userId),
            videoSegments(normalizedTaskId, userId),
            List.copyOf(resultAiCalls)
        );
    }

    private static TranslationStatus translationStatus(
        AnalysisTask task,
        TaskFullTextResultView fullText,
        List<SubtitleTranslationSegmentView> translations,
        List<AiCallRecordView> aiCalls
    ) {
        if ((translations != null && !translations.isEmpty())
            || (fullText != null && fullText.translatedFullText() != null && !fullText.translatedFullText().isBlank())) {
            return TranslationStatus.SUCCEEDED;
        }
        String status = task.getStatus() == null ? "" : task.getStatus();
        if ("CANCELED".equals(status)) {
            return TranslationStatus.CANCELED;
        }
        boolean translationFailed = aiCalls != null && aiCalls.stream().anyMatch(call ->
            call.stage() == com.example.courselingo.ai.record.domain.AiCallStage.TRANSLATION
                && call.status() == com.example.courselingo.ai.record.domain.AiCallRecordStatus.FAILED
        );
        if (translationFailed || ("FAILED".equals(status) && isTranslationStage(task.getCurrentStage()))) {
            return TranslationStatus.FAILED;
        }
        if ("CREATED".equals(status) || "QUEUED".equals(status) || "RUNNING".equals(status) || "RETRYING".equals(status)) {
            return TranslationStatus.RUNNING;
        }
        return "SUCCEEDED".equals(status) ? TranslationStatus.SKIPPED : TranslationStatus.NOT_STARTED;
    }

    private static boolean isTranslationStage(String stage) {
        return stage != null && (stage.equals("TRANSLATE") || stage.equals("TRANSLATING")
            || stage.equals("TRANSLATE_SUBTITLES"));
    }

    private static String translationErrorSummary(TranslationStatus status, List<AiCallRecordView> calls) {
        if (status != TranslationStatus.FAILED) {
            return null;
        }
        return calls == null ? "翻译生成失败，请重新处理任务。" : calls.stream()
            .filter(call -> call.stage() == com.example.courselingo.ai.record.domain.AiCallStage.TRANSLATION)
            .filter(call -> call.status() == com.example.courselingo.ai.record.domain.AiCallRecordStatus.FAILED)
            .findFirst()
            .map(call -> "翻译生成失败（" + (call.errorCode() == null ? "UNKNOWN" : call.errorCode()) + "），请重新处理任务。")
            .orElse("翻译生成失败，请重新处理任务。");
    }

    private static ResultSubtitleSegment toSubtitle(SubtitleSegmentView view) {
        return new ResultSubtitleSegment(
            view.segmentIndex(),
            view.startMillis(),
            view.endMillis(),
            view.language(),
            view.text()
        );
    }

    private static ResultTranslationSegment toTranslation(SubtitleTranslationSegmentView view) {
        return new ResultTranslationSegment(
            view.segmentIndex(),
            view.startMillis(),
            view.endMillis(),
            view.sourceLanguage(),
            view.targetLanguage(),
            view.translatedText()
        );
    }

    private ResultLearningPackage toLearningPackage(LearningPackageView view) {
        return new ResultLearningPackage(
            view.targetLanguage(),
            view.title(),
            view.summary(),
            parseList(view.keyPointsJson(), KEY_POINTS_TYPE),
            parseList(view.glossaryJson(), GLOSSARY_TYPE),
            parseList(view.qaJson(), QA_TYPE)
        );
    }

    private static ResultArtifactFile toArtifact(ArtifactFileView view) {
        return new ResultArtifactFile(
            view.artifactType().name(),
            view.language(),
            view.fileName(),
            view.contentType(),
            view.sizeBytes(),
            view.sha256(),
            view.createdAt()
        );
    }

    private static ResultAiCallRecord toAiCallRecord(AiCallRecordView view) {
        return new ResultAiCallRecord(
            view.id(),
            view.callType().name(),
            view.stage().name(),
            view.provider(),
            view.model(),
            view.status().name(),
            view.durationMillis(),
            view.providerDurationMillis(),
            view.batchCount(),
            view.retryCount(),
            view.promptTokens(),
            view.completionTokens(),
            view.totalTokens(),
            view.inputUnits(),
            view.outputUnits(),
            view.createdAt()
        );
    }

    private void appendHistoricalVisionRecord(
        List<ResultAiCallRecord> destination,
        List<AiCallRecordView> persistedCalls,
        String taskId,
        Long userId
    ) {
        boolean persisted = persistedCalls.stream().anyMatch(call ->
            call.stage() == com.example.courselingo.ai.record.domain.AiCallStage.VISION_ANALYSIS
        );
        if (persisted || keyframeAnalysisMapper == null) return;
        List<VideoKeyframeAnalysis> rows = keyframeAnalysisMapper.selectByTaskIdAndUserId(taskId, userId);
        if (rows.isEmpty()) return;
        long providerDuration = rows.stream().map(VideoKeyframeAnalysis::getDurationMillis)
            .filter(java.util.Objects::nonNull).mapToLong(Long::longValue).sum();
        int completed = (int) rows.stream().filter(row ->
            "SUCCEEDED".equals(row.getStatus()) || "EMPTY".equals(row.getStatus())
        ).count();
        java.time.LocalDateTime earliest = rows.stream().map(VideoKeyframeAnalysis::getCreatedAt)
            .filter(java.util.Objects::nonNull).min(java.time.LocalDateTime::compareTo).orElse(null);
        java.time.LocalDateTime latest = rows.stream().map(VideoKeyframeAnalysis::getUpdatedAt)
            .filter(java.util.Objects::nonNull).max(java.time.LocalDateTime::compareTo).orElse(earliest);
        long wallDuration = earliest == null || latest == null
            ? providerDuration
            : Math.max(providerDuration, Duration.between(earliest, latest).toMillis());
        destination.add(new ResultAiCallRecord(
            null,
            "VLM",
            "VISION_ANALYSIS",
            commonValue(rows.stream().map(VideoKeyframeAnalysis::getProvider).toList()),
            commonValue(rows.stream().map(VideoKeyframeAnalysis::getModel).toList()),
            completed < rows.size() ? "PARTIAL_SUCCESS" : "SUCCEEDED",
            wallDuration,
            providerDuration,
            rows.size(),
            0,
            null,
            null,
            null,
            rows.size(),
            completed,
            earliest
        ));
    }

    private static String commonValue(List<String> values) {
        List<String> normalized = values.stream().filter(value -> value != null && !value.isBlank())
            .map(String::strip).distinct().toList();
        if (normalized.isEmpty()) return "vision";
        return normalized.size() == 1 ? normalized.getFirst() : "mixed";
    }

    private List<VideoKeyframeView> keyframes(String taskId, Long userId) {
        if (videoKeyframeMapper == null) {
            return List.of();
        }
        List<VideoKeyframe> keyframes = videoKeyframeMapper.selectByTaskIdAndUserId(taskId, userId);
        return VideoKeyframeViews.toViews(
            keyframes,
            ocrMapper == null
                ? List.of()
                : ocrMapper.selectByKeyframeIds(taskId, userId, keyframes.stream().map(VideoKeyframe::getId).toList()),
            ocrProperties.isEnabled(),
            keyframeAnalysisMapper == null
                ? List.of()
                : keyframeAnalysisMapper.selectByKeyframeIds(
                    taskId,
                    userId,
                    keyframes.stream().map(VideoKeyframe::getId).toList()
                ),
            visionAnalysisProperties.isEnabled()
        );
    }

    private List<VideoSegmentResponse> videoSegments(String taskId, Long userId) {
        if (videoSegmentService == null) {
            return List.of();
        }
        return videoSegmentService.listByTaskId(taskId, userId, 300, 0, "");
    }

    private static String buildSourceFullText(List<SubtitleSegmentView> subtitles) {
        if (subtitles == null || subtitles.isEmpty()) {
            return "";
        }
        return subtitles.stream()
            .map(SubtitleSegmentView::text)
            .filter(text -> text != null && !text.isBlank())
            .map(text -> text.replaceAll("\\s+", " ").strip())
            .reduce("", (left, right) -> left.isBlank() ? right : left + "\n\n" + right)
            .strip();
    }

    private static List<String> sourceParagraphs(String sourceFullText) {
        if (sourceFullText == null || sourceFullText.isBlank()) {
            return List.of();
        }
        return java.util.Arrays.stream(sourceFullText.split("\\n\\s*\\n"))
            .map(String::strip)
            .filter(text -> !text.isBlank())
            .toList();
    }

    private static String firstNonBlank(String value, String fallback) {
        return value == null || value.isBlank() ? nullToEmpty(fallback) : value.strip();
    }

    private static String nullToEmpty(String value) {
        return value == null ? "" : value;
    }

    private <T> List<T> parseList(String json, TypeReference<List<T>> typeReference) {
        if (json == null || json.isBlank()) {
            return List.of();
        }
        try {
            return objectMapper.readValue(json, typeReference);
        } catch (JsonProcessingException ex) {
            return List.of();
        }
    }
}
