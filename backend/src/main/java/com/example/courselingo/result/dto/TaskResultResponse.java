package com.example.courselingo.result.dto;

import java.util.List;
import com.example.courselingo.fusion.VideoSegmentResponse;
import com.example.courselingo.vision.keyframe.VideoKeyframeView;

public record TaskResultResponse(
    String taskId,
    String targetLanguage,
    TranslationStatus translationStatus,
    String translationErrorSummary,
    String sourceFullText,
    List<String> sourceParagraphs,
    String translatedFullText,
    List<ResultSubtitleSegment> subtitles,
    List<ResultTranslationSegment> translations,
    ResultLearningPackage learningPackage,
    List<ResultArtifactFile> artifacts,
    List<VideoKeyframeView> keyframes,
    List<VideoSegmentResponse> videoSegments,
    List<ResultAiCallRecord> aiCallRecords,
    BackgroundStageStatus learningPackageStatus,
    BackgroundStageStatus artifactsStatus
) {
    public TaskResultResponse(
        String taskId,
        String targetLanguage,
        TranslationStatus translationStatus,
        String translationErrorSummary,
        String sourceFullText,
        List<String> sourceParagraphs,
        String translatedFullText,
        List<ResultSubtitleSegment> subtitles,
        List<ResultTranslationSegment> translations,
        ResultLearningPackage learningPackage,
        List<ResultArtifactFile> artifacts,
        List<VideoKeyframeView> keyframes,
        List<VideoSegmentResponse> videoSegments,
        List<ResultAiCallRecord> aiCallRecords
    ) {
        this(taskId, targetLanguage, translationStatus, translationErrorSummary, sourceFullText, sourceParagraphs,
            translatedFullText, subtitles, translations, learningPackage, artifacts, keyframes, videoSegments, aiCallRecords,
            learningPackage == null ? BackgroundStageStatus.NOT_STARTED : BackgroundStageStatus.SUCCEEDED,
            artifacts == null || artifacts.isEmpty() ? BackgroundStageStatus.NOT_STARTED : BackgroundStageStatus.SUCCEEDED);
    }

    public TaskResultResponse(
        String taskId,
        String targetLanguage,
        String sourceFullText,
        List<String> sourceParagraphs,
        String translatedFullText,
        List<ResultSubtitleSegment> subtitles,
        List<ResultTranslationSegment> translations,
        ResultLearningPackage learningPackage,
        List<ResultArtifactFile> artifacts,
        List<VideoKeyframeView> keyframes,
        List<VideoSegmentResponse> videoSegments,
        List<ResultAiCallRecord> aiCallRecords
    ) {
        this(
            taskId, targetLanguage,
            translations == null || translations.isEmpty() ? TranslationStatus.NOT_STARTED : TranslationStatus.SUCCEEDED,
            null, sourceFullText, sourceParagraphs, translatedFullText, subtitles, translations, learningPackage,
            artifacts, keyframes, videoSegments, aiCallRecords
        );
    }
}
