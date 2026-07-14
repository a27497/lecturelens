package com.example.courselingo.vision.analysis;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.courselingo.vision.keyframe.KeyframeSelectionReason;
import com.example.courselingo.vision.keyframe.VideoKeyframe;
import com.example.courselingo.vision.ocr.OcrStatus;
import com.example.courselingo.vision.ocr.VideoKeyframeOcr;
import java.util.List;

import org.junit.jupiter.api.Test;

class HighValueKeyframeSelectorTest {

    @Test
    void prefersSceneContentAndChangedOcrTextWithinCaps() {
        VisionAnalysisProperties properties = new VisionAnalysisProperties();
        properties.setMaxFramesTotal(2);
        properties.setMaxFramesPerMinute(1);
        properties.setMinGapSeconds(10);
        properties.setOcrTextChangeThreshold(0.35);

        List<VideoKeyframe> selected = new HighValueKeyframeSelector().select(
            List.of(
                keyframe(1L, 0L, KeyframeSelectionReason.FIRST_FRAME),
                keyframe(2L, 5_000L, KeyframeSelectionReason.CONTENT_CHANGE),
                keyframe(3L, 65_000L, KeyframeSelectionReason.SCENE_CHANGE),
                keyframe(4L, 70_000L, KeyframeSelectionReason.PERIODIC_ANCHOR)
            ),
            List.of(
                ocr(1L, ""),
                ocr(2L, "Intro agenda"),
                ocr(3L, "Database schema migration"),
                ocr(4L, "Database schema migration")
            ),
            properties
        );

        assertThat(selected).extracting(VideoKeyframe::getId).containsExactly(2L, 3L);
    }

    @Test
    void fallsBackToFirstFrameWhenNoHighValueFrameExists() {
        VisionAnalysisProperties properties = new VisionAnalysisProperties();

        List<VideoKeyframe> selected = new HighValueKeyframeSelector().select(
            List.of(keyframe(1L, 0L, KeyframeSelectionReason.FIRST_FRAME)),
            List.of(ocr(1L, "")),
            properties
        );

        assertThat(selected).extracting(VideoKeyframe::getId).containsExactly(1L);
    }

    @Test
    void skipsRepeatedOcrOnlyFramesWhenTextHasNotChangedEnough() {
        VisionAnalysisProperties properties = new VisionAnalysisProperties();
        properties.setMaxFramesTotal(3);
        properties.setMaxFramesPerMinute(5);
        properties.setMinGapSeconds(0);
        properties.setOcrTextChangeThreshold(0.35);

        List<VideoKeyframe> selected = new HighValueKeyframeSelector().select(
            List.of(
                keyframe(1L, 0L, KeyframeSelectionReason.PERIODIC_ANCHOR),
                keyframe(2L, 10_000L, KeyframeSelectionReason.PERIODIC_ANCHOR),
                keyframe(3L, 20_000L, KeyframeSelectionReason.PERIODIC_ANCHOR)
            ),
            List.of(
                ocr(1L, "Database schema migration"),
                ocr(2L, "Database schema migration"),
                ocr(3L, "Frontend keyframe panel")
            ),
            properties
        );

        assertThat(selected).extracting(VideoKeyframe::getId).containsExactly(1L, 3L);
    }

    private static VideoKeyframe keyframe(Long id, Long timestampMillis, KeyframeSelectionReason reason) {
        VideoKeyframe keyframe = new VideoKeyframe();
        keyframe.setId(id);
        keyframe.setTaskId("task_1");
        keyframe.setUserId(42L);
        keyframe.setTimestampMillis(timestampMillis);
        keyframe.setSelectReason(reason.name());
        keyframe.setObjectKey("keyframes/42/task_1/frame-" + id + ".jpg");
        return keyframe;
    }

    private static VideoKeyframeOcr ocr(Long keyframeId, String text) {
        VideoKeyframeOcr row = new VideoKeyframeOcr();
        row.setKeyframeId(keyframeId);
        row.setStatus(text == null || text.isBlank() ? OcrStatus.EMPTY.name() : OcrStatus.SUCCEEDED.name());
        row.setOcrText(text);
        return row;
    }
}
