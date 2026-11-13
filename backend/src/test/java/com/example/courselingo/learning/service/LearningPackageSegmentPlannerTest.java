package com.example.courselingo.learning.service;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.subtitle.domain.SubtitleTranslationSegment;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class LearningPackageSegmentPlannerTest {

    @Test
    void groupsCuesIntoDefault240SecondChaptersWithoutSplittingACue() {
        List<SubtitleSegment> sources = cues(
            0, 0, 60_000,
            1, 60_000, 120_000,
            2, 180_000, 250_000, // starts inside the first 240s window, even though it ends after
            3, 240_000, 300_000,
            4, 480_000, 510_000
        );
        List<SubtitleTranslationSegment> translations = translations(sources);

        var chapters = LearningPackageSegmentPlanner.plan(sources, translations, new LearningPackageProperties());

        assertThat(chapters).hasSize(3);
        assertThat(chapters.get(0).sources()).extracting(SubtitleSegment::getSegmentIndex).containsExactly(0, 1, 2);
        assertThat(chapters.get(0).startMillis()).isEqualTo(0L);
        assertThat(chapters.get(0).endMillis()).isEqualTo(250_000L);
        assertThat(chapters.get(1).sources()).extracting(SubtitleSegment::getSegmentIndex).containsExactly(3);
        assertThat(chapters.get(2).sources()).extracting(SubtitleSegment::getSegmentIndex).containsExactly(4);
        assertThat(chapters.get(0).translations()).extracting(SubtitleTranslationSegment::getSegmentIndex)
            .containsExactly(0, 1, 2);
    }

    @Test
    void emptyOrNullSourcesYieldNoChapters() {
        assertThat(LearningPackageSegmentPlanner.plan(null, List.of(), new LearningPackageProperties())).isEmpty();
        assertThat(LearningPackageSegmentPlanner.plan(List.of(), List.of(), new LearningPackageProperties())).isEmpty();
    }

    @Test
    void honorsAConfiguredWindow() {
        LearningPackageProperties properties = new LearningPackageProperties();
        properties.setSegmentWindowSeconds(60);
        List<SubtitleSegment> sources = cues(0, 0, 30_000, 1, 60_000, 90_000);

        var chapters = LearningPackageSegmentPlanner.plan(sources, List.of(), properties);

        assertThat(chapters).hasSize(2);
        assertThat(LearningPackageSegmentPlanner.windowMillis(properties)).isEqualTo(60_000);
    }

    private static List<SubtitleSegment> cues(int... values) {
        List<SubtitleSegment> sources = new ArrayList<>();
        for (int i = 0; i < values.length; i += 3) {
            SubtitleSegment segment = new SubtitleSegment();
            segment.setSegmentIndex(values[i]);
            segment.setStartMillis((long) values[i + 1]);
            segment.setEndMillis((long) values[i + 2]);
            segment.setText("cue " + values[i]);
            sources.add(segment);
        }
        return sources;
    }

    private static List<SubtitleTranslationSegment> translations(List<SubtitleSegment> sources) {
        List<SubtitleTranslationSegment> translations = new ArrayList<>();
        for (SubtitleSegment source : sources) {
            SubtitleTranslationSegment translation = new SubtitleTranslationSegment();
            translation.setSegmentIndex(source.getSegmentIndex());
            translation.setStartMillis(source.getStartMillis());
            translation.setEndMillis(source.getEndMillis());
            translation.setTranslatedText("译文 " + source.getSegmentIndex());
            translations.add(translation);
        }
        return translations;
    }
}
