package com.example.courselingo.vision.adaptive;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** Applies temporal coverage, content representation, and bounded global budgets. */
public final class ContentAdaptiveFrameBudgetAllocator {

    private static final Set<VideoContentType> REPRESENTATIVE_TYPES = EnumSet.of(
        VideoContentType.CODE_OR_TERMINAL,
        VideoContentType.VISUAL_DEMO,
        VideoContentType.SLIDE
    );

    public record Config(
        int windowSeconds,
        int slideFramesPerWindow,
        int codeFramesPerWindow,
        int visualDemoFramesPerWindow,
        int talkingFramesPerWindow,
        int unknownFramesPerWindow,
        int maximumTotal
    ) {

        public Config {
            if (windowSeconds <= 0 || maximumTotal <= 0
                || slideFramesPerWindow <= 0 || codeFramesPerWindow <= 0
                || visualDemoFramesPerWindow <= 0 || talkingFramesPerWindow <= 0
                || unknownFramesPerWindow <= 0) {
                throw new IllegalArgumentException("content frame budgets must be positive");
            }
        }
    }

    public record FrameSignal<T>(
        T value,
        long timestampMillis,
        VideoContentType contentType,
        double priority,
        boolean qualityEligible
    ) {

        public FrameSignal(T value, long timestampMillis, VideoContentType contentType, double priority) {
            this(value, timestampMillis, contentType, priority, true);
        }
    }

    private final Config config;

    public ContentAdaptiveFrameBudgetAllocator(Config config) {
        this.config = config;
    }

    public <T> List<T> select(List<FrameSignal<T>> frames) {
        if (frames == null || frames.isEmpty()) {
            return List.of();
        }
        long windowMillis = config.windowSeconds() * 1_000L;
        List<FrameSignal<T>> eligible = frames.stream()
            .filter(frame -> frame != null && frame.value() != null && frame.qualityEligible())
            .sorted(Comparator.comparingLong(FrameSignal<T>::timestampMillis))
            .toList();
        if (eligible.isEmpty()) {
            return List.of();
        }
        Map<Long, List<FrameSignal<T>>> windows = new LinkedHashMap<>();
        eligible.stream()
            .forEach(frame -> windows.computeIfAbsent(
                Math.max(0L, frame.timestampMillis()) / windowMillis,
                ignored -> new ArrayList<>()
            ).add(frame));
        Map<Long, Integer> budgets = new LinkedHashMap<>();
        windows.forEach((window, values) -> budgets.put(window, budget(dominantType(values))));
        Map<Long, List<FrameSignal<T>>> rankedWindows = new LinkedHashMap<>();
        windows.forEach((window, values) -> rankedWindows.put(
            window,
            selectWithinWindow(window, values, budgets.get(window), windowMillis)
        ));
        List<FrameSignal<T>> selected = selectWindowCoverage(rankedWindows, config.maximumTotal());
        ensureContentRepresentatives(selected, eligible, budgets, windowMillis, config.maximumTotal());

        int round = 0;
        while (selected.size() < config.maximumTotal()) {
            boolean found = false;
            for (Map.Entry<Long, List<FrameSignal<T>>> entry : rankedWindows.entrySet()) {
                int budget = budgets.get(entry.getKey());
                if (selectedCountInWindow(selected, entry.getKey(), windowMillis) >= budget) {
                    continue;
                }
                FrameSignal<T> candidate = nextUnselected(entry.getValue(), selected, round);
                if (candidate != null) {
                    selected.add(candidate);
                    found = true;
                    if (selected.size() == config.maximumTotal()) {
                        break;
                    }
                }
            }
            if (!found) {
                break;
            }
            round++;
        }
        ensureContentRepresentatives(selected, eligible, budgets, windowMillis, config.maximumTotal());
        return selected.stream()
            .sorted(Comparator.comparingLong(FrameSignal<T>::timestampMillis))
            .map(FrameSignal::value)
            .toList();
    }

    private static <T> List<FrameSignal<T>> selectWindowCoverage(
        Map<Long, List<FrameSignal<T>>> windows,
        int maximum
    ) {
        List<Long> populated = windows.entrySet().stream()
            .filter(entry -> !entry.getValue().isEmpty())
            .map(Map.Entry::getKey)
            .toList();
        if (populated.isEmpty() || maximum <= 0) {
            return new ArrayList<>();
        }
        List<Long> covered = evenlySpread(populated, Math.min(maximum, populated.size()));
        List<FrameSignal<T>> selected = new ArrayList<>(covered.size());
        for (Long window : covered) {
            selected.add(windows.get(window).get(0));
        }
        return selected;
    }

