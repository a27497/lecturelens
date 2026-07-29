package com.example.courselingo.vision.adaptive;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/**
 * Applies temporal fairness and content-change priority before any OCR process is started.
 * The allocator is deterministic and intentionally independent from OCR text.
 */
public final class PreOcrFrameBudgetAllocator {

    public record Config(
        int windowSeconds,
        int normalMaxFramesPerWindow,
        int contentChangeMaxFramesPerWindow,
        int lowInformationMaxFramesPerWindow,
        int maxFramesTotal
    ) {

        public Config {
            if (windowSeconds <= 0
                || normalMaxFramesPerWindow <= 0
                || contentChangeMaxFramesPerWindow < normalMaxFramesPerWindow
                || lowInformationMaxFramesPerWindow <= 0
                || maxFramesTotal <= 0) {
                throw new IllegalArgumentException("Pre-OCR budget values must be positive and dense limits must not shrink normal limits");
            }
        }
    }

    public record FrameSignal<T>(
        T payload,
        long timestampMillis,
        SceneCandidate.Source source,
        double sourceScore,
        double edgeDensity,
        double qualityScore,
        boolean visualOnlyEligible
    ) {

        public FrameSignal {
            Objects.requireNonNull(payload, "payload");
            timestampMillis = Math.max(0L, timestampMillis);
            source = source == null ? SceneCandidate.Source.WINDOW_COVERAGE : source;
            sourceScore = finite(sourceScore);
            edgeDensity = finite(edgeDensity);
            qualityScore = finite(qualityScore);
        }

        private static double finite(double value) {
            return Double.isFinite(value) ? Math.max(0.0d, value) : 0.0d;
        }
    }

    public record Allocation<T>(List<T> ocrFrames, List<T> visualOnlyFrames, List<T> rejectedFrames) {

        public Allocation {
            ocrFrames = ocrFrames == null ? List.of() : List.copyOf(ocrFrames);
            visualOnlyFrames = visualOnlyFrames == null ? List.of() : List.copyOf(visualOnlyFrames);
            rejectedFrames = rejectedFrames == null ? List.of() : List.copyOf(rejectedFrames);
        }
    }

    private final Config config;

    public PreOcrFrameBudgetAllocator(Config config) {
        this.config = Objects.requireNonNull(config, "config");
    }

