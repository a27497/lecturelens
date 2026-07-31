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
}
