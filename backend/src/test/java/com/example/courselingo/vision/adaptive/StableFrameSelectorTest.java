package com.example.courselingo.vision.adaptive;

import static org.assertj.core.api.Assertions.assertThat;

import java.awt.Color;
import java.awt.image.BufferedImage;
import java.util.List;
import org.junit.jupiter.api.Test;

class StableFrameSelectorTest {

    private final ImageQualityAnalyzer analyzer = new ImageQualityAnalyzer();

    @Test
    void selectsReadableStructuredFrameInsteadOfBlackOrBlankTransitionFrames() {
        StableFrameSelector selector = new StableFrameSelector(analyzer);
        BufferedImage black = ImageQualityAnalyzerTest.solid(128, 96, Color.BLACK);
        BufferedImage blank = ImageQualityAnalyzerTest.solid(128, 96, Color.WHITE);
        BufferedImage clear = ImageQualityAnalyzerTest.checkerboard(128, 96, 8);
        SceneCandidate candidate = SceneCandidate.sceneChange(30.0, 0.9);

        var selected = selector.select(candidate, List.of(
            new StableFrameSelector.FrameSample(29.8, black),
            new StableFrameSelector.FrameSample(30.4, blank),
            new StableFrameSelector.FrameSample(30.9, clear)
        ));

        assertThat(selected).isPresent();
        assertThat(selected.orElseThrow().timestampSeconds()).isEqualTo(30.9);
        assertThat(selected.orElseThrow().quality().black()).isFalse();
        assertThat(selected.orElseThrow().relaxed()).isFalse();
    }

    @Test
    void periodicAnchorCanRelaxQualityButNormalSceneCannot() {
        BufferedImage modest = verticalBars(128, 96, 24);
        ImageQualityAnalysis measured = analyzer.analyze(modest);
        StableFrameSelector.Config config = new StableFrameSelector.Config(
            List.of(-0.2, 0.4, 0.9, 1.4),
            measured.laplacianVariance() * 1.5,
            measured.edgeDensity() * 1.5,
            0.0,
            0.5
        );
        StableFrameSelector selector = new StableFrameSelector(config, analyzer);
        List<StableFrameSelector.FrameSample> samples = List.of(
            new StableFrameSelector.FrameSample(90.4, modest));

        assertThat(selector.select(SceneCandidate.sceneChange(90, 0.8), samples)).isEmpty();
        assertThat(selector.select(new SceneCandidate(90, SceneCandidate.Source.PERIODIC_ANCHOR,
            "coverage", 0.3), samples)).hasValueSatisfying(selected ->
                assertThat(selected.relaxed()).isTrue());
    }

    @Test
    void evenCoverageAnchorsNeverAcceptBlackOrCompletelyBlankFrames() {
        StableFrameSelector selector = new StableFrameSelector(analyzer);
        SceneCandidate anchor = new SceneCandidate(60, SceneCandidate.Source.PERIODIC_ANCHOR,
            "coverage", 0.3);

        assertThat(selector.select(anchor, List.of(
            new StableFrameSelector.FrameSample(60.4, ImageQualityAnalyzerTest.solid(80, 60, Color.BLACK)),
            new StableFrameSelector.FrameSample(60.9, ImageQualityAnalyzerTest.solid(80, 60, Color.WHITE))
        ))).isEmpty();
    }

    @Test
    void clipsConfiguredNeighborOffsetsAtVideoBoundaries() {
        StableFrameSelector selector = new StableFrameSelector(analyzer);

        assertThat(selector.sampleTimestamps(0.1, 1.0)).containsExactly(0.0, 0.5, 1.0);
    }

    @Test
    void equalQualityTransitionSamplesPreferTheNewScene() {
        StableFrameSelector selector = new StableFrameSelector(analyzer);
        BufferedImage before = ImageQualityAnalyzerTest.checkerboard(128, 96, 8);
        BufferedImage after = ImageQualityAnalyzerTest.checkerboard(128, 96, 8);

        var selected = selector.select(SceneCandidate.contentChange(30.0, 0.05), List.of(
            new StableFrameSelector.FrameSample(29.8, before),
            new StableFrameSelector.FrameSample(30.4, after)
        ));

        assertThat(selected).hasValueSatisfying(value ->
            assertThat(value.timestampSeconds()).isEqualTo(30.4));
    }

    @Test
    void detectedChangeNeverFallsBackToReadableOldScene() {
        StableFrameSelector selector = new StableFrameSelector(analyzer);

        var selected = selector.select(SceneCandidate.sceneChange(30.0, 0.9), List.of(
            new StableFrameSelector.FrameSample(29.8, ImageQualityAnalyzerTest.checkerboard(128, 96, 8)),
            new StableFrameSelector.FrameSample(30.4, ImageQualityAnalyzerTest.solid(128, 96, Color.BLACK))
        ));

        assertThat(selected).isEmpty();
    }

    private static BufferedImage verticalBars(int width, int height, int barWidth) {
        BufferedImage image = new BufferedImage(width, height, BufferedImage.TYPE_INT_RGB);
        for (int y = 0; y < height; y++) {
            for (int x = 0; x < width; x++) {
                int value = (x / barWidth) % 2 == 0 ? 70 : 190;
                image.setRGB(x, y, new Color(value, value, value).getRGB());
            }
        }
        return image;
    }
}
