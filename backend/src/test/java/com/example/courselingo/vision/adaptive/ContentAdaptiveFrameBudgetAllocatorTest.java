package com.example.courselingo.vision.adaptive;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

class ContentAdaptiveFrameBudgetAllocatorTest {

    private final VideoContentClassifier classifier = new VideoContentClassifier();
    private final ContentAdaptiveFrameBudgetAllocator allocator = new ContentAdaptiveFrameBudgetAllocator(
        new ContentAdaptiveFrameBudgetAllocator.Config(60, 2, 4, 3, 1, 2, 20)
    );

    @Test
    void multipleCodeUpdatesWithinOneMinuteReceiveFourFrameBudget() {
        List<Integer> selected = allocator.select(signals(5, VideoContentType.CODE_OR_TERMINAL));

        assertThat(selected).hasSize(4);
    }

    @Test
    void terminalErrorToSuccessIsARealCodeChange() {
        String error = "PS> mvn test\nBUILD FAILED\njava.lang.AssertionError";
        String success = "PS> mvn test\nBUILD SUCCESS\nTests run: 1120";

        assertThat(classifier.classify(error, 0.08d, 0.2d, null))
            .isEqualTo(VideoContentType.CODE_OR_TERMINAL);
        assertThat(classifier.classify(success, 0.08d, 0.2d, null))
            .isEqualTo(VideoContentType.CODE_OR_TERMINAL);
        assertThat(VideoContentClassifier.textChangeRatio(error, success)).isGreaterThan(0.06d);
    }

    @Test
    void staticSlideUsesTwoFrameBudget() {
        assertThat(allocator.select(signals(5, VideoContentType.SLIDE))).hasSize(2);
    }

    @Test
    void talkingHeadLowInformationUsesOneFrameBudget() {
        assertThat(allocator.select(signals(5, VideoContentType.TALKING_OR_LOW_INFORMATION))).hasSize(1);
    }

    @Test
    void scrollingAcrossDifferentCodeRegionsRetainsChronologicalCoverage() {
        List<Integer> selected = allocator.select(signals(6, VideoContentType.CODE_OR_TERMINAL));

        assertThat(selected).containsExactly(0, 1, 2, 4);
    }

    @Test
    void retainsTextFreeVisualDemoRepresentativeAlongsideSlideAndCode() {
        List<String> selected = allocator.select(List.of(
            signal("slide", 2_000L, VideoContentType.SLIDE, 95.0d),
            signal("code-1", 12_000L, VideoContentType.CODE_OR_TERMINAL, 100.0d),
            signal("code-2", 25_000L, VideoContentType.CODE_OR_TERMINAL, 98.0d),
            signal("diagram-without-ocr", 38_000L, VideoContentType.VISUAL_DEMO, 50.0d),
            signal("terminal", 52_000L, VideoContentType.CODE_OR_TERMINAL, 96.0d)
        ));

        assertThat(selected).contains("slide", "code-1", "diagram-without-ocr");
        assertThat(selected).hasSize(4);
    }

    @Test
    void qualityRejectedVisualCandidateCannotReenterThroughRepresentativeRetention() {
        List<String> selected = allocator.select(List.of(
            signal("slide", 2_000L, VideoContentType.SLIDE, 50.0d),
            new ContentAdaptiveFrameBudgetAllocator.FrameSignal<>(
                "black-diagram", 30_000L, VideoContentType.VISUAL_DEMO, 10_000.0d, false
            )
        ));

        assertThat(selected).containsExactly("slide");
    }

    @Test
    void insufficientBudgetKeepsTimelineCoverageAndHighestValueTypes() {
        ContentAdaptiveFrameBudgetAllocator constrained = new ContentAdaptiveFrameBudgetAllocator(
            new ContentAdaptiveFrameBudgetAllocator.Config(60, 2, 4, 3, 1, 2, 2)
        );

        List<String> selected = constrained.select(List.of(
            signal("code", 5_000L, VideoContentType.CODE_OR_TERMINAL, 100.0d),
            signal("visual", 25_000L, VideoContentType.VISUAL_DEMO, 90.0d),
            signal("slide", 48_000L, VideoContentType.SLIDE, 80.0d)
        ));

        assertThat(selected).containsExactly("code", "visual");
    }

    @Test
    void threeHourTimelineDoesNotExhaustGlobalBudgetInFirstHalf() {
        ContentAdaptiveFrameBudgetAllocator constrained = new ContentAdaptiveFrameBudgetAllocator(
            new ContentAdaptiveFrameBudgetAllocator.Config(60, 2, 4, 3, 1, 2, 12)
        );
        List<ContentAdaptiveFrameBudgetAllocator.FrameSignal<Integer>> threeHours = IntStream.range(0, 180)
            .mapToObj(minute -> signal(
                minute,
                minute * 60_000L,
                VideoContentType.SLIDE,
                100.0d - minute / 10.0d
            ))
            .toList();

        List<Integer> selected = constrained.select(threeHours);

        assertThat(selected).hasSize(12);
        assertThat(selected.getFirst()).isEqualTo(0);
        assertThat(selected.getLast()).isEqualTo(179);
        assertThat(selected).anyMatch(minute -> minute >= 90 && minute < 150);
    }

    private static List<ContentAdaptiveFrameBudgetAllocator.FrameSignal<Integer>> signals(
        int count,
        VideoContentType type
    ) {
        return IntStream.range(0, count)
            .mapToObj(index -> new ContentAdaptiveFrameBudgetAllocator.FrameSignal<>(
                index,
                index * 8_000L,
                type,
                100.0d - index
            ))
            .toList();
    }

    private static <T> ContentAdaptiveFrameBudgetAllocator.FrameSignal<T> signal(
        T value,
        long timestampMillis,
        VideoContentType type,
        double priority
    ) {
        return new ContentAdaptiveFrameBudgetAllocator.FrameSignal<>(value, timestampMillis, type, priority);
    }
}
