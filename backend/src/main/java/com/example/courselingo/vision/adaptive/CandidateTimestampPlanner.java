package com.example.courselingo.vision.adaptive;

import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/** Plans bounded candidates independently in every window, preserving full-timeline coverage. */
public final class CandidateTimestampPlanner {

    public record Config(
        double windowSeconds,
        int maxCandidatesPerWindow,
        double mergeDistanceSeconds,
        double shortVideoLimitSeconds,
        double mediumVideoLimitSeconds,
        double shortAnchorIntervalSeconds,
        double mediumAnchorIntervalSeconds,
        double longAnchorIntervalSeconds
    ) {

        public Config {
            requirePositive(windowSeconds, "windowSeconds");
            if (maxCandidatesPerWindow < 1 || maxCandidatesPerWindow > 100) {
                throw new IllegalArgumentException("maxCandidatesPerWindow must be between 1 and 100");
            }
            if (!Double.isFinite(mergeDistanceSeconds) || mergeDistanceSeconds < 0.0
                || mergeDistanceSeconds > windowSeconds) {
                throw new IllegalArgumentException("mergeDistanceSeconds must be within the window");
            }
            requirePositive(shortVideoLimitSeconds, "shortVideoLimitSeconds");
            requirePositive(mediumVideoLimitSeconds, "mediumVideoLimitSeconds");
            if (mediumVideoLimitSeconds < shortVideoLimitSeconds) {
                throw new IllegalArgumentException("mediumVideoLimitSeconds must not be shorter than the short limit");
            }
            requirePositive(shortAnchorIntervalSeconds, "shortAnchorIntervalSeconds");
            requirePositive(mediumAnchorIntervalSeconds, "mediumAnchorIntervalSeconds");
            requirePositive(longAnchorIntervalSeconds, "longAnchorIntervalSeconds");
        }

        public static Config defaults() {
            return new Config(60.0, 6, 1.0, 3_600.0, 7_200.0, 30.0, 45.0, 60.0);
        }

        private static void requirePositive(double value, String name) {
            if (!Double.isFinite(value) || value <= 0.0) {
                throw new IllegalArgumentException(name + " must be finite and positive");
            }
        }
    }

    private static final Comparator<SceneCandidate> BY_SELECTION_PRIORITY = Comparator
        .comparingInt((SceneCandidate candidate) -> priority(candidate.source())).reversed()
        .thenComparing(Comparator.comparingDouble(SceneCandidate::score).reversed())
        .thenComparingDouble(SceneCandidate::timestampSeconds);

    private final Config config;

    public CandidateTimestampPlanner() {
        this(Config.defaults());
    }

    public CandidateTimestampPlanner(Config config) {
        this.config = Objects.requireNonNull(config, "config");
    }

    public Config config() {
        return config;
    }

    public double anchorIntervalSeconds(double durationSeconds) {
        requireDuration(durationSeconds);
        if (durationSeconds <= config.shortVideoLimitSeconds()) {
            return config.shortAnchorIntervalSeconds();
        }
        if (durationSeconds <= config.mediumVideoLimitSeconds()) {
            return config.mediumAnchorIntervalSeconds();
        }
        return config.longAnchorIntervalSeconds();
    }

    public List<SceneCandidate> plan(double durationSeconds, List<SceneCandidate> scenePoints) {
        requireDuration(durationSeconds);
        List<SceneCandidate> all = new ArrayList<>();
        all.add(new SceneCandidate(0.0, SceneCandidate.Source.START, "video-start", 1.0));
        all.add(new SceneCandidate(durationSeconds, SceneCandidate.Source.END, "video-end", 1.0));
        if (scenePoints != null) {
            for (SceneCandidate candidate : scenePoints) {
                if (candidate == null) {
                    continue;
                }
                double clipped = clip(candidate.timestampSeconds(), durationSeconds);
                SceneCandidate.Source source = candidate.source() == SceneCandidate.Source.CONTENT_CHANGE
                    ? SceneCandidate.Source.CONTENT_CHANGE
                    : SceneCandidate.Source.SCENE_CHANGE;
                all.add(new SceneCandidate(clipped, source,
                    candidate.reason(), candidate.score()));
            }
        }

        double interval = anchorIntervalSeconds(durationSeconds);
        for (double timestamp = interval; timestamp < durationSeconds; timestamp += interval) {
            all.add(new SceneCandidate(timestamp, SceneCandidate.Source.PERIODIC_ANCHOR,
                "periodic-coverage", 0.35));
        }

        int windowCount = Math.max(1, (int) Math.ceil(durationSeconds / config.windowSeconds()));
        for (int window = 0; window < windowCount; window++) {
            double start = window * config.windowSeconds();
            double end = Math.min(durationSeconds, start + config.windowSeconds());
            double midpoint = start + Math.max(0.0, end - start) / 2.0;
            all.add(new SceneCandidate(midpoint, SceneCandidate.Source.WINDOW_COVERAGE,
                "window-" + window + "-coverage", 0.2));
        }

        Map<Integer, List<SceneCandidate>> byWindow = new LinkedHashMap<>();
        for (SceneCandidate candidate : all) {
            int window = windowIndex(candidate.timestampSeconds(), durationSeconds, windowCount);
            byWindow.computeIfAbsent(window, ignored -> new ArrayList<>()).add(candidate);
        }

        List<SceneCandidate> selected = new ArrayList<>();
        for (int window = 0; window < windowCount; window++) {
            List<SceneCandidate> merged = mergeNearby(byWindow.getOrDefault(window, List.of()));
            if (merged.size() > config.maxCandidatesPerWindow()) {
                merged = selectFairlyAcrossWindow(merged, window, durationSeconds);
            }
            selected.addAll(merged);
        }
        return selected.stream()
            .sorted(Comparator.comparingDouble(SceneCandidate::timestampSeconds)
                .thenComparing(Comparator.comparingInt(
                    (SceneCandidate candidate) -> priority(candidate.source())).reversed()))
            .toList();
    }

