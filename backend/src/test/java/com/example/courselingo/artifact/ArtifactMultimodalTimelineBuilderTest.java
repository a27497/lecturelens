package com.example.courselingo.artifact;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.courselingo.artifact.service.ArtifactMultimodalTimelineBuilder;
import com.example.courselingo.fusion.VideoSegment;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class ArtifactMultimodalTimelineBuilderTest {

    @Test
    void deduplicatesBeforeApplyingTimelineLimit() {
        List<VideoSegment> segments = new ArrayList<>();
        for (int index = 0; index < 240; index++) {
            segments.add(segment(index, 0L, "repeated evidence"));
        }
        segments.add(segment(240, 1_000L, "later unique evidence"));

        var timeline = new ArtifactMultimodalTimelineBuilder(new ObjectMapper()).build(segments);

        assertThat(timeline).hasSize(2);
        assertThat(timeline).extracting(item -> item.visualSummary())
            .containsExactly("repeated evidence", "later unique evidence");
    }

    @Test
    void rejectsHistoricalOcrNoiseFromDirectAndFusedExportEvidence() {
        VideoSegment segment = segment(0, 0L, "Architecture diagram remains useful");
        segment.setOcrText("Readable prefix \uFFFD fictional corrupted OCR body");
        segment.setFusedSummary(
            "本段主要讲解：microservices；画面文字包括：Readable prefix \uFFFD fictional corrupted OCR body；"
                + "画面显示：Architecture diagram remains useful"
        );

        var timeline = new ArtifactMultimodalTimelineBuilder(new ObjectMapper()).build(List.of(segment));

        assertThat(timeline).singleElement().satisfies(item -> {
            assertThat(item.ocrText()).isEmpty();
            assertThat(item.fusedSummary())
                .contains("microservices", "Architecture diagram remains useful")
                .doesNotContain("corrupted OCR body", "画面文字包括");
        });
    }

    @Test
    void preservesUsefulTechnicalOcrInExportEvidence() {
        VideoSegment segment = segment(0, 0L, "Terminal demo");
        segment.setOcrText("docker compose up -d");
        segment.setFusedSummary("画面文字包括：docker compose up -d；画面显示：Terminal demo");

        var timeline = new ArtifactMultimodalTimelineBuilder(new ObjectMapper()).build(List.of(segment));

        assertThat(timeline).singleElement().satisfies(item -> {
            assertThat(item.ocrText()).isEqualTo("docker compose up -d");
            assertThat(item.fusedSummary()).contains("docker compose up -d");
        });
    }

    private VideoSegment segment(int index, long startMillis, String visualSummary) {
        VideoSegment segment = new VideoSegment();
        segment.setId((long) index + 1L);
        segment.setSegmentIndex(index);
        segment.setStartMillis(startMillis);
        segment.setEndMillis(startMillis + 500L);
        segment.setVisualSummary(visualSummary);
        return segment;
    }
}
