package com.example.courselingo.vision.adaptive;

import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;
import javax.imageio.ImageIO;

/** OCR enhancement that never mutates the source image and always emits lossless PNG. */
public final class OcrImagePreprocessor {

    public record Options(
        int maximumWidth,
        double scaleFactor,
        double contrastFactor,
        double sharpenAmount,
        boolean binarize
    ) {

        public Options {
            if (maximumWidth < 64 || maximumWidth > 8_192) {
                throw new IllegalArgumentException("maximumWidth must be between 64 and 8192");
            }
            if (!Double.isFinite(scaleFactor) || scaleFactor < 0.5 || scaleFactor > 4.0) {
                throw new IllegalArgumentException("scaleFactor must be between 0.5 and 4.0");
            }
            if (!Double.isFinite(contrastFactor) || contrastFactor < 0.5 || contrastFactor > 3.0) {
                throw new IllegalArgumentException("contrastFactor must be between 0.5 and 3.0");
            }
            if (!Double.isFinite(sharpenAmount) || sharpenAmount < 0.0 || sharpenAmount > 1.0) {
                throw new IllegalArgumentException("sharpenAmount must be between 0 and 1");
            }
        }

        public static Options defaults() {
            return new Options(2_000, 1.5, 1.25, 0.18, false);
        }
    }

    public OcrPreprocessingResult preprocess(Path source, Path outputDirectory) {
        return preprocess(source, outputDirectory, Options.defaults());
    }

