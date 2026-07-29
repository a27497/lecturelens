package com.example.courselingo.vision.adaptive;

import static org.assertj.core.api.Assertions.assertThat;

import java.awt.Color;
import java.awt.Graphics2D;
import java.awt.image.BufferedImage;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashSet;
import java.util.Set;
import javax.imageio.ImageIO;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class OcrImagePreprocessorTest {

    @TempDir
    Path tempDirectory;

    private final OcrImagePreprocessor preprocessor = new OcrImagePreprocessor();

    @Test
    void preservesOriginalAndWritesSeparateEnhancedPngWithoutDefaultBinarization() throws Exception {
        Path source = tempDirectory.resolve("code frame.png");
        ImageIO.write(codeLikeImage(), "png", source.toFile());
        byte[] before = Files.readAllBytes(source);
        OcrImagePreprocessor.Options options = new OcrImagePreprocessor.Options(800, 1.5, 1.2, 0.15, false);

        OcrPreprocessingResult result = preprocessor.preprocess(source, tempDirectory.resolve("ocr"), options);

        assertThat(result.originalImage()).isEqualTo(source.toAbsolutePath().normalize());
        assertThat(result.enhancedImage()).isNotEqualTo(result.originalImage()).exists();
        assertThat(result.enhancedImage().getFileName().toString()).endsWith(".png");
        assertThat(Files.readAllBytes(source)).isEqualTo(before);
        assertThat(result.binarized()).isFalse();
        BufferedImage enhanced = ImageIO.read(result.enhancedImage().toFile());
        assertThat(enhanced.getWidth()).isEqualTo(200);
        assertThat(distinctValues(enhanced)).hasSizeGreaterThan(2);
        assertThat(enhanced.getRaster().getSample(5, 20, 0)).isGreaterThan(220);
    }

    @Test
    void optionalOtsuBinarizationProducesOnlyBlackAndWhite() {
        BufferedImage enhanced = preprocessor.enhance(codeLikeImage(),
            new OcrImagePreprocessor.Options(500, 1.0, 1.2, 0.1, true));

        assertThat(distinctValues(enhanced)).containsOnly(0, 255);
    }

    @Test
    void maximumWidthNeverUpscalesAndPreservesAspectRatio() {
        BufferedImage source = new BufferedImage(1_600, 900, BufferedImage.TYPE_INT_RGB);

        BufferedImage enhanced = preprocessor.enhance(source,
            new OcrImagePreprocessor.Options(2_000, 2.0, 1.0, 0.0, false));

        assertThat(enhanced.getWidth()).isEqualTo(1_600);
        assertThat(enhanced.getHeight()).isEqualTo(900);
    }

    private static BufferedImage codeLikeImage() {
        BufferedImage image = new BufferedImage(200, 100, BufferedImage.TYPE_INT_RGB);
        Graphics2D graphics = image.createGraphics();
        graphics.setColor(Color.WHITE);
        graphics.fillRect(0, 0, 200, 100);
        graphics.setColor(new Color(40, 40, 40));
        graphics.fillRect(35, 20, 130, 4);
        graphics.setColor(new Color(90, 90, 90));
        graphics.fillRect(55, 40, 90, 4);
        graphics.setColor(new Color(150, 150, 150));
        graphics.fillRect(55, 60, 115, 4);
        graphics.dispose();
        return image;
    }

    private static Set<Integer> distinctValues(BufferedImage image) {
        Set<Integer> result = new HashSet<>();
        for (int y = 0; y < image.getHeight(); y++) {
            for (int x = 0; x < image.getWidth(); x++) {
                result.add(image.getRaster().getSample(x, y, 0));
            }
        }
        return result;
    }
}
