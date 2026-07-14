package com.example.courselingo.vision.keyframe;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;

class KeyframeSelectionServiceTest {

    private final KeyframeSelectionService selector = new KeyframeSelectionService();

    @Test
    void selectsFirstFrameSceneChangeContentChangeAndPeriodicAnchors() {
        VideoKeyframeProperties properties = properties();
        List<SelectedKeyframe> selected = selector.select(List.of(
            candidate(0, 0, 0.0, 0.0),
            candidate(1, 1_000, 40.0, 0.20),
            candidate(4, 4_000, 5.0, 0.15),
            candidate(8, 8_000, 30.0, 0.02),
            candidate(60, 60_000, 1.0, 0.01)
        ), properties);

        assertThat(selected)
            .extracting(SelectedKeyframe::reason)
            .containsExactly(
                KeyframeSelectionReason.FIRST_FRAME,
                KeyframeSelectionReason.SCENE_CHANGE,
                KeyframeSelectionReason.CONTENT_CHANGE,
                KeyframeSelectionReason.PERIODIC_ANCHOR
            );
        assertThat(selected).extracting(SelectedKeyframe::timestampMillis)
            .containsExactly(0L, 4_000L, 8_000L, 60_000L);
    }

    @Test
    void respectsMinimumGapPerMinuteLimitAndTotalLimit() {
        VideoKeyframeProperties properties = properties();
        properties.setMinKeyframeGapSeconds(3);
        properties.setMaxKeyframesPerMinute(2);
        properties.setMaxKeyframesTotal(3);

        List<SelectedKeyframe> selected = selector.select(List.of(
            candidate(0, 0, 0.0, 0.0),
            candidate(1, 1_000, 80.0, 0.50),
            candidate(4, 4_000, 80.0, 0.50),
            candidate(8, 8_000, 80.0, 0.50),
            candidate(70, 70_000, 80.0, 0.50)
        ), properties);

        assertThat(selected).extracting(SelectedKeyframe::timestampMillis)
            .containsExactly(0L, 4_000L, 70_000L);
        assertThat(selected).hasSize(3);
    }

    @Test
    void lowChangeLongVideoKeepsFirstFrameAndPeriodicFallbackFrames() {
        VideoKeyframeProperties properties = properties();
        properties.setPeriodicAnchorSeconds(300);
        properties.setMaxKeyframesTotal(12);

        List<KeyframeCandidate> candidates = new java.util.ArrayList<>();
        for (int minute = 0; minute <= 42; minute++) {
            candidates.add(candidate(minute, minute * 60_000L, 1.0, 0.001));
        }

        List<SelectedKeyframe> selected = selector.select(candidates, properties);

        assertThat(selected).extracting(SelectedKeyframe::reason)
            .contains(KeyframeSelectionReason.FIRST_FRAME, KeyframeSelectionReason.PERIODIC_ANCHOR);
        assertThat(selected).extracting(SelectedKeyframe::timestampMillis)
            .containsExactly(0L, 300_000L, 600_000L, 900_000L, 1_200_000L, 1_500_000L,
                1_800_000L, 2_100_000L, 2_400_000L);
    }

    private static VideoKeyframeProperties properties() {
        VideoKeyframeProperties properties = new VideoKeyframeProperties();
        properties.setPeriodicAnchorSeconds(60);
        properties.setMinKeyframeGapSeconds(3);
        properties.setMaxKeyframesPerMinute(4);
        properties.setMaxKeyframesTotal(300);
        properties.setSceneChangeThreshold(0.08);
        properties.setPixelDiffThreshold(18);
        return properties;
    }

    private static KeyframeCandidate candidate(
        int frameIndex,
        long timestampMillis,
        double averagePixelDelta,
        double changedPixelRatio
    ) {
        return new KeyframeCandidate(
            frameIndex,
            timestampMillis,
            Path.of("frame-" + frameIndex + ".jpg"),
            new FrameChangeScore(averagePixelDelta, changedPixelRatio)
        );
    }
}
