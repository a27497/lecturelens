package com.example.courselingo.result.dto;

import java.util.List;
import com.example.courselingo.fusion.VideoSegmentResponse;
import com.example.courselingo.vision.keyframe.VideoKeyframeView;

public record TaskResultResponse(
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
}