    private static <T> void ensureContentRepresentatives(
        List<FrameSignal<T>> selected,
        List<FrameSignal<T>> eligible,
        Map<Long, Integer> budgets,
        long windowMillis,
        int maximum
    ) {
        Comparator<FrameSignal<T>> priority = priorityComparator();
        List<VideoContentType> presentTypes = REPRESENTATIVE_TYPES.stream()
            .filter(type -> eligible.stream().anyMatch(frame -> safeType(frame) == type))
            .sorted(Comparator.comparingInt(ContentAdaptiveFrameBudgetAllocator::importance))
            .toList();
        for (VideoContentType type : presentTypes) {
            if (containsType(selected, type)) {
                continue;
            }
            FrameSignal<T> representative = eligible.stream()
                .filter(frame -> safeType(frame) == type && !selected.contains(frame))
                .min(priority)
                .orElse(null);
            if (representative == null) {
                continue;
            }
            long targetWindow = windowOf(representative, windowMillis);
            int targetCount = selectedCountInWindow(selected, targetWindow, windowMillis);
            int targetBudget = budgets.getOrDefault(targetWindow, 1);
            if (selected.size() < maximum && targetCount < targetBudget) {
                selected.add(representative);
                continue;
            }
            FrameSignal<T> replacement = replacementCandidate(
                selected,
                representative,
                targetCount >= targetBudget,
                windowMillis
            );
            if (replacement != null) {
                selected.remove(replacement);
                selected.add(representative);
            }
        }
    }

    private static <T> FrameSignal<T> replacementCandidate(
        List<FrameSignal<T>> selected,
        FrameSignal<T> representative,
        boolean targetWindowFull,
        long windowMillis
    ) {
        long targetWindow = windowOf(representative, windowMillis);
        Map<VideoContentType, Long> typeCounts = new HashMap<>();
        Map<Long, Long> windowCounts = new HashMap<>();
        selected.forEach(frame -> {
            typeCounts.merge(safeType(frame), 1L, Long::sum);
            windowCounts.merge(windowOf(frame, windowMillis), 1L, Long::sum);
        });
        return selected.stream()
            .filter(frame -> !targetWindowFull || windowOf(frame, windowMillis) == targetWindow)
            .filter(frame -> !REPRESENTATIVE_TYPES.contains(safeType(frame))
                || typeCounts.getOrDefault(safeType(frame), 0L) > 1L)
            .filter(frame -> windowOf(frame, windowMillis) == targetWindow
                || windowCounts.getOrDefault(windowOf(frame, windowMillis), 0L) > 1L)
            .min(Comparator.comparingDouble(FrameSignal<T>::priority)
                .thenComparingLong(FrameSignal<T>::timestampMillis))
            .orElse(null);
    }

    private static <T> FrameSignal<T> nextUnselected(
        List<FrameSignal<T>> candidates,
        List<FrameSignal<T>> selected,
        int preferredIndex
    ) {
        if (preferredIndex < candidates.size() && !selected.contains(candidates.get(preferredIndex))) {
            return candidates.get(preferredIndex);
        }
        return candidates.stream().filter(candidate -> !selected.contains(candidate)).findFirst().orElse(null);
    }

    private <T> List<FrameSignal<T>> selectWithinWindow(
        long windowIndex,
        List<FrameSignal<T>> values,
        int budget,
        long windowMillis
    ) {
        Comparator<FrameSignal<T>> priority = priorityComparator();
        if (values.size() <= budget) {
            return values.stream().sorted(priority).toList();
        }
        long startMillis = windowIndex * windowMillis;
        double bucketWidth = windowMillis / (double) budget;
        Map<Integer, List<FrameSignal<T>>> buckets = new LinkedHashMap<>();
        for (FrameSignal<T> value : values) {
            int bucket = Math.min(budget - 1, Math.max(0,
                (int) Math.floor((Math.max(0L, value.timestampMillis()) - startMillis) / bucketWidth)));
            buckets.computeIfAbsent(bucket, ignored -> new ArrayList<>()).add(value);
        }
        List<FrameSignal<T>> selected = new ArrayList<>();
        buckets.values().stream()
            .map(bucket -> bucket.stream().min(priority).orElseThrow())
            .forEach(selected::add);
        ensureWindowRepresentatives(selected, values, budget, priority);
        if (selected.size() < budget) {
            values.stream()
                .filter(value -> !selected.contains(value))
                .sorted(priority)
                .limit(budget - selected.size())
                .forEach(selected::add);
        }
        return selected.stream().sorted(priority).toList();
    }

