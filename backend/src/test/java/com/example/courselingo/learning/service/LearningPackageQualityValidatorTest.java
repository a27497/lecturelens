package com.example.courselingo.learning.service;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.stream.IntStream;
import java.util.List;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.example.courselingo.learning.dto.GlossaryItem;
import com.example.courselingo.learning.dto.KeyPointItem;
import org.junit.jupiter.api.Test;

class LearningPackageQualityValidatorTest {

    private static final LearningPackageQualityProfile LONG = new LearningPackageQualityProfile(
        "LONG", 220, 800, 6, 12, 8, 15, 5, 8, false
    );

    @Test
    void reportsExactLongCourseDeficits() {
        var parsed = new LearningPackageResponseParser().parse("""
            {"title":"课程学习资料","summary":"简短总结","keyPoints":["一点"],
             "glossary":[{"term":"Spring Boot","definition":"框架"}],
             "qa":[{"question":"什么是框架？","answer":"课程中的框架。"}]}
            """, "zh-CN");

        LearningPackageQualityReport report = LearningPackageQualityValidator.validate(parsed, LONG, "zh-CN");

        assertThat(report.valid()).isFalse();
        assertThat(report.promptText())
            .contains("summary has", "keyPoints has 1", "glossary has 1", "qa has 1");
    }

    @Test
    void deterministicLongFallbackMeetsTierAndCoversDistributedEvidence() {
        String evidence = IntStream.range(0, 36)
            .mapToObj(index -> "课程证据片段" + index + "讲解 Spring Boot、Docker、HTTP 和微服务组件之间的关系。")
            .reduce("", (left, right) -> left + right);

        var parsed = LearningPackageFallbackFactory.build(evidence, "zh-CN", LONG);
        LearningPackageQualityReport report = LearningPackageQualityValidator.validate(parsed, LONG, "zh-CN");

        assertThat(report.valid()).as(report.promptText()).isTrue();
        assertThat(parsed.title()).isEqualTo("课程学习资料");
        assertThat(parsed.summary()).contains("课程证据片段0").contains("课程证据片段35");
    }

    @Test
    void parserUsesTargetAwareChineseDefaultsForAllChineseVariants() {
        LearningPackageResponseParser parser = new LearningPackageResponseParser();

        assertThat(parser.parse("{}", "zh").title()).isEqualTo("课程学习资料");
        assertThat(parser.parse("{}", "zh-CN").title()).isEqualTo("课程学习资料");
        assertThat(parser.parse("{}", "zh-TW").title()).isEqualTo("课程学习资料");
        assertThat(parser.parse("{}", "en").title()).isEqualTo("Learning Package");
    }

    @Test
    void fallbackDoesNotDuplicateSentencesOrCaseVariantsOfGlossaryTerms() throws Exception {
        String evidence = IntStream.range(0, 16)
            .mapToObj(index -> index % 2 == 0
                ? "Spring Boot module " + index + " explains Docker routing and HTTP contracts."
                : "spring boot module " + index + " compares docker routing with http clients.")
            .collect(java.util.stream.Collectors.joining(" "));

        var parsed = LearningPackageFallbackFactory.build(evidence, "en", LONG);
        List<GlossaryItem> glossary = new ObjectMapper().readValue(
            parsed.glossaryJson(), new TypeReference<List<GlossaryItem>>() { }
        );
        List<KeyPointItem> keyPoints = new ObjectMapper().readValue(
            parsed.keyPointsJson(), new TypeReference<List<KeyPointItem>>() { }
        );

        assertThat(glossary).extracting(GlossaryItem::term)
            .doesNotHaveDuplicates();
        assertThat(glossary.stream().map(item -> item.term().toLowerCase(java.util.Locale.ROOT)).toList())
            .doesNotHaveDuplicates();
        assertThat(keyPoints).extracting(KeyPointItem::text).doesNotHaveDuplicates();
    }
}
