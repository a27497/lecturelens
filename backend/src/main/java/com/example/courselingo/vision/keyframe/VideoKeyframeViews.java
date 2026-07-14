package com.example.courselingo.vision.keyframe;

import com.example.courselingo.vision.analysis.VideoKeyframeAnalysis;
import com.example.courselingo.vision.analysis.VideoKeyframeAnalysisView;
import com.example.courselingo.vision.analysis.VideoKeyframeAnalysisViews;
import com.example.courselingo.vision.ocr.VideoKeyframeOcr;
import com.example.courselingo.vision.ocr.VideoKeyframeOcrView;
import com.example.courselingo.vision.ocr.VideoKeyframeOcrViews;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.function.Function;

public final class VideoKeyframeViews {

    private VideoKeyframeViews() {
    }

    public static List<VideoKeyframeView> toViews(
        List<VideoKeyframe> keyframes,
        Collection<VideoKeyframeOcr> ocrRows,
        boolean ocrEnabled
    ) {
        return toViews(keyframes, ocrRows, ocrEnabled, List.of(), false);
    }

    public static List<VideoKeyframeView> toViews(
        List<VideoKeyframe> keyframes,
        Collection<VideoKeyframeOcr> ocrRows,
        boolean ocrEnabled,
        Collection<VideoKeyframeAnalysis> analysisRows,
        boolean visualAnalysisEnabled
    ) {
        if (keyframes == null || keyframes.isEmpty()) {
            return List.of();
        }
        Map<Long, VideoKeyframeOcrView> ocrViews = VideoKeyframeOcrViews.byKeyframeId(ocrRows);
        Function<Long, VideoKeyframeOcrView> ocrResolver = VideoKeyframeOcrViews.resolver(ocrViews, ocrEnabled);
        Map<Long, VideoKeyframeAnalysisView> analysisViews = VideoKeyframeAnalysisViews.byKeyframeId(analysisRows);
        Function<Long, VideoKeyframeAnalysisView> analysisResolver = VideoKeyframeAnalysisViews.resolver(
            analysisViews,
            visualAnalysisEnabled
        );
        return keyframes.stream()
            .map(keyframe -> toView(
                keyframe,
                ocrResolver.apply(keyframe.getId()),
                analysisResolver.apply(keyframe.getId())
            ))
            .toList();
    }

    private static VideoKeyframeView toView(
        VideoKeyframe keyframe,
        VideoKeyframeOcrView ocr,
        VideoKeyframeAnalysisView visualAnalysis
    ) {
        return new VideoKeyframeView(
            keyframe.getId(),
            keyframe.getTimestampMillis(),
            keyframe.getTimeText(),
            "/api/tasks/" + keyframe.getTaskId() + "/keyframes/" + keyframe.getId() + "/image",
            keyframe.getChangeScore(),
            keyframe.getSelectReason(),
            keyframe.getCreatedAt(),
            ocr,
            visualAnalysis
        );
    }
}
