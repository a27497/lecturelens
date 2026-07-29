package com.example.courselingo.vision.keyframe;

import com.example.courselingo.vision.analysis.VideoKeyframeAnalysisView;
import com.example.courselingo.vision.analysis.VideoKeyframeAnalysisViews;
import com.example.courselingo.vision.ocr.VideoKeyframeOcrView;
import java.time.LocalDateTime;

public record VideoKeyframeView(
    Long frameId,
    Long timestampMillis,
    String timeText,
    String imageUrl,
    Double changeScore,
    String selectReason,
    LocalDateTime createdAt,
    VideoKeyframeOcrView ocr,
    VideoKeyframeAnalysisView visualAnalysis,
    Double qualityScore,
    String sourceType,
    Boolean degraded
) {
    public VideoKeyframeView(
        Long frameId,
        Long timestampMillis,
        String timeText,
        String imageUrl,
        Double changeScore,
        String selectReason,
        LocalDateTime createdAt,
        VideoKeyframeOcrView ocr,
        VideoKeyframeAnalysisView visualAnalysis
    ) {
        this(
            frameId,
            timestampMillis,
            timeText,
            imageUrl,
            changeScore,
            selectReason,
            createdAt,
            ocr,
            visualAnalysis,
            null,
            null,
            null
        );
    }

    public VideoKeyframeView(
        Long frameId,
        Long timestampMillis,
        String timeText,
        String imageUrl,
        Double changeScore,
        String selectReason,
        LocalDateTime createdAt,
        VideoKeyframeOcrView ocr
    ) {
        this(
            frameId,
            timestampMillis,
            timeText,
            imageUrl,
            changeScore,
            selectReason,
            createdAt,
            ocr,
            VideoKeyframeAnalysisViews.missing(false),
            null,
            null,
            null
        );
    }
}
