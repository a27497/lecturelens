package com.example.courselingo.vision.keyframe;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.nio.file.Path;
import javax.imageio.ImageIO;
import org.springframework.stereotype.Component;

@Component
public class FrameDifferenceCalculator {

    public FrameChangeScore score(Path previousFrame, Path currentFrame, int pixelDiffThreshold) {
        if (previousFrame == null || currentFrame == null) {
            return FrameChangeScore.none();
        }
        try {
            BufferedImage previous = ImageIO.read(previousFrame.toFile());
            BufferedImage current = ImageIO.read(currentFrame.toFile());
            if (previous == null || current == null) {
                return FrameChangeScore.none();
            }
            return score(previous, current, pixelDiffThreshold);
        } catch (IOException ex) {
            throw new BusinessException(ErrorCode.MEDIA_INPUT_INVALID, "Keyframe image diff failed", ex);
        }
    }

    private static FrameChangeScore score(BufferedImage previous, BufferedImage current, int pixelDiffThreshold) {
        int width = Math.min(previous.getWidth(), current.getWidth());
        int height = Math.min(previous.getHeight(), current.getHeight());
        if (width <= 0 || height <= 0) {
            return FrameChangeScore.none();
        }
        int stepX = Math.max(1, width / 96);
        int stepY = Math.max(1, height / 96);
        long samples = 0;
        double totalDelta = 0.0;
        long changed = 0;
        int threshold = Math.max(1, pixelDiffThreshold);
        for (int y = 0; y < height; y += stepY) {
            for (int x = 0; x < width; x += stepX) {
                double delta = Math.abs(gray(previous.getRGB(x, y)) - gray(current.getRGB(x, y)));
                totalDelta += delta;
                if (delta >= threshold) {
                    changed++;
                }
                samples++;
            }
        }
        if (samples == 0) {
            return FrameChangeScore.none();
        }
        return new FrameChangeScore(totalDelta / samples, (double) changed / samples);
    }

    private static double gray(int rgb) {
        int red = (rgb >> 16) & 0xff;
        int green = (rgb >> 8) & 0xff;
        int blue = rgb & 0xff;
        return red * 0.299 + green * 0.587 + blue * 0.114;
    }
}