    public <T> Allocation<T> allocate(List<FrameSignal<T>> input) {
        List<FrameSignal<T>> ordered = input == null
            ? List.of()
            : input.stream().filter(Objects::nonNull)
                .sorted(Comparator.comparingLong(FrameSignal<T>::timestampMillis))
                .toList();
        if (ordered.isEmpty()) {
            return new Allocation<>(List.of(), List.of(), List.of());
        }

        long windowMillis = config.windowSeconds() * 1_000L;
        Map<Long, List<FrameSignal<T>>> byWindow = new LinkedHashMap<>();
        for (FrameSignal<T> signal : ordered.stream().sorted(Comparator.comparingLong(FrameSignal::timestampMillis)).toList()) {
            byWindow.computeIfAbsent(signal.timestampMillis() / windowMillis, ignored -> new ArrayList<>()).add(signal);
        }

        List<FrameSignal<T>> visualOnly = new ArrayList<>();
        Map<Long, List<FrameSignal<T>>> ocrByWindow = new LinkedHashMap<>();
        for (Map.Entry<Long, List<FrameSignal<T>>> entry : byWindow.entrySet()) {
            List<FrameSignal<T>> values = new ArrayList<>(entry.getValue());
            values.sort(priority());
            values.stream().filter(FrameSignal::visualOnlyEligible).findFirst().ifPresent(visualOnly::add);
            Set<FrameSignal<T>> visualSet = new LinkedHashSet<>(visualOnly);
            List<FrameSignal<T>> remaining = values.stream().filter(value -> !visualSet.contains(value)).toList();
            if (!remaining.isEmpty()) {
                ocrByWindow.put(entry.getKey(), remaining);
            }
        }

        Map<Long, Integer> limits = new LinkedHashMap<>();
        for (Map.Entry<Long, List<FrameSignal<T>>> entry : ocrByWindow.entrySet()) {
            List<FrameSignal<T>> values = entry.getValue();
            long contentChanges = values.stream().filter(this::isContentChange).count();
            boolean lowInformation = values.stream().allMatch(this::isLowInformation);
            int limit = lowInformation
                ? config.lowInformationMaxFramesPerWindow()
                : contentChanges >= 2
                    ? config.contentChangeMaxFramesPerWindow()
                    : config.normalMaxFramesPerWindow();
            limits.put(entry.getKey(), Math.min(limit, values.size()));
        }

        List<FrameSignal<T>> selected = new ArrayList<>();
        int round = 0;
        while (selected.size() < config.maxFramesTotal()) {
            int currentRound = round;
            List<Map.Entry<Long, List<FrameSignal<T>>>> eligible = ocrByWindow.entrySet().stream()
                .filter(entry -> currentRound < limits.get(entry.getKey()))
                .filter(entry -> currentRound < entry.getValue().size())
                .sorted(Map.Entry.comparingByKey())
                .toList();
            if (eligible.isEmpty()) {
                break;
            }
            int slots = Math.min(config.maxFramesTotal() - selected.size(), eligible.size());
            if (round == 0) {
                for (int position : evenlySpacedPositions(eligible.size(), slots)) {
                    selected.add(eligible.get(position).getValue().get(round));
                }
            } else {
                List<Map.Entry<Long, List<FrameSignal<T>>>> dense = eligible.stream()
                    .filter(entry -> denseRank(entry.getValue()) > 0).toList();
                int denseSlots = Math.min(slots, dense.size());
                for (int position : evenlySpacedPositions(dense.size(), denseSlots)) {
                    selected.add(dense.get(position).getValue().get(round));
                }
                int normalSlots = slots - denseSlots;
                List<Map.Entry<Long, List<FrameSignal<T>>>> normal = eligible.stream()
                    .filter(entry -> denseRank(entry.getValue()) == 0).toList();
                for (int position : evenlySpacedPositions(normal.size(), normalSlots)) {
                    selected.add(normal.get(position).getValue().get(round));
                }
            }
            round++;
        }

        Set<FrameSignal<T>> retained = new LinkedHashSet<>(selected);
        retained.addAll(visualOnly);
        List<T> rejected = ordered.stream().filter(value -> !retained.contains(value)).map(FrameSignal::payload).toList();
        return new Allocation<>(
            selected.stream().sorted(Comparator.comparingLong(FrameSignal::timestampMillis)).map(FrameSignal::payload).toList(),
            visualOnly.stream().sorted(Comparator.comparingLong(FrameSignal::timestampMillis)).map(FrameSignal::payload).toList(),
            rejected
        );
    }

    private <T> Comparator<FrameSignal<T>> priority() {
        return Comparator
            .comparingInt((FrameSignal<T> value) -> sourceRank(value)).reversed()
            .thenComparing(Comparator.comparingDouble(FrameSignal<T>::sourceScore).reversed())
            .thenComparing(Comparator.comparingDouble(FrameSignal<T>::qualityScore).reversed())
            .thenComparingLong(FrameSignal::timestampMillis);
    }

    private <T> int sourceRank(FrameSignal<T> value) {
        return switch (value.source()) {
            case CONTENT_CHANGE -> 6;
            case SCENE_CHANGE -> 5;
            case START, END -> 4;
            case PERIODIC_ANCHOR -> 3;
            case WINDOW_COVERAGE -> 2;
        };
    }

    private <T> boolean isContentChange(FrameSignal<T> value) {
        return value.source() == SceneCandidate.Source.CONTENT_CHANGE;
    }

    private <T> boolean isLowInformation(FrameSignal<T> value) {
        return value.source() == SceneCandidate.Source.PERIODIC_ANCHOR
            || value.source() == SceneCandidate.Source.WINDOW_COVERAGE
            ? value.edgeDensity() < 0.012d && value.sourceScore() < 0.20d
            : value.edgeDensity() < 0.004d;
    }

    private <T> int denseRank(List<FrameSignal<T>> values) {
        return values.stream().anyMatch(this::isContentChange) ? 1 : 0;
    }

    private static List<Integer> evenlySpacedPositions(int size, int count) {
        if (count <= 0 || size <= 0) {
            return List.of();
        }
        if (count >= size) {
            return java.util.stream.IntStream.range(0, size).boxed().toList();
        }
        if (count == 1) {
            return List.of(size / 2);
        }
        List<Integer> result = new ArrayList<>(count);
        for (int index = 0; index < count; index++) {
            result.add((int) Math.round(index * (size - 1.0d) / (count - 1.0d)));
        }
        return List.copyOf(result);
    }
}
