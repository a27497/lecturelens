package com.example.courselingo.vision.adaptive;

import static org.assertj.core.api.Assertions.assertThat;

import java.awt.Color;
import java.awt.Graphics2D;
import java.awt.image.BufferedImage;
import org.junit.jupiter.api.Test;

class ImageQualityAnalyzerTest {

    private final ImageQualityAnalyzer analyzer = new ImageQualityAnalyzer();

    @Test
    void identifiesBlackAndNearPureWhiteFrames() {
        ImageQualityAnalysis black = analyzer.analyze(solid(96, 64, new Color(2, 2, 2)));
        ImageQualityAnalysis white = analyzer.analyze(solid(96, 64, Color.WHITE));

        assertThat(black.black()).isTrue();
        assertThat(black.totalScore()).isZero();
        assertThat(white.black()).isFalse();
        assertThat(white.blank()).isTrue();
        assertThat(white.totalScore()).isLessThan(20.0);
    }

    @Test
    void sharpStructuredFrameHasEdgesVarianceAndHigherExplainableScore() {
        ImageQualityAnalysis flat = analyzer.analyze(solid(128, 96, new Color(130, 130, 130)));
        ImageQualityAnalysis sharp = analyzer.analyze(checkerboard(128, 96, 8));

        assertThat(sharp.laplacianVariance()).isGreaterThan(flat.laplacianVariance());
        assertThat(sharp.brightnessVariance()).isGreaterThan(flat.brightnessVariance());
        assertThat(sharp.edgeDensity()).isGreaterThan(0.1);
        assertThat(sharp.totalScore()).isGreaterThan(flat.totalScore());
        assertThat(sharp.scoreComponents()).containsKeys(
            "clarity", "brightness", "contrast", "edges", "stability", "scene", "penalty");
        assertThat(sharp.explanation()).contains("clarity=", "stability=", "penalty=");
    }

    @Test
    void computesDeterministicDhashAndNeighborStabilityWithoutChangingSource() {
        BufferedImage first = checkerboard(90, 80, 9);
        BufferedImage same = checkerboard(90, 80, 9);
        BufferedImage different = horizontalGradient(90, 80);
        int originalWidth = first.getWidth();

        ImageQualityAnalysis analysis = analyzer.analyze(first, same, 0.75);

        assertThat(analysis.perceptualHash()).isEqualTo(ImageQualityAnalyzer.differenceHash(same));
        assertThat(analysis.contentFingerprint()).isEqualTo(ImageQualityAnalyzer.contentFingerprint(same));
        assertThat(analysis.contentFingerprint()).isNotEqualTo(ImageQualityAnalyzer.contentFingerprint(different));
        assertThat(analysis.stability()).isEqualTo(1.0);
        assertThat(analysis.sceneChangeScore()).isEqualTo(0.75);
        assertThat(PerceptualHashDeduplicator.hammingDistance(
            analysis.perceptualHash(), ImageQualityAnalyzer.differenceHash(different))).isPositive();
        assertThat(first.getWidth()).isEqualTo(originalWidth);
    }

    static BufferedImage solid(int width, int height, Color color) {
        BufferedImage image = new BufferedImage(width, height, BufferedImage.TYPE_INT_RGB);
        Graphics2D graphics = image.createGraphics();
        graphics.setColor(color);
        graphics.fillRect(0, 0, width, height);
        graphics.dispose();
        return image;
    }

    static BufferedImage checkerboard(int width, int height, int cell) {
        BufferedImage image = new BufferedImage(width, height, BufferedImage.TYPE_INT_RGB);
        for (int y = 0; y < height; y++) {
            for (int x = 0; x < width; x++) {
                int value = ((x / cell) + (y / cell)) % 2 == 0 ? 25 : 235;
                image.setRGB(x, y, new Color(value, value, value).getRGB());
            }
        }
        return image;
    }

    static BufferedImage horizontalGradient(int width, int height) {
        BufferedImage image = new BufferedImage(width, height, BufferedImage.TYPE_INT_RGB);
        for (int y = 0; y < height; y++) {
            for (int x = 0; x < width; x++) {
                int value = x * 255 / Math.max(1, width - 1);
                image.setRGB(x, y, new Color(value, value, value).getRGB());
            }
        }
        return image;
    }
}
