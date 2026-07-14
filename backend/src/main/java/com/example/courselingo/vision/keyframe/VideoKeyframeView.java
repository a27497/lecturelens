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
    VideoKeyframeAnalysisView visualAnalysis
) {
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
            VideoKeyframeAnalysisViews.missing(false)
        );
    }
}
