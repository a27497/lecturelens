package com.example.courselingo.vision.keyframe;

import static org.assertj.core.api.Assertions.assertThat;

import java.awt.Color;
import java.awt.image.BufferedImage;
import java.nio.file.Path;
import javax.imageio.ImageIO;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class EvidenceImageWriterTest {

    @TempDir
    Path tempDirectory;

    private final EvidenceImageWriter writer = new EvidenceImageWriter();

    @Test
    void lowResolutionImageIsNeverUpscaled() throws Exception {
        BufferedImage source = new BufferedImage(320, 180, BufferedImage.TYPE_INT_RGB);

        BufferedImage output = write(source, "low.jpg", 960);

        assertThat(output.getWidth()).isEqualTo(320);
        assertThat(output.getHeight()).isEqualTo(180);
    }

    @Test
    void sevenTwentyAndTenEightyPImagesRespectEvidenceMaximum() throws Exception {
        assertThat(write(new BufferedImage(1280, 720, BufferedImage.TYPE_INT_RGB), "720p.jpg", 960).getWidth())
            .isEqualTo(960);
        assertThat(write(new BufferedImage(1920, 1080, BufferedImage.TYPE_INT_RGB), "1080p.jpg", 960).getWidth())
            .isEqualTo(960);
    }

    @Test
    void transparentPixelsUseWhiteJpegBackground() throws Exception {
        BufferedImage source = new BufferedImage(320, 180, BufferedImage.TYPE_INT_ARGB);
        source.setRGB(10, 10, new Color(255, 0, 0, 0).getRGB());

        BufferedImage output = write(source, "transparent.jpg", 960);
        Color pixel = new Color(output.getRGB(10, 10));

        assertThat(pixel.getRed()).isGreaterThan(240);
        assertThat(pixel.getGreen()).isGreaterThan(240);
        assertThat(pixel.getBlue()).isGreaterThan(240);
    }

    private BufferedImage write(BufferedImage source, String name, int maximumWidth) throws Exception {
        Path output = writer.write(source, tempDirectory.resolve(name), maximumWidth);
        return ImageIO.read(output.toFile());
    }
}
