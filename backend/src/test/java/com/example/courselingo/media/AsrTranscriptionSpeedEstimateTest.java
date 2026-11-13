package com.example.courselingo.media;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * Offline, fixture-based wall-clock estimate. No provider is called.
 * Request time is modeled as {@code overhead + duration} or overhead-only,
 * then scheduled onto a fixed number of workers.
 */
class AsrTranscriptionSpeedEstimateTest {
    @TempDir Path directory;

    @Test
    void mergeAndConcurrencyFourShortenModeledWallClockForASilencePlan() {
        var original = SilenceAudioChunkPlanner.partition(
            5_400_000L,
            List.of(),
            directory,
            new SilenceSegmentationPolicy(-35, 600, 15000, 30000, 30000, 256, 16000, 1, 4, 4 * 1024 * 1024),
            4 * 1024 * 1024
        );
        var merged = SilenceAudioChunkPlanner.applyMerge(
            original,
            directory,
            SilenceAudioChunkPlannerTest.policy(),
            new AudioClipMergePolicy(60000, 90000, 120000)
        );
        assertThat(original.chunks()).hasSize(180);
        assertThat(merged.chunks()).hasSize(60);

        long beforeProportional = schedule(durations(original), 2, 5_000L, true);
        long afterProportional = schedule(durations(merged), 4, 5_000L, true);
        long beforeOverhead = schedule(durations(original), 2, 5_000L, false);
        long afterOverhead = schedule(durations(merged), 4, 5_000L, false);

        assertThat(afterProportional)
            .as("proportional model before=%d after=%d", beforeProportional, afterProportional)
            .isLessThan(beforeProportional);
        assertThat(afterOverhead)
            .as("overhead-only model before=%d after=%d", beforeOverhead, afterOverhead)
            .isLessThan(beforeOverhead);
        // 90-minute continuous speech, 5s fixed overhead per request:
        // before (30s clips, concurrency 2) vs after (90s clips, concurrency 4).
        assertThat(beforeProportional).isEqualTo(3_150_000L);
        assertThat(afterProportional).isEqualTo(1_425_000L);
        assertThat(beforeOverhead).isEqualTo(450_000L);
        assertThat(afterOverhead).isEqualTo(75_000L);
    }

    @Test
    void raisingLegacyConcurrencyHalvesModeledBatchesForFixedOneHundredEightySecondChunks() {
        List<Long> chunks = new ArrayList<>();
        for (int i = 0; i < 30; i++) {
            chunks.add(180_000L);
        }
        long before = schedule(chunks, 2, 5_000L, true);
        long after = schedule(chunks, 4, 5_000L, true);
        assertThat(after).as("legacy 180s path before=%d after=%d", before, after).isLessThan(before);
        assertThat(before).isEqualTo(2_775_000L);
        assertThat(after).isEqualTo(1_480_000L);
    }

    private static List<Long> durations(SilenceAudioChunkPlanner.Plan plan) {
        return plan.chunks().stream().map(chunk -> chunk.endMillis() - chunk.offsetMillis()).toList();
    }

    /** Exclusive-processor list scheduling; returns modeled wall-clock milliseconds. */
    private static long schedule(List<Long> clipMillis, int concurrency, long overheadMillis, boolean includeDuration) {
        var workers = new PriorityQueue<Long>();
        for (int i = 0; i < concurrency; i++) {
            workers.add(0L);
        }
        var sorted = new ArrayList<>(clipMillis);
        sorted.sort(Comparator.reverseOrder());
        for (long duration : sorted) {
            long start = workers.remove();
            workers.add(start + overheadMillis + (includeDuration ? duration : 0L));
        }
        return workers.stream().mapToLong(Long::longValue).max().orElse(0L);
    }
}
