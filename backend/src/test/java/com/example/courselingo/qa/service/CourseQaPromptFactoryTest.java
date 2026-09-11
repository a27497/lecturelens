package com.example.courselingo.qa.service;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.courselingo.qa.dto.CourseQaEvidenceItem;
import java.util.List;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

class CourseQaPromptFactoryTest {

    @Test
    void longSubtitleEvidenceStaysWithinTwelveThousandCharacters() {
        List<CourseQaEvidenceItem> evidence = IntStream.range(0, 69)
            .mapToObj(index -> new CourseQaEvidenceItem(
                "SUBTITLE", Integer.toString(index), index * 1000L, (index + 1L) * 1000L,
                "00:00:01", "Spring Boot evidence ".repeat(100), "中文证据 ".repeat(100), 0.9d
            ))
            .toList();

        var messages = CourseQaPromptFactory.buildMessages(
            "请解释课程中的 Spring Boot API Gateway", evidence, 12_000
        );

        assertThat(CourseQaPromptFactory.promptChars(messages)).isLessThanOrEqualTo(12_000);
        assertThat(messages.getLast().content()).contains("Question:", "Return JSON only.");
    }

    @Test
    void citationIndexesAndSnippetsAreBoundedByActualVisibleEvidence() {
        var items = IntStream.range(0, 30).mapToObj(i -> new CourseQaEvidenceItem("SUBTITLE", "" + i,
            0L, 1000L, "00:00:00", "Evidence content ".repeat(20), null, 0.9d, "id" + i, 1L)).toList();
        var prepared = CourseQaPromptFactory.prepare("Question", items, 1500, 100);
        assertThat(prepared.evidence()).isNotEmpty().hasSizeLessThan(items.size());
        assertThat(prepared.evidence()).allSatisfy(item -> {
            assertThat(item.snippet()).hasSize(100);
            assertThat(prepared.messages().getLast().content()).contains(item.snippet());
            assertThat(item.evidenceId()).startsWith("id");
        });
        int excluded = prepared.evidence().size();
        var parsed = new CourseQaResponseParser().parse(
            "{\"answer\":\"answer\",\"citedEvidenceIndexes\":[0," + excluded + "]}", excluded);
        assertThat(parsed.citedEvidenceIndexes()).containsExactly(0);
        assertThat(CourseQaPromptFactory.promptChars(prepared.messages())).isLessThanOrEqualTo(1500);
    }
}
