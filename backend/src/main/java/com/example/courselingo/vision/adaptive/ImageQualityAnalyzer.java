package com.example.courselingo.vision.adaptive;

import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import javax.imageio.ImageIO;

/** Pure-Java image metrics computed on a bounded grayscale representation. */
public final class ImageQualityAnalyzer {

    public record Config(
        int analysisMaxDimension,
        double blackMeanThreshold,
        double blackVarianceThreshold,
        double blankVarianceThreshold,
        double blankEdgeDensityThreshold,
        double edgeGradientThreshold,
        double sharpnessNormalization
    ) {

        public Config {
            if (analysisMaxDimension < 16 || analysisMaxDimension > 2_048) {
                throw new IllegalArgumentException("analysisMaxDimension must be between 16 and 2048");
            }
            requireRange(blackMeanThreshold, 0.0, 255.0, "blackMeanThreshold");
            requireNonNegative(blackVarianceThreshold, "blackVarianceThreshold");
            requireNonNegative(blankVarianceThreshold, "blankVarianceThreshold");
            requireRange(blankEdgeDensityThreshold, 0.0, 1.0, "blankEdgeDensityThreshold");
            requireNonNegative(edgeGradientThreshold, "edgeGradientThreshold");
            if (!Double.isFinite(sharpnessNormalization) || sharpnessNormalization <= 0.0) {
                throw new IllegalArgumentException("sharpnessNormalization must be positive");
            }
        }

        public static Config defaults() {
            return new Config(256, 14.0, 80.0, 30.0, 0.006, 28.0, 1_200.0);
        }

        private static void requireRange(double value, double min, double max, String name) {
            if (!Double.isFinite(value) || value < min || value > max) {
                throw new IllegalArgumentException(name + " is out of range");
            }
        }

        private static void requireNonNegative(double value, String name) {
            if (!Double.isFinite(value) || value < 0.0) {
                throw new IllegalArgumentException(name + " must be non-negative");
            }
        }
    }

    private final Config config;

    public ImageQualityAnalyzer() {
        this(Config.defaults());
    }

    public ImageQualityAnalyzer(Config config) {
        this.config = Objects.requireNonNull(config, "config");
    }

    public ImageQualityAnalysis analyze(Path image) {
        return analyze(read(image));
    }

    public ImageQualityAnalysis analyze(Path image, Path neighbor, double sceneChangeScore) {
        return analyze(read(image), neighbor == null ? null : read(neighbor), sceneChangeScore);
    }

    public ImageQualityAnalysis analyze(BufferedImage image) {
        return analyze(image, List.of(), 0.0);
    }

    public ImageQualityAnalysis analyze(BufferedImage image, BufferedImage neighbor, double sceneChangeScore) {
        return analyze(image, neighbor == null ? List.of() : List.of(neighbor), sceneChangeScore);
    }

    public ImageQualityAnalysis analyze(
        BufferedImage image,
        List<BufferedImage> neighbors,
        double sceneChangeScore
    ) {
        Objects.requireNonNull(image, "image");
        if (image.getWidth() <= 0 || image.getHeight() <= 0) {
            throw new IllegalArgumentException("image dimensions must be positive");
        }
        BufferedImage bounded = boundedCopy(image, config.analysisMaxDimension());
        double[][] gray = grayscale(bounded);
        Moments moments = moments(gray);
        double laplacianVariance = laplacianVariance(gray);
        double edgeDensity = edgeDensity(gray, config.edgeGradientThreshold());
        boolean black = moments.mean() <= config.blackMeanThreshold()
            && moments.variance() <= config.blackVarianceThreshold();
        boolean blank = !black
            && moments.variance() <= config.blankVarianceThreshold()
            && edgeDensity <= config.blankEdgeDensityThreshold();
        long hash = differenceHash(image);
        String contentFingerprint = contentFingerprint(bounded);
        double stability = averageStability(image, neighbors);
        double boundedSceneScore = unit(sceneChangeScore);

        Map<String, Double> components = score(
            laplacianVariance,
            moments.mean(),
            moments.variance(),
            edgeDensity,
            stability,
            boundedSceneScore,
            black,
            blank
        );
        double total = components.values().stream().mapToDouble(Double::doubleValue).sum();
        total = Math.max(0.0, Math.min(100.0, total));
        String explanation = "clarity=" + rounded(components.get("clarity"))
            + ", brightness=" + rounded(components.get("brightness"))
            + ", contrast=" + rounded(components.get("contrast"))
            + ", edges=" + rounded(components.get("edges"))
            + ", stability=" + rounded(components.get("stability"))
            + ", scene=" + rounded(components.get("scene"))
            + ", penalty=" + rounded(components.get("penalty"));
        return new ImageQualityAnalysis(
            image.getWidth(),
            image.getHeight(),
            laplacianVariance,
            moments.mean(),
            moments.variance(),
            black,
            blank,
            edgeDensity,
            hash,
            contentFingerprint,
            stability,
            boundedSceneScore,
            total,
            components,
            explanation
        );
    }

