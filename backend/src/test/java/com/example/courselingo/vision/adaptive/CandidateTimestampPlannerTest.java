package com.example.courselingo.vision.adaptive;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

class CandidateTimestampPlannerTest {

    private final CandidateTimestampPlanner planner = new CandidateTimestampPlanner();

    @Test
    void choosesThirtyFortyFiveAndSixtySecondAnchorsFromRealDuration() {
        assertThat(planner.anchorIntervalSeconds(3_600)).isEqualTo(30.0);
        assertThat(planner.anchorIntervalSeconds(3_600.01)).isEqualTo(45.0);
        assertThat(planner.anchorIntervalSeconds(7_200)).isEqualTo(45.0);
        assertThat(planner.anchorIntervalSeconds(7_200.01)).isEqualTo(60.0);
    }

    @Test
    void coversEveryWindowAndTheEndOfAThreeHourLecture() {
        double duration = 3 * 60 * 60;

        List<SceneCandidate> candidates = planner.plan(duration, List.<SceneCandidate>of());

        assertThat(candidates.getFirst().timestampSeconds()).isZero();
        assertThat(candidates.getLast().timestampSeconds()).isEqualTo(duration);
        assertThat(candidates.getLast().source()).isEqualTo(SceneCandidate.Source.END);
        Map<Integer, Long> counts = candidates.stream().collect(Collectors.groupingBy(
            candidate -> Math.min(179, (int) (candidate.timestampSeconds() / 60.0)),
            Collectors.counting()
        ));
        assertThat(counts).hasSize(180);
        assertThat(counts.values()).allSatisfy(count -> assertThat(count).isBetween(1L, 6L));
        assertThat(candidates).anySatisfy(candidate ->
            assertThat(candidate.timestampSeconds()).isGreaterThan(10_700.0));
    }

    @Test
    void denseEarlySceneChangesCannotConsumeLaterWindowCoverage() {
        List<SceneCandidate> dense = new ArrayList<>();
        for (double second = 1.0; second < 55.0; second += 2.0) {
            dense.add(SceneCandidate.sceneChange(second, second / 60.0));
        }

        List<SceneCandidate> candidates = planner.plan(600.0, dense);

        for (int window = 0; window < 10; window++) {
            int expectedWindow = window;
            assertThat(candidates).anyMatch(candidate -> window(candidate.timestampSeconds(), 10) == expectedWindow);
            assertThat(candidates.stream().filter(candidate -> window(candidate.timestampSeconds(), 10) == expectedWindow))
                .hasSizeLessThanOrEqualTo(6);
        }
    }

    @Test
    void mergesNearbyPointsWhileGivingSceneChangesPriorityOverFallbackAnchors() {
        CandidateTimestampPlanner custom = new CandidateTimestampPlanner(new CandidateTimestampPlanner.Config(
            60, 3, 2, 3_600, 7_200, 30, 45, 60));

        List<SceneCandidate> candidates = custom.plan(121.0, List.of(
            SceneCandidate.sceneChange(29.5, 0.9),
            SceneCandidate.sceneChange(30.4, 0.5),
            SceneCandidate.sceneChange(31.0, 0.8)
        ));

        assertThat(candidates.stream().filter(candidate -> candidate.timestampSeconds() > 28
            && candidate.timestampSeconds() < 32)).singleElement().satisfies(candidate -> {
                assertThat(candidate.source()).isEqualTo(SceneCandidate.Source.SCENE_CHANGE);
                assertThat(candidate.timestampSeconds()).isEqualTo(29.5);
                assertThat(candidate.score()).isEqualTo(0.9);
            });
    }

    @Test
    void preservesSubtleContentChangesAndSpreadsDenseCandidatesAcrossTheWindow() {
        CandidateTimestampPlanner custom = new CandidateTimestampPlanner(new CandidateTimestampPlanner.Config(
            60, 3, 0.1, 3_600, 7_200, 30, 45, 60));
        List<SceneCandidate> dense = List.of(
            SceneCandidate.contentChange(2.0, 0.08),
            SceneCandidate.contentChange(4.0, 0.09),
            SceneCandidate.contentChange(22.0, 0.04),
            SceneCandidate.contentChange(35.0, 0.05),
            SceneCandidate.contentChange(48.0, 0.03),
            SceneCandidate.contentChange(56.0, 0.02)
        );

        List<SceneCandidate> firstWindow = custom.plan(61.0, dense).stream()
            .filter(candidate -> candidate.timestampSeconds() < 60.0)
            .toList();

        assertThat(firstWindow).hasSize(3);
        assertThat(firstWindow).anyMatch(candidate -> candidate.source() == SceneCandidate.Source.CONTENT_CHANGE);
        assertThat(firstWindow).anyMatch(candidate -> candidate.timestampSeconds() == 35.0);
        assertThat(firstWindow).anyMatch(candidate -> candidate.timestampSeconds() >= 40.0);
    }

    private static int window(double timestamp, int count) {
        return Math.min(count - 1, (int) (timestamp / 60.0));
    }
}