    public List<SceneCandidate> plan(double durationSeconds, Collection<Double> sceneTimestamps) {
        List<SceneCandidate> candidates = sceneTimestamps == null ? List.of() : sceneTimestamps.stream()
            .filter(Objects::nonNull)
            .filter(Double::isFinite)
            .filter(value -> value >= 0.0)
            .map(value -> SceneCandidate.sceneChange(value, 1.0))
            .toList();
        return plan(durationSeconds, candidates);
    }

    private List<SceneCandidate> mergeNearby(List<SceneCandidate> candidates) {
        if (candidates.isEmpty()) {
            return List.of();
        }
        List<SceneCandidate> sorted = candidates.stream()
            .sorted(Comparator.comparingDouble(SceneCandidate::timestampSeconds))
            .toList();
        List<SceneCandidate> merged = new ArrayList<>();
        for (SceneCandidate candidate : sorted) {
            if (merged.isEmpty()) {
                merged.add(candidate);
                continue;
            }
            int lastIndex = merged.size() - 1;
            SceneCandidate previous = merged.get(lastIndex);
            if (candidate.timestampSeconds() - previous.timestampSeconds() <= config.mergeDistanceSeconds()) {
                merged.set(lastIndex, better(previous, candidate));
            } else {
                merged.add(candidate);
            }
        }
        return merged;
    }

    private List<SceneCandidate> selectFairlyAcrossWindow(
        List<SceneCandidate> candidates,
        int windowIndex,
        double durationSeconds
    ) {
        int limit = config.maxCandidatesPerWindow();
        double windowStart = windowIndex * config.windowSeconds();
        double windowEnd = Math.min(durationSeconds, windowStart + config.windowSeconds());
        double bucketWidth = Math.max(0.001d, (windowEnd - windowStart) / limit);
        Map<Integer, List<SceneCandidate>> buckets = new LinkedHashMap<>();
        for (SceneCandidate candidate : candidates) {
            int bucket = Math.min(limit - 1, Math.max(0,
                (int) Math.floor((candidate.timestampSeconds() - windowStart) / bucketWidth)));
            buckets.computeIfAbsent(bucket, ignored -> new ArrayList<>()).add(candidate);
        }

        List<SceneCandidate> selected = new ArrayList<>();
        for (Map.Entry<Integer, List<SceneCandidate>> entry : buckets.entrySet()) {
            double target = windowStart + (entry.getKey() + 0.5d) * bucketWidth;
            SceneCandidate best = entry.getValue().stream()
                .min(Comparator
                    .comparingInt((SceneCandidate candidate) -> priority(candidate.source())).reversed()
                    .thenComparingDouble(candidate -> Math.abs(candidate.timestampSeconds() - target))
                    .thenComparing(Comparator.comparingDouble(SceneCandidate::score).reversed())
                    .thenComparingDouble(SceneCandidate::timestampSeconds))
                .orElseThrow();
            selected.add(best);
        }
        if (selected.size() < limit) {
            candidates.stream()
                .filter(candidate -> !selected.contains(candidate))
                .sorted(BY_SELECTION_PRIORITY)
                .limit(limit - selected.size())
                .forEach(selected::add);
        }
        return selected.stream()
            .sorted(Comparator.comparingDouble(SceneCandidate::timestampSeconds))
            .toList();
    }

    private static SceneCandidate better(SceneCandidate first, SceneCandidate second) {
        int priorityComparison = Integer.compare(priority(first.source()), priority(second.source()));
        if (priorityComparison != 0) {
            return priorityComparison > 0 ? first : second;
        }
        if (Double.compare(first.score(), second.score()) != 0) {
            return first.score() > second.score() ? first : second;
        }
        return first.timestampSeconds() <= second.timestampSeconds() ? first : second;
    }

    private static int priority(SceneCandidate.Source source) {
        return switch (source) {
            case START, END -> 5;
            case SCENE_CHANGE -> 5;
            case CONTENT_CHANGE -> 4;
            case PERIODIC_ANCHOR -> 3;
            case WINDOW_COVERAGE -> 2;
        };
    }

    private int windowIndex(double timestamp, double duration, int count) {
        if (timestamp >= duration) {
            return count - 1;
        }
        return Math.min(count - 1, Math.max(0, (int) Math.floor(timestamp / config.windowSeconds())));
    }

    private static double clip(double value, double duration) {
        return Math.max(0.0, Math.min(duration, value));
    }

    private static void requireDuration(double durationSeconds) {
        if (!Double.isFinite(durationSeconds) || durationSeconds <= 0.0) {
            throw new IllegalArgumentException("durationSeconds must be finite and positive");
        }
    }
}
