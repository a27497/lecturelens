package com.example.courselingo.learning;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.learning.service.LearningPackageResponseParser;
import org.junit.jupiter.api.Test;

class LearningPackageResponseParserTest {

    private final LearningPackageResponseParser parser = new LearningPackageResponseParser();

    @Test
    void parserAcceptsStandardJsonWithPromptShape() {
        LearningPackageResponseParser.ParsedLearningPackage parsed = parser.parse("""
            {
              "summary": "Course summary",
              "keyPoints": ["First point"],
              "glossary": [{"term": "Term", "definition": "Definition"}],
              "qa": [{"question": "Question", "answer": "Answer"}]
            }
            """);

        assertThat(parsed.title()).isEqualTo("Learning Package");
        assertThat(parsed.summary()).isEqualTo("Course summary");
        assertThat(parsed.keyPointsJson()).isEqualTo("[{\"index\":1,\"text\":\"First point\"}]");
        assertThat(parsed.glossaryJson()).isEqualTo("[{\"term\":\"Term\",\"definition\":\"Definition\",\"translation\":\"\"}]");
        assertThat(parsed.qaJson()).isEqualTo("[{\"question\":\"Question\",\"answer\":\"Answer\"}]");
    }

    @Test
    void parserAcceptsJsonWrappedInMarkdownCodeFence() {
        LearningPackageResponseParser.ParsedLearningPackage parsed = parser.parse("""
            ```json
            {
              "title": "Course Title",
              "summary": "Course summary",
              "keyPoints": [{"index": 1, "text": "First point"}],
              "glossary": [],
              "qa": []
            }
            ```
            """);

        assertThat(parsed.title()).isEqualTo("Course Title");
        assertThat(parsed.summary()).isEqualTo("Course summary");
    }

    @Test
    void parserExtractsJsonWhenResponseIncludesExplanationText() {
        LearningPackageResponseParser.ParsedLearningPackage parsed = parser.parse("""
            Here is the result:
            {"summary":"Short summary","keyPoints":["Point"],"glossary":[],"qa":[]}
            Thanks.
            """);

        assertThat(parsed.summary()).isEqualTo("Short summary");
        assertThat(parsed.keyPointsJson()).isEqualTo("[{\"index\":1,\"text\":\"Point\"}]");
    }

    @Test
    void parserAcceptsTopLevelFieldAliases() {
        LearningPackageResponseParser.ParsedLearningPackage parsed = parser.parse("""
            {
              "summary": "Course summary",
              "key_points": ["First point"],
              "terms": [{"term": "Bean", "definition": "Spring object"}],
              "questions": [{"question": "What is Spring?", "answer": "A framework."}]
            }
            """);

        assertThat(parsed.keyPointsJson()).isEqualTo("[{\"index\":1,\"text\":\"First point\"}]");
        assertThat(parsed.glossaryJson()).isEqualTo("[{\"term\":\"Bean\",\"definition\":\"Spring object\",\"translation\":\"\"}]");
        assertThat(parsed.qaJson()).isEqualTo("[{\"question\":\"What is Spring?\",\"answer\":\"A framework.\"}]");
    }

    @Test
    void parserAcceptsNestedFieldAliases() {
        LearningPackageResponseParser.ParsedLearningPackage parsed = parser.parse("""
            {
              "summary": "Course summary",
              "mainPoints": [{"text": "First point"}],
              "vocabulary": [{"term": "IoC", "explanation": "Inversion of control"}, {"term": "DI", "meaning": "Dependency injection"}],
              "qas": [{"q": "What is IoC?", "a": "A design principle."}]
            }
            """);

        assertThat(parsed.keyPointsJson()).isEqualTo("[{\"index\":1,\"text\":\"First point\"}]");
        assertThat(parsed.glossaryJson())
            .isEqualTo("[{\"term\":\"IoC\",\"definition\":\"Inversion of control\",\"translation\":\"\"},{\"term\":\"DI\",\"definition\":\"Dependency injection\",\"translation\":\"\"}]");
        assertThat(parsed.qaJson()).isEqualTo("[{\"question\":\"What is IoC?\",\"answer\":\"A design principle.\"}]");
    }

    @Test
    void parserUsesEmptyDefaultsForMissingOptionalFields() {
        LearningPackageResponseParser.ParsedLearningPackage parsed = parser.parse("{}");

        assertThat(parsed.title()).isEqualTo("Learning Package");
        assertThat(parsed.summary()).isEqualTo("");
        assertThat(parsed.keyPointsJson()).isEqualTo("[]");
        assertThat(parsed.glossaryJson()).isEqualTo("[]");
        assertThat(parsed.qaJson()).isEqualTo("[]");
    }

    @Test
    void parserConvertsStringArrayItemsToRecoverableObjects() {
        LearningPackageResponseParser.ParsedLearningPackage parsed = parser.parse("""
            {
              "summary": "Course summary",
              "points": ["First point"],
              "glossary": ["Term only"],
              "quiz": ["Question only"]
            }
            """);

        assertThat(parsed.keyPointsJson()).isEqualTo("[{\"index\":1,\"text\":\"First point\"}]");
        assertThat(parsed.glossaryJson()).isEqualTo("[{\"term\":\"Term only\",\"definition\":\"\",\"translation\":\"\"}]");
        assertThat(parsed.qaJson()).isEqualTo("[]");
    }