    public static long differenceHash(BufferedImage image) {
        Objects.requireNonNull(image, "image");
        BufferedImage scaled = resize(image, 9, 8);
        long hash = 0L;
        int bit = 0;
        for (int y = 0; y < 8; y++) {
            for (int x = 0; x < 8; x++) {
                if (gray(scaled.getRGB(x, y)) > gray(scaled.getRGB(x + 1, y))) {
                    hash |= 1L << bit;
                }
                bit++;
            }
        }
        return hash;
    }

    public static String contentFingerprint(BufferedImage image) {
        Objects.requireNonNull(image, "image");
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            for (int y = 0; y < image.getHeight(); y++) {
                for (int x = 0; x < image.getWidth(); x++) {
                    int rgb = image.getRGB(x, y);
                    digest.update((byte) ((rgb >>> 16) & 0xff));
                    digest.update((byte) ((rgb >>> 8) & 0xff));
                    digest.update((byte) (rgb & 0xff));
                }
            }
            return HexFormat.of().formatHex(digest.digest());
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is unavailable", exception);
        }
    }

    public static double stability(BufferedImage first, BufferedImage second) {
        Objects.requireNonNull(first, "first");
        Objects.requireNonNull(second, "second");
        BufferedImage left = resize(first, 64, 64);
        BufferedImage right = resize(second, 64, 64);
        double totalDifference = 0.0;
        for (int y = 0; y < 64; y++) {
            for (int x = 0; x < 64; x++) {
                totalDifference += Math.abs(gray(left.getRGB(x, y)) - gray(right.getRGB(x, y)));
            }
        }
        return unit(1.0 - totalDifference / (64.0 * 64.0 * 255.0));
    }

    private Map<String, Double> score(
        double sharpness,
        double mean,
        double variance,
        double edgeDensity,
        double stability,
        double sceneScore,
        boolean black,
        boolean blank
    ) {
        Map<String, Double> values = new LinkedHashMap<>();
        values.put("clarity", unit(sharpness / config.sharpnessNormalization()) * 35.0);
        double brightnessFitness = 1.0 - Math.min(1.0, Math.abs(mean - 135.0) / 135.0);
        values.put("brightness", brightnessFitness * 12.0);
        values.put("contrast", unit(variance / 2_000.0) * 13.0);
        values.put("edges", unit(edgeDensity / 0.15) * 10.0);
        values.put("stability", stability * 25.0);
        values.put("scene", sceneScore * 5.0);
        values.put("penalty", black ? -100.0 : blank ? -55.0 : 0.0);
        return values;
    }

    private static double averageStability(BufferedImage image, List<BufferedImage> neighbors) {
        if (neighbors == null || neighbors.isEmpty()) {
            return 0.5;
        }
        List<Double> values = new ArrayList<>();
        for (BufferedImage neighbor : neighbors) {
            if (neighbor != null) {
                values.add(stability(image, neighbor));
            }
        }
        return values.isEmpty() ? 0.5 : values.stream().mapToDouble(Double::doubleValue).average().orElse(0.5);
    }

    private static BufferedImage boundedCopy(BufferedImage source, int maximumDimension) {
        int largest = Math.max(source.getWidth(), source.getHeight());
        if (largest <= maximumDimension) {
            return source;
        }
        double factor = maximumDimension / (double) largest;
        return resize(source, Math.max(1, (int) Math.round(source.getWidth() * factor)),
            Math.max(1, (int) Math.round(source.getHeight() * factor)));
    }

    private static BufferedImage resize(BufferedImage source, int width, int height) {
        BufferedImage target = new BufferedImage(width, height, BufferedImage.TYPE_INT_RGB);
        Graphics2D graphics = target.createGraphics();
        try {
            graphics.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BILINEAR);
            graphics.setRenderingHint(RenderingHints.KEY_RENDERING, RenderingHints.VALUE_RENDER_QUALITY);
            graphics.drawImage(source, 0, 0, width, height, null);
        } finally {
            graphics.dispose();
        }
        return target;
    }

    private static double[][] grayscale(BufferedImage image) {
        double[][] result = new double[image.getHeight()][image.getWidth()];
        for (int y = 0; y < image.getHeight(); y++) {
            for (int x = 0; x < image.getWidth(); x++) {
                result[y][x] = gray(image.getRGB(x, y));
            }
        }
        return result;
    }

    private static Moments moments(double[][] pixels) {
        double sum = 0.0;
        double sumSquares = 0.0;
        long count = 0;
        for (double[] row : pixels) {
            for (double value : row) {
                sum += value;
                sumSquares += value * value;
                count++;
            }
        }
        double mean = count == 0 ? 0.0 : sum / count;
        return new Moments(mean, count == 0 ? 0.0 : Math.max(0.0, sumSquares / count - mean * mean));
    }

    private static double laplacianVariance(double[][] pixels) {
        int height = pixels.length;
        int width = height == 0 ? 0 : pixels[0].length;
        if (width < 3 || height < 3) {
            return 0.0;
        }
        double sum = 0.0;
        double sumSquares = 0.0;
        long count = 0;
        for (int y = 1; y < height - 1; y++) {
            for (int x = 1; x < width - 1; x++) {
                double value = pixels[y - 1][x] + pixels[y + 1][x]
                    + pixels[y][x - 1] + pixels[y][x + 1] - 4.0 * pixels[y][x];
                sum += value;
                sumSquares += value * value;
                count++;
            }
        }
        double mean = count == 0 ? 0.0 : sum / count;
        return count == 0 ? 0.0 : Math.max(0.0, sumSquares / count - mean * mean);
    }

    private static double edgeDensity(double[][] pixels, double threshold) {
        int height = pixels.length;
        int width = height == 0 ? 0 : pixels[0].length;
        if (width < 3 || height < 3) {
            return 0.0;
        }
        long edges = 0;
        long count = 0;
        for (int y = 1; y < height - 1; y++) {
            for (int x = 1; x < width - 1; x++) {
                double gradient = Math.abs(pixels[y][x + 1] - pixels[y][x - 1])
                    + Math.abs(pixels[y + 1][x] - pixels[y - 1][x]);
                if (gradient >= threshold) {
                    edges++;
                }
                count++;
            }
        }
        return count == 0 ? 0.0 : edges / (double) count;
    }

    private static double gray(int rgb) {
        int red = (rgb >>> 16) & 0xff;
        int green = (rgb >>> 8) & 0xff;
        int blue = rgb & 0xff;
        return red * 0.299 + green * 0.587 + blue * 0.114;
    }

    private static BufferedImage read(Path path) {
        Objects.requireNonNull(path, "path");
        try {
            BufferedImage image = ImageIO.read(path.toFile());
            if (image == null) {
                throw new IllegalArgumentException("Unsupported image: " + path.getFileName());
            }
            return image;
        } catch (IOException ex) {
            throw new IllegalArgumentException("Could not read image: " + path.getFileName(), ex);
        }
    }

    private static double unit(double value) {
        return Double.isFinite(value) ? Math.max(0.0, Math.min(1.0, value)) : 0.0;
    }

    private static double rounded(double value) {
        return Math.round(value * 100.0) / 100.0;
    }

    private record Moments(double mean, double variance) {
    }
}
