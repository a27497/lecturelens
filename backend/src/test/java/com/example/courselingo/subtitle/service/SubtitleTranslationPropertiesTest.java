package com.example.courselingo.subtitle.service;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class SubtitleTranslationPropertiesTest {

    @Test
    void semanticAttemptsDefaultToTwoAndInvalidValuesFallBackToTwo() {
        SubtitleTranslationProperties.FullText fullText = new SubtitleTranslationProperties.FullText();

        assertThat(fullText.getSemanticMaxAttempts()).isEqualTo(2);

        fullText.setSemanticMaxAttempts(1);
        assertThat(fullText.getSemanticMaxAttempts()).isEqualTo(1);

        fullText.setSemanticMaxAttempts(2);
        assertThat(fullText.getSemanticMaxAttempts()).isEqualTo(2);

        fullText.setSemanticMaxAttempts(3);
        assertThat(fullText.getSemanticMaxAttempts()).isEqualTo(2);

        fullText.setSemanticMaxAttempts(100);
        assertThat(fullText.getSemanticMaxAttempts()).isEqualTo(2);

        fullText.setSemanticMaxAttempts(Integer.MAX_VALUE);
        assertThat(fullText.getSemanticMaxAttempts()).isEqualTo(2);

        fullText.setSemanticMaxAttempts(0);
        assertThat(fullText.getSemanticMaxAttempts()).isEqualTo(2);

        fullText.setSemanticMaxAttempts(-1);
        assertThat(fullText.getSemanticMaxAttempts()).isEqualTo(2);
    }

    @Test
    void semanticAttemptsAreIndependentFromProviderTransportAttempts() {
        SubtitleTranslationProperties.FullText fullText = new SubtitleTranslationProperties.FullText();

        fullText.setMaxAttempts(4);
        fullText.setSemanticMaxAttempts(2);

        assertThat(fullText.getMaxAttempts()).isEqualTo(4);
        assertThat(fullText.getSemanticMaxAttempts()).isEqualTo(2);
    }
}