    @Test
    void parserDropsGlossaryItemsWithBlankTermAndAllowsBlankDefinition() {
        LearningPackageResponseParser.ParsedLearningPackage parsed = parser.parse("""
            {
              "summary": "Course summary",
              "keyPoints": [],
              "glossary": [
                {"term": "Valid term", "definition": ""},
                {"term": " ", "definition": "Should be dropped"},
                "",
                {"term": "Another term", "meaning": "Meaning"}
              ],
              "qa": []
            }
            """);

        assertThat(parsed.glossaryJson())
            .isEqualTo("[{\"term\":\"Valid term\",\"definition\":\"\",\"translation\":\"\"},{\"term\":\"Another term\",\"definition\":\"Meaning\",\"translation\":\"\"}]");
    }

    @Test
    void parserAllowsGlossaryToBecomeEmptyAfterDroppingInvalidItems() {
        LearningPackageResponseParser.ParsedLearningPackage parsed = parser.parse("""
            {
              "summary": "Course summary",
              "keyPoints": [],
              "glossary": [{"term": " ", "definition": ""}, ""],
              "qa": []
            }
            """);

        assertThat(parsed.glossaryJson()).isEqualTo("[]");
    }

    @Test
    void parserDropsQaItemsWithBlankQuestionOrAnswer() {
        LearningPackageResponseParser.ParsedLearningPackage parsed = parser.parse("""
            {
              "summary": "Course summary",
              "keyPoints": [],
              "glossary": [],
              "qa": [
                {"question": "Valid question", "answer": "Valid answer"},
                {"question": " ", "answer": "Dropped"},
                {"question": "Missing answer", "answer": ""},
                ""
              ]
            }
            """);

        assertThat(parsed.qaJson()).isEqualTo("[{\"question\":\"Valid question\",\"answer\":\"Valid answer\"}]");
    }

    @Test
    void parserFiltersBlankKeyPointsAndAllowsAllArraysToBeEmpty() {
        LearningPackageResponseParser.ParsedLearningPackage parsed = parser.parse("""
            {
              "summary": "Course summary",
              "keyPoints": [" ", {"text": ""}, {"text": "Valid point"}],
              "glossary": [],
              "qa": []
            }
            """);

        assertThat(parsed.keyPointsJson()).isEqualTo("[{\"index\":1,\"text\":\"Valid point\"}]");
        assertThat(parsed.glossaryJson()).isEqualTo("[]");
        assertThat(parsed.qaJson()).isEqualTo("[]");
    }

    @Test
    void parserConvertsFlatGlossaryStringPairsToObjects() {
        LearningPackageResponseParser.ParsedLearningPackage parsed = parser.parse("""
            {
              "summary": "Course summary",
              "keyPoints": [],
              "glossary": ["term1", "def1", "term2", "def2"],
              "qa": []
            }
            """);

        assertThat(parsed.glossaryJson())
            .isEqualTo("[{\"term\":\"term1\",\"definition\":\"def1\",\"translation\":\"\"},{\"term\":\"term2\",\"definition\":\"def2\",\"translation\":\"\"}]");
    }

    @Test
    void parserFlattensNestedQaArrays() {
        LearningPackageResponseParser.ParsedLearningPackage parsed = parser.parse("""
            {
              "summary": "Course summary",
              "keyPoints": [],
              "glossary": [],
              "qa": [[{"question": "Question", "answer": "Answer"}]]
            }
            """);

        assertThat(parsed.qaJson()).isEqualTo("[{\"question\":\"Question\",\"answer\":\"Answer\"}]");
    }

    @Test
    void parserKeepsLongOrRepetitiveQaAnswerAsRecoverableStructure() {
        LearningPackageResponseParser.ParsedLearningPackage parsed = parser.parse("""
            {
              "summary": "Course summary",
              "keyPoints": [],
              "glossary": [],
              "qa": [{"question": "Question", "answer": "answer answer answer answer answer answer answer answer answer answer answer answer answer answer answer answer answer answer answer answer"}]
            }
            """);

        assertThat(parsed.qaJson()).contains("answer answer answer");
    }

    @Test
    void parserOnlyRejectsCompletelyInvalidJsonOrUnrecoverableStructure() {
        assertValidationFailure("{not-json");
        assertValidationFailure("[\"not\", \"an\", \"object\"]");
    }

    @Test
    void parserKeepsErrorsSanitized() {
        assertThatThrownBy(() -> parser.parse("""
            {"title":"Authorization: Bearer token","summary":"Summary","keyPoints":[{"index":1,"text":"Point"}],"glossary":[],"qa":[]}
            """))
            .isInstanceOf(BusinessException.class)
            .satisfies(error -> assertSafe(error.getMessage()));
    }

    private void assertValidationFailure(String content) {
        assertThatThrownBy(() -> parser.parse(content))
            .isInstanceOf(BusinessException.class)
            .satisfies(error -> {
                assertThat(((BusinessException) error).errorCode()).isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);
                assertSafe(error.getMessage());
            });
    }

    private static void assertSafe(String message) {
        assertThat(message).doesNotContain("C:\\", "/home/");
        assertThat(message.toLowerCase()).doesNotContain("token", "secret", "api key", "authorization");
    }
}
