package com.example.courselingo.vision.ocr;

import static org.assertj.core.api.Assertions.assertThat;

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
}
