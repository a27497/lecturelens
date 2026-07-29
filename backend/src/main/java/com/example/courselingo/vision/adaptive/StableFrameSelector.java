package com.example.courselingo.vision.adaptive;

import java.awt.image.BufferedImage;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

/** Selects a readable frame near a candidate instead of using the transition instant directly. */
public final class StableFrameSelector {

    public record Config(
        List<Double> samplingOffsetsSeconds,
        double minimumLaplacianVariance,
        double minimumEdgeDensity,
        double minimumTotalScore,
        double relaxedThresholdFactor
    ) {

        public Config {
            if (samplingOffsetsSeconds == null || samplingOffsetsSeconds.isEmpty()
                || samplingOffsetsSeconds.stream().anyMatch(value -> value == null || !Double.isFinite(value))) {
                throw new IllegalArgumentException("samplingOffsetsSeconds must contain finite values");
            }
            samplingOffsetsSeconds = List.copyOf(samplingOffsetsSeconds);
            requireNonNegative(minimumLaplacianVariance, "minimumLaplacianVariance");
            requireNonNegative(minimumEdgeDensity, "minimumEdgeDensity");
            requireNonNegative(minimumTotalScore, "minimumTotalScore");
            if (!Double.isFinite(relaxedThresholdFactor) || relaxedThresholdFactor <= 0.0
                || relaxedThresholdFactor > 1.0) {
                throw new IllegalArgumentException("relaxedThresholdFactor must be in (0, 1]");
            }
        }

        public static Config defaults() {
            return new Config(List.of(-0.2, 0.4, 0.9, 1.4), 45.0, 0.002, 32.0, 0.35);
        }

        private static void requireNonNegative(double value, String name) {
            if (!Double.isFinite(value) || value < 0.0) {
                throw new IllegalArgumentException(name + " must be non-negative");
            }
        }
    }

    public record FrameSample(double timestampSeconds, BufferedImage image) {

        public FrameSample {
            if (!Double.isFinite(timestampSeconds) || timestampSeconds < 0.0) {
                throw new IllegalArgumentException("timestampSeconds must be finite and non-negative");
            }
            Objects.requireNonNull(image, "image");
        }
    }

    public record SelectedStableFrame(
        double timestampSeconds,
        BufferedImage image,
        ImageQualityAnalysis quality,
        boolean relaxed
    ) {
    }

    private record Scored(FrameSample sample, ImageQualityAnalysis quality) {
    }

    private final Config config;
    private final ImageQualityAnalyzer analyzer;

    public StableFrameSelector(ImageQualityAnalyzer analyzer) {
        this(Config.defaults(), analyzer);
    }

    public StableFrameSelector(Config config, ImageQualityAnalyzer analyzer) {
        this.config = Objects.requireNonNull(config, "config");
        this.analyzer = Objects.requireNonNull(analyzer, "analyzer");
    }

    public List<Double> sampleTimestamps(double candidateTimestampSeconds, double durationSeconds) {
        if (!Double.isFinite(candidateTimestampSeconds) || !Double.isFinite(durationSeconds)
            || candidateTimestampSeconds < 0.0 || durationSeconds < 0.0) {
            throw new IllegalArgumentException("timestamps must be finite and non-negative");
        }
        return config.samplingOffsetsSeconds().stream()
            .map(offset -> Math.max(0.0, Math.min(durationSeconds, candidateTimestampSeconds + offset)))
            .distinct()
            .sorted()
            .toList();
    }

    public Optional<SelectedStableFrame> select(SceneCandidate candidate, List<FrameSample> samples) {
        Objects.requireNonNull(candidate, "candidate");
        if (samples == null || samples.isEmpty()) {
            return Optional.empty();
        }
        List<Scored> scored = new ArrayList<>();
        for (int index = 0; index < samples.size(); index++) {
            FrameSample sample = samples.get(index);
            if (sample == null) {
                continue;
            }
            List<BufferedImage> neighbors = new ArrayList<>(2);
            if (index > 0 && samples.get(index - 1) != null) {
                neighbors.add(samples.get(index - 1).image());
            }
            if (index + 1 < samples.size() && samples.get(index + 1) != null) {
                neighbors.add(samples.get(index + 1).image());
            }
            scored.add(new Scored(sample, analyzer.analyze(sample.image(), neighbors, candidate.score())));
        }
        Comparator<Scored> bestFirst = Comparator
            .comparingDouble((Scored value) -> selectionScore(value.quality())).reversed()
            .thenComparingInt(value -> transitionSidePenalty(candidate, value))
            .thenComparingDouble(value -> Math.abs(value.sample().timestampSeconds() - candidate.timestampSeconds()));

        boolean detectedChange = candidate.source() == SceneCandidate.Source.SCENE_CHANGE
            || candidate.source() == SceneCandidate.Source.CONTENT_CHANGE;
        Optional<Scored> strict = scored.stream()
            .filter(value -> strictlyReadable(value.quality()))
            .filter(value -> !detectedChange
                || value.sample().timestampSeconds() >= candidate.timestampSeconds())
            .min(bestFirst);
        if (strict.isPresent()) {
            return strict.map(value -> selected(value, false));
        }

        boolean coverageAnchor = candidate.source() == SceneCandidate.Source.PERIODIC_ANCHOR
            || candidate.source() == SceneCandidate.Source.WINDOW_COVERAGE
            || candidate.source() == SceneCandidate.Source.START
            || candidate.source() == SceneCandidate.Source.END;
        if (!coverageAnchor) {
            return Optional.empty();
        }
        return scored.stream()
            .filter(value -> relaxedReadable(value.quality()))
            .min(bestFirst)
            .map(value -> selected(value, true));
    }

    private boolean strictlyReadable(ImageQualityAnalysis quality) {
        return !quality.black()
            && !quality.blank()
            && quality.laplacianVariance() >= config.minimumLaplacianVariance()
            && quality.edgeDensity() >= config.minimumEdgeDensity()
            && quality.totalScore() >= config.minimumTotalScore();
    }

    private boolean relaxedReadable(ImageQualityAnalysis quality) {
        return !quality.black()
            && !quality.blank()
            && quality.laplacianVariance() >= config.minimumLaplacianVariance() * config.relaxedThresholdFactor()
            && quality.edgeDensity() >= config.minimumEdgeDensity() * config.relaxedThresholdFactor()
            && quality.totalScore() >= config.minimumTotalScore() * config.relaxedThresholdFactor();
    }

    private static double selectionScore(ImageQualityAnalysis quality) {
        return quality.totalScore() + quality.stability() * 15.0;
    }

    private static int transitionSidePenalty(SceneCandidate candidate, Scored value) {
        boolean detectedChange = candidate.source() == SceneCandidate.Source.SCENE_CHANGE
            || candidate.source() == SceneCandidate.Source.CONTENT_CHANGE;
        return detectedChange && value.sample().timestampSeconds() < candidate.timestampSeconds() ? 1 : 0;
    }

    private static SelectedStableFrame selected(Scored value, boolean relaxed) {
        return new SelectedStableFrame(
            value.sample().timestampSeconds(),
            value.sample().image(),
            value.quality(),
            relaxed
        );
    }
}
