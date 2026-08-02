package com.example.courselingo.chapter;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.courselingo.chapter.dto.CourseChapterEvidenceItem;
import com.example.courselingo.chapter.service.CourseChapterPromptFactory;
import java.util.List;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

class CourseChapterPromptFactoryTest {

    @Test
    void compressesLongEvidenceWithoutExceedingConfiguredPromptLimit() {
        List<CourseChapterEvidenceItem> evidence = IntStream.range(0, 24)
            .mapToObj(index -> new CourseChapterEvidenceItem(
                index, index * 240_000L, (index + 1L) * 240_000L, "01:00:00", "evidence ".repeat(1000)
            ))
            .toList();

        var messages = CourseChapterPromptFactory.buildMessages(
            evidence, "global context ".repeat(1000), 20, 12_000
        );

        assertThat(CourseChapterPromptFactory.promptChars(messages)).isLessThanOrEqualTo(12_000);
        assertThat(messages.getLast().content()).contains(
            "Evidence:",
            "start=",
            "end=",
            "every evidence index must be cited",
            "contiguous with no uncovered time gap"
        );
    }

    @Test
    void repairRequestAddsCorrectionWithoutEchoingProviderOutput() {
        var original = CourseChapterPromptFactory.buildMessages(
            List.of(new CourseChapterEvidenceItem(0, 0L, 60_000L, "00:00", "Spring Boot")),
            "",
            5,
            4_000
        );

        var repaired = CourseChapterPromptFactory.buildRepairMessages(original);

        assertThat(repaired).hasSize(original.size() + 1);
        assertThat(repaired.getLast().content())
            .contains("未通过结构校验", "完整 JSON object")
            .doesNotContain("provider response", "raw response");
    }
}
