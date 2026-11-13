package com.example.courselingo.ai.asr;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;

class AsrTextNormalizerTest {

    @Test
    void cleansTokensEmojiControlsAndObviousEnglishTechnicalJoins() {
        String normalized = AsrTextNormalizer.normalize(
            "<|en|> SpringBoot\u0000 APIGateway 😀 DockerCompose!!! HTTPrequest",
            "en-US"
        );

        assertThat(normalized)
            .isEqualTo("Spring Boot API Gateway Docker Compose! HTTP request")
            .doesNotContain("<|en|>", "😀", "\u0000");
    }

    @Test
    void lineBreaksAndTabsStayWordBoundaries() {
        assertThat(AsrTextNormalizer.normalize(
            "Remember, in the\nfirst lecture, we drew a diagram\r\nsort of\tlike this. This is\u0085my memory.",
            "en"
        )).isEqualTo("Remember, in the first lecture, we drew a diagram sort of like this. This is my memory.");
        assertThat(AsrTextNormalizer.normalize("one \n\n  two", "en")).isEqualTo("one two");
    }

    @Test
    void lineBreaksNextToCjkTextAddNoSpace() {
        assertThat(AsrTextNormalizer.normalize("字符串\n不可变", "zh-CN")).isEqualTo("字符串不可变");
        assertThat(AsrTextNormalizer.normalize("调用 API\n网关。\n下一步", "zh-CN")).isEqualTo("调用 API网关。下一步");
        assertThat(AsrTextNormalizer.normalize("变量 s\n is bound", "zh-CN")).isEqualTo("变量 s is bound");
    }

    @Test
    void removesOnlyIsolatedLowRatioCjkFromEnglishAndKeepsLegitimateChineseTerms() {
        assertThat(AsrTextNormalizer.normalize(
            "This deliberately long English sentence discusses the Java backend and Spring Boot architecture 你 today",
            "en"
        )).doesNotContain("你");
        assertThat(AsrTextNormalizer.normalize("Spring Boot 微服务 网关", "en"))
            .contains("微服务", "网关");
    }

    @Test
    void deduplicatesChunkBoundaryTokensWithoutJoiningWords() {
        List<TranscribedSegment> normalized = AsrTextNormalizer.normalizeAndDeduplicate(List.of(
            new TranscribedSegment(0, 0, 2000, "Deploy the API Gateway with Docker Compose"),
            new TranscribedSegment(1, 1800, 4000, "Docker Compose for the Java backend")
        ), "en-GB");

        assertThat(normalized).extracting(TranscribedSegment::text)
            .containsExactly("Deploy the API Gateway with Docker Compose", "for the Java backend");
    }
}
