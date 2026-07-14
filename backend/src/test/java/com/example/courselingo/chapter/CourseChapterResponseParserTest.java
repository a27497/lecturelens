package com.example.courselingo.chapter;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.courselingo.chapter.dto.CourseChapterEvidenceItem;
import com.example.courselingo.chapter.service.CourseChapterResponseParser;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.util.List;
import org.junit.jupiter.api.Test;

class CourseChapterResponseParserTest {

    private final CourseChapterResponseParser parser = new CourseChapterResponseParser();

    @Test
    void parseSortsClampsFiltersEvidenceIndexesAndHandlesOverlap() {
        List<CourseChapterEvidenceItem> evidence = List.of(
            evidence(0, 0L, 240000L),
            evidence(1, 240000L, 480000L)
        );

        List<CourseChapterResponseParser.ParsedCourseChapter> chapters = parser.parse("""
            {"chapters":[
              {"title":"第二章","summary":"后半段","startTimeMillis":200000,"endTimeMillis":999999,"keywords":["训练"],"evidenceIndexes":[1,99,-1]},
              {"title":"第一章","summary":"前半段","startTimeMillis":-1000,"endTimeMillis":260000,"keywords":["模型"],"evidenceIndexes":[0]},
              {"title":"无效","summary":"无效","startTimeMillis":10,"endTimeMillis":5,"keywords":[],"evidenceIndexes":[0]}
            ]}
            """, evidence, 20);

        assertThat(chapters).hasSize(2);
        assertThat(chapters.get(0).title()).isEqualTo("第一章");
        assertThat(chapters.get(0).startTimeMillis()).isEqualTo(0L);
        assertThat(chapters.get(0).endTimeMillis()).isEqualTo(240000L);
        assertThat(chapters.get(0).evidenceIndexes()).containsExactly(0);
        assertThat(chapters.get(1).title()).isEqualTo("第二章");
        assertThat(chapters.get(1).startTimeMillis()).isEqualTo(240000L);
        assertThat(chapters.get(1).endTimeMillis()).isEqualTo(480000L);
        assertThat(chapters.get(1).evidenceIndexes()).containsExactly(1);
    }

    @Test
    void parseRejectsInvalidJson() {
        assertThatThrownBy(() -> parser.parse("{not-json", List.of(evidence(0, 0L, 1L)), 20))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AI_PROVIDER_FAILED);
    }

    @Test
    void parseClampsModelTailBeyondAuthoritativeEvidenceDuration() {
        long durationMillis = 4_090_265L;
        List<CourseChapterResponseParser.ParsedCourseChapter> chapters = parser.parse("""
            {"chapters":[
              {"title":"最后一章","summary":"课程结尾","startTimeMillis":4080000,"endTimeMillis":4140000,"keywords":["结尾"],"evidenceIndexes":[0]}
            ]}
            """, List.of(evidence(0, 4_080_000L, durationMillis)), 20);

        assertThat(chapters).singleElement().satisfies(chapter -> {
            assertThat(chapter.startTimeMillis()).isEqualTo(4_080_000L);
            assertThat(chapter.endTimeMillis()).isEqualTo(durationMillis);
            assertThat(chapter.endTimeMillis()).isLessThan(4_140_000L);
        });
    }

    @Test
    void parsedTypeDoesNotExposeRawSensitiveFields() {
        assertThat(List.of(CourseChapterResponseParser.ParsedCourseChapter.class.getRecordComponents())
                .stream()
                .map(java.lang.reflect.RecordComponent::getName))
            .doesNotContain(
                "raw" + "Response",
                "raw" + "Prompt",
                "object" + "Key",
                "local" + "Path",
                "api" + "Key",
                "token"
            );
    }

    private static CourseChapterEvidenceItem evidence(int index, long start, long end) {
        return new CourseChapterEvidenceItem(index, start, end, "time", "text");
    }
}