    private static <T> void ensureWindowRepresentatives(
        List<FrameSignal<T>> selected,
        List<FrameSignal<T>> values,
        int budget,
        Comparator<FrameSignal<T>> priority
    ) {
        List<VideoContentType> presentTypes = REPRESENTATIVE_TYPES.stream()
            .filter(type -> values.stream().anyMatch(frame -> safeType(frame) == type))
            .sorted(Comparator.comparingInt(ContentAdaptiveFrameBudgetAllocator::importance))
            .toList();
        for (VideoContentType type : presentTypes) {
            if (containsType(selected, type)) {
                continue;
            }
            FrameSignal<T> representative = values.stream()
                .filter(frame -> safeType(frame) == type)
                .min(priority)
                .orElse(null);
            if (representative == null) {
                continue;
            }
            if (selected.size() < budget) {
                selected.add(representative);
                continue;
            }
            Map<VideoContentType, Long> counts = new HashMap<>();
            selected.forEach(frame -> counts.merge(safeType(frame), 1L, Long::sum));
            FrameSignal<T> replacement = selected.stream()
                .filter(frame -> !REPRESENTATIVE_TYPES.contains(safeType(frame))
                    || counts.getOrDefault(safeType(frame), 0L) > 1L)
                .min(Comparator.comparingDouble(FrameSignal<T>::priority)
                    .thenComparingLong(FrameSignal<T>::timestampMillis))
                .orElse(null);
            if (replacement != null) {
                selected.remove(replacement);
                selected.add(representative);
            }
        }
    }

    private static <T> Comparator<FrameSignal<T>> priorityComparator() {
        return Comparator.comparingDouble(FrameSignal<T>::priority).reversed()
            .thenComparingLong(FrameSignal<T>::timestampMillis);
    }

    private static <T> boolean containsType(List<FrameSignal<T>> frames, VideoContentType type) {
        return frames.stream().anyMatch(frame -> safeType(frame) == type);
    }

    private static <T> int selectedCountInWindow(
        List<FrameSignal<T>> frames,
        long window,
        long windowMillis
    ) {
        return (int) frames.stream().filter(frame -> windowOf(frame, windowMillis) == window).count();
    }

    private static <T> long windowOf(FrameSignal<T> frame, long windowMillis) {
        return Math.max(0L, frame.timestampMillis()) / windowMillis;
    }

    private static <T> VideoContentType safeType(FrameSignal<T> frame) {
        return frame.contentType() == null ? VideoContentType.UNKNOWN : frame.contentType();
    }

    private static <T> List<T> evenlySpread(List<T> values, int maximum) {
        if (maximum <= 0 || values.isEmpty()) {
            return List.of();
        }
        if (values.size() <= maximum) {
            return List.copyOf(values);
        }
        if (maximum == 1) {
            return List.of(values.get(values.size() / 2));
        }
        List<T> result = new ArrayList<>(maximum);
        Set<Integer> used = new HashSet<>();
        for (int index = 0; index < maximum; index++) {
            int position = (int) Math.round(index * (values.size() - 1.0d) / (maximum - 1.0d));
            if (used.add(position)) {
                result.add(values.get(position));
            }
        }
        return result;
    }

    private <T> VideoContentType dominantType(List<FrameSignal<T>> values) {
        return values.stream()
            .map(FrameSignal::contentType)
            .min(Comparator.comparingInt(ContentAdaptiveFrameBudgetAllocator::importance))
            .orElse(VideoContentType.UNKNOWN);
    }

    private int budget(VideoContentType type) {
        return switch (type == null ? VideoContentType.UNKNOWN : type) {
            case SLIDE -> config.slideFramesPerWindow();
            case CODE_OR_TERMINAL -> config.codeFramesPerWindow();
            case VISUAL_DEMO -> config.visualDemoFramesPerWindow();
            case TALKING_OR_LOW_INFORMATION -> config.talkingFramesPerWindow();
            case UNKNOWN -> config.unknownFramesPerWindow();
        };
    }

    private static int importance(VideoContentType type) {
        return switch (type == null ? VideoContentType.UNKNOWN : type) {
            case CODE_OR_TERMINAL -> 0;
            case VISUAL_DEMO -> 1;
            case SLIDE -> 2;
            case UNKNOWN -> 3;
            case TALKING_OR_LOW_INFORMATION -> 4;
        };
    }
}
