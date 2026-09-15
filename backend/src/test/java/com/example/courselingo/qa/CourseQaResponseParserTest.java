package com.example.courselingo.qa;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.qa.service.CourseQaResponseParser;
import java.util.List;
import org.junit.jupiter.api.Test;

class CourseQaResponseParserTest {

    private final CourseQaResponseParser parser = new CourseQaResponseParser();

    @Test
    void parseKeepsOnlyValidCitedEvidenceIndexes() {
        CourseQaResponseParser.ParsedCourseQaResponse parsed = parser.parse(
            """
            {"answer":"Answer from course evidence","citedEvidenceIndexes":[0,2,99,-1,2]}
            """,
            3
        );

        assertThat(parsed.answer()).isEqualTo("Answer from course evidence");
        assertThat(parsed.citedEvidenceIndexes()).containsExactly(0, 2);
    }

    @Test
    void parseRejectsInvalidJsonOrBlankAnswer() {
        assertThatThrownBy(() -> parser.parse("{not-json", 1))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AI_PROVIDER_FAILED);

        assertThatThrownBy(() -> parser.parse("{\"answer\":\" \",\"citedEvidenceIndexes\":[]}", 1))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AI_PROVIDER_FAILED);
    }

    @Test
    void refusalNeverCarriesCitationsAndFractionalIndexesAreNotCoerced() {
        var refusal = parser.parse("""
            {"answer":"当前课程内容中没有找到明确依据","citedEvidenceIndexes":[0,1]}
            """, 2);
        assertThat(refusal.citedEvidenceIndexes()).isEmpty();
        var answer = parser.parse("""
            {"answer":"Supported answer","citedEvidenceIndexes":[0.5,1.0,1,"0"]}
            """, 2);
        assertThat(answer.citedEvidenceIndexes()).containsExactly(1);
    }

    @Test
    void parsedTypeDoesNotExposeRawProviderResponse() {
        assertThat(List.of(CourseQaResponseParser.ParsedCourseQaResponse.class.getRecordComponents())
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
}