    public OcrPreprocessingResult preprocess(Path source, Path outputDirectory, Options options) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(outputDirectory, "outputDirectory");
        Objects.requireNonNull(options, "options");
        Path original = source.toAbsolutePath().normalize();
        BufferedImage image = read(original);
        BufferedImage enhanced = enhance(image, options);
        Path directory = outputDirectory.toAbsolutePath().normalize();
        try {
            Files.createDirectories(directory);
            String fileName = safeBaseName(original.getFileName().toString()) + ".ocr-enhanced.png";
            Path output = directory.resolve(fileName).normalize();
            if (!output.startsWith(directory) || output.equals(original)) {
                throw new IllegalArgumentException("Enhanced OCR image must be separate from its source");
            }
            if (!ImageIO.write(enhanced, "png", output.toFile())) {
                throw new IllegalStateException("PNG writer is unavailable");
            }
            return new OcrPreprocessingResult(
                original,
                output,
                options.binarize(),
                enhanced.getWidth(),
                enhanced.getHeight()
            );
        } catch (IOException ex) {
            throw new IllegalArgumentException("Could not write enhanced OCR image", ex);
        }
    }

    public BufferedImage enhance(BufferedImage source, Options options) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(options, "options");
        if (source.getWidth() <= 0 || source.getHeight() <= 0) {
            throw new IllegalArgumentException("source dimensions must be positive");
        }
        BufferedImage scaled = scale(source, options);
        int width = scaled.getWidth();
        int height = scaled.getHeight();
        int[][] gray = new int[height][width];
        long sum = 0L;
        for (int y = 0; y < height; y++) {
            for (int x = 0; x < width; x++) {
                int value = gray(scaled.getRGB(x, y));
                gray[y][x] = value;
                sum += value;
            }
        }
        double mean = sum / (double) (width * (long) height);
        for (int y = 0; y < height; y++) {
            for (int x = 0; x < width; x++) {
                gray[y][x] = clamp(mean + (gray[y][x] - mean) * options.contrastFactor());
            }
        }
        int[][] sharpened = sharpen(gray, options.sharpenAmount());
        if (options.binarize()) {
            int threshold = otsuThreshold(sharpened);
            for (int y = 0; y < height; y++) {
                for (int x = 0; x < width; x++) {
                    sharpened[y][x] = sharpened[y][x] > threshold ? 255 : 0;
                }
            }
        }
        BufferedImage result = new BufferedImage(width, height, BufferedImage.TYPE_BYTE_GRAY);
        for (int y = 0; y < height; y++) {
            for (int x = 0; x < width; x++) {
                int value = sharpened[y][x];
                result.getRaster().setSample(x, y, 0, value);
            }
        }
        return result;
    }

    private static BufferedImage scale(BufferedImage source, Options options) {
        int targetWidth = Math.min(source.getWidth(), options.maximumWidth());
        int targetHeight = Math.max(1,
            (int) Math.round(source.getHeight() * (targetWidth / (double) source.getWidth())));
        if (targetWidth == source.getWidth() && targetHeight == source.getHeight()) {
            return source;
        }
        BufferedImage scaled = new BufferedImage(targetWidth, targetHeight, BufferedImage.TYPE_INT_RGB);
        Graphics2D graphics = scaled.createGraphics();
        try {
            graphics.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BICUBIC);
            graphics.setRenderingHint(RenderingHints.KEY_RENDERING, RenderingHints.VALUE_RENDER_QUALITY);
            graphics.drawImage(source, 0, 0, targetWidth, targetHeight, null);
        } finally {
            graphics.dispose();
        }
        return scaled;
    }

    private static int[][] sharpen(int[][] source, double amount) {
        int height = source.length;
        int width = height == 0 ? 0 : source[0].length;
        int[][] result = new int[height][width];
        for (int y = 0; y < height; y++) {
            System.arraycopy(source[y], 0, result[y], 0, width);
        }
        if (amount == 0.0 || width < 3 || height < 3) {
            return result;
        }
        for (int y = 1; y < height - 1; y++) {
            for (int x = 1; x < width - 1; x++) {
                double blurred = (source[y - 1][x] + source[y + 1][x]
                    + source[y][x - 1] + source[y][x + 1]) / 4.0;
                result[y][x] = clamp(source[y][x] + amount * (source[y][x] - blurred));
            }
        }
        return result;
    }

    private static int otsuThreshold(int[][] values) {
        long[] histogram = new long[256];
        long total = 0;
        long sum = 0;
        for (int[] row : values) {
            for (int value : row) {
                histogram[value]++;
                total++;
                sum += value;
            }
        }
        long backgroundWeight = 0;
        long backgroundSum = 0;
        double greatestVariance = -1.0;
        int threshold = 127;
        for (int value = 0; value < 256; value++) {
            backgroundWeight += histogram[value];
            if (backgroundWeight == 0) {
                continue;
            }
            long foregroundWeight = total - backgroundWeight;
            if (foregroundWeight == 0) {
                break;
            }
            backgroundSum += (long) value * histogram[value];
            double backgroundMean = backgroundSum / (double) backgroundWeight;
            double foregroundMean = (sum - backgroundSum) / (double) foregroundWeight;
            double between = backgroundWeight * (double) foregroundWeight
                * (backgroundMean - foregroundMean) * (backgroundMean - foregroundMean);
            if (between > greatestVariance) {
                greatestVariance = between;
                threshold = value;
            }
        }
        return threshold;
    }

    private static BufferedImage read(Path source) {
        try {
            BufferedImage image = ImageIO.read(source.toFile());
            if (image == null) {
                throw new IllegalArgumentException("Unsupported image: " + source.getFileName());
            }
            return image;
        } catch (IOException ex) {
            throw new IllegalArgumentException("Could not read image: " + source.getFileName(), ex);
        }
    }

    private static int gray(int rgb) {
        int red = (rgb >>> 16) & 0xff;
        int green = (rgb >>> 8) & 0xff;
        int blue = rgb & 0xff;
        return clamp(red * 0.299 + green * 0.587 + blue * 0.114);
    }

    private static int clamp(double value) {
        return Math.max(0, Math.min(255, (int) Math.round(value)));
    }

    private static String safeBaseName(String fileName) {
        int dot = fileName.lastIndexOf('.');
        String base = dot > 0 ? fileName.substring(0, dot) : fileName;
        String safe = base.replaceAll("[^A-Za-z0-9._-]", "_");
        return safe.isBlank() ? "frame" : safe;
    }
}
