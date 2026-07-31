package com.example.courselingo.vision.ocr;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertTimeoutPreemptively;

import java.time.Duration;

import org.junit.jupiter.api.Test;

class OcrTextQualityEvaluatorTest {

    @Test
    void rejectsShortSymbolHeavyOcrNoise() {
        assertThat(OcrTextQualityEvaluator.isUseful("aw & 9D", null)).isFalse();
        assertThat(OcrTextQualityEvaluator.isUseful("oe 8 Sr", null)).isFalse();
        assertThat(OcrTextQualityEvaluator.isUseful("宸?i…= SY", null)).isFalse();
        assertThat(OcrTextQualityEvaluator.isUseful("QO sD k 3 dl", null)).isFalse();
    }

    @Test
    void rejectsBracePrefixedLatinOcrNoise() {
        assertThat(OcrTextQualityEvaluator.isUseful("{emcee ade ie ot...", null)).isFalse();
    }

    @Test
    void preservesReadableEnglishAndChineseText() {
        assertThat(OcrTextQualityEvaluator.isUseful("What is OpenCL?", null)).isTrue();
        assertThat(OcrTextQualityEvaluator.isUseful("Traditional Chatbot", null)).isTrue();
        assertThat(OcrTextQualityEvaluator.isUseful("React pattern", null)).isTrue();
        assertThat(OcrTextQualityEvaluator.isUseful("这是一段正常的中文课程文字", null)).isTrue();
    }

    @Test
    void rejectsLowConfidenceTextEvenWhenCharactersLookReadable() {
        assertThat(OcrTextQualityEvaluator.isUseful("Traditional Chatbot", 0.2)).isFalse();
        assertThat(OcrTextQualityEvaluator.isUseful("Traditional Chatbot", 0.82)).isTrue();
    }

    @Test
    void rejectsFictionalNoiseWithTheSameFragmentedStructureAsRealOcr() {
        var report = OcrTextQualityEvaluator.evaluate(
            "RX eee I tok 一 mm c i eS yr * zz q p", null, "chi_sim+eng", "BROWSER"
        );

        assertThat(report.useful()).isFalse();
        assertThat(report.reason()).isIn("fragmented_single_character_tokens", "symbol_heavy");
    }

    @Test
    void preservesTechnicalCodeCommandsPathsAndSlides() {
        assertThat(OcrTextQualityEvaluator.isUseful("Spring Boot API Gateway", null, "eng", "PPT")).isTrue();
        assertThat(OcrTextQualityEvaluator.isUseful("docker compose up -d", null, "eng", "TERMINAL")).isTrue();
        assertThat(OcrTextQualityEvaluator.isUseful("public static void main(String[] args)", null, "eng", "CODE")).isTrue();
        assertThat(OcrTextQualityEvaluator.isUseful("GET /students HTTP/1.1", null, "eng", "DIAGRAM")).isTrue();
        assertThat(OcrTextQualityEvaluator.isUseful("C++ architecture.cpp", null, "eng", "CODE")).isTrue();
    }

    @Test
    void rejectsLanguageMismatchAndPrivateUseCharacters() {
        assertThat(OcrTextQualityEvaluator.evaluate("无意乱码汉字输出内容", null, "eng", "OTHER").useful()).isFalse();
        assertThat(OcrTextQualityEvaluator.evaluate("Readable text \uE000 hidden", null, "eng", "PPT").reason())
            .isEqualTo("control_private_or_replacement_character");
    }

    @Test
    void evaluatesLongOrdinaryTechnicalTextWithinABoundedTime() {
        String text = java.util.stream.IntStream.range(0, 20_000)
            .mapToObj(index -> "SpringBootModule" + index + " APIService" + index + " HTTPRoute" + index)
            .collect(java.util.stream.Collectors.joining(" "));

        assertTimeoutPreemptively(Duration.ofSeconds(2), () ->
            assertThat(OcrTextQualityEvaluator.isUseful(text, 0.95d, "eng", "PPT")).isTrue()
        );
    }
}
