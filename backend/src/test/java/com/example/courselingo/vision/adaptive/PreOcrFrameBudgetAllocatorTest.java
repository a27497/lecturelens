package com.example.courselingo.vision.adaptive;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

class PreOcrFrameBudgetAllocatorTest {

    @Test
    void smallGlobalBudgetIsEvenlyDistributedAcrossTheTimeline() {
        PreOcrFrameBudgetAllocator allocator = allocator(3);
        List<PreOcrFrameBudgetAllocator.FrameSignal<Long>> signals = IntStream.range(0, 10)
            .mapToObj(window -> signal(window * 60_000L, SceneCandidate.Source.PERIODIC_ANCHOR, 0.3d, 0.03d))
            .toList();

        PreOcrFrameBudgetAllocator.Allocation<Long> result = allocator.allocate(signals);

        assertThat(result.ocrFrames()).containsExactly(0L, 300_000L, 540_000L);
        assertThat(result.rejectedFrames()).hasSize(7);
    }

    @Test
    void allocationIsDeterministicAndPrioritizesDetectedContentChanges() {
        PreOcrFrameBudgetAllocator allocator = allocator(2);
        List<PreOcrFrameBudgetAllocator.FrameSignal<Long>> chronological = List.of(
            signal(0L, SceneCandidate.Source.PERIODIC_ANCHOR, 0.9d, 0.03d),
            signal(10_000L, SceneCandidate.Source.CONTENT_CHANGE, 0.3d, 0.03d),
            signal(20_000L, SceneCandidate.Source.CONTENT_CHANGE, 0.2d, 0.03d),
            signal(30_000L, SceneCandidate.Source.WINDOW_COVERAGE, 0.8d, 0.03d)
        );
        List<PreOcrFrameBudgetAllocator.FrameSignal<Long>> reversed = List.of(
            chronological.get(3), chronological.get(2), chronological.get(1), chronological.get(0)
        );

        PreOcrFrameBudgetAllocator.Allocation<Long> first = allocator.allocate(chronological);
        PreOcrFrameBudgetAllocator.Allocation<Long> second = allocator.allocate(reversed);

        assertThat(first.ocrFrames()).containsExactly(10_000L, 20_000L);
        assertThat(second).isEqualTo(first);
    }

    @Test
    void threeHourPlanKeepsEveryWindowWithinDefaultTotalBudget() {
        PreOcrFrameBudgetAllocator allocator = allocator(360);
        List<PreOcrFrameBudgetAllocator.FrameSignal<Long>> signals = new ArrayList<>();
        for (int window = 0; window < 180; window++) {
            for (int candidate = 0; candidate < 6; candidate++) {
                long timestamp = window * 60_000L + candidate * 9_000L;
                signals.add(signal(timestamp, SceneCandidate.Source.PERIODIC_ANCHOR, 0.1d, 0.03d));
            }
        }

        PreOcrFrameBudgetAllocator.Allocation<Long> result = allocator.allocate(signals);
        Map<Long, Long> byWindow = result.ocrFrames().stream()
            .collect(Collectors.groupingBy(value -> value / 60_000L, Collectors.counting()));

        assertThat(result.ocrFrames()).hasSize(360);
        assertThat(byWindow).hasSize(180);
        assertThat(byWindow.values()).allMatch(count -> count == 2L);
        assertThat(byWindow).containsKeys(0L, 179L);
    }

    @Test
    void denseContentChangeWindowReceivesFourSlotsBeforeNormalWindowsReceiveExtras() {
        PreOcrFrameBudgetAllocator allocator = allocator(12);
        List<PreOcrFrameBudgetAllocator.FrameSignal<Long>> signals = new ArrayList<>();
        for (int window = 0; window < 5; window++) {
            for (int candidate = 0; candidate < 6; candidate++) {
                SceneCandidate.Source source = window == 2
                    ? SceneCandidate.Source.CONTENT_CHANGE
                    : SceneCandidate.Source.PERIODIC_ANCHOR;
                long timestamp = window * 60_000L + candidate * 8_000L;
                signals.add(signal(timestamp, source, 0.25d, 0.04d));
            }
        }

        PreOcrFrameBudgetAllocator.Allocation<Long> result = allocator.allocate(signals);
        Map<Long, Long> byWindow = result.ocrFrames().stream()
            .collect(Collectors.groupingBy(value -> value / 60_000L, Collectors.counting()));

        assertThat(byWindow.get(2L)).isEqualTo(4L);
        assertThat(byWindow.entrySet().stream().filter(entry -> entry.getKey() != 2L))
            .allMatch(entry -> entry.getValue() == 2L);
    }

    @Test
    void lowInformationWindowIsCappedAndVisualOnlyFrameBypassesOcr() {
        PreOcrFrameBudgetAllocator allocator = allocator(20);
        List<PreOcrFrameBudgetAllocator.FrameSignal<Long>> signals = IntStream.range(0, 5)
            .mapToObj(index -> new PreOcrFrameBudgetAllocator.FrameSignal<>(
                (long) index * 5_000L,
                (long) index * 5_000L,
                index == 4 ? SceneCandidate.Source.SCENE_CHANGE : SceneCandidate.Source.WINDOW_COVERAGE,
                index == 4 ? 0.8d : 0.1d,
                index == 4 ? 0.12d : 0.001d,
                50.0d,
                index == 4
            )).toList();

        PreOcrFrameBudgetAllocator.Allocation<Long> result = allocator.allocate(signals);

        assertThat(result.visualOnlyFrames()).containsExactly(20_000L);
        assertThat(result.ocrFrames()).hasSize(1);
        assertThat(result.rejectedFrames()).hasSize(3);
    }

    private static PreOcrFrameBudgetAllocator allocator(int total) {
        return new PreOcrFrameBudgetAllocator(new PreOcrFrameBudgetAllocator.Config(60, 2, 4, 1, total));
    }

    private static PreOcrFrameBudgetAllocator.FrameSignal<Long> signal(
        long timestamp,
        SceneCandidate.Source source,
        double score,
        double edgeDensity
    ) {
        return new PreOcrFrameBudgetAllocator.FrameSignal<>(
            timestamp,
            timestamp,
            source,
            score,
            edgeDensity,
            60.0d,
            false
        );
    }
}
