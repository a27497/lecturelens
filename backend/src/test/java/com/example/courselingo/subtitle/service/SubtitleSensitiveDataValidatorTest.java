package com.example.courselingo.subtitle.service;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class SubtitleSensitiveDataValidatorTest {

    @Test
    void allowsOrdinarySecurityAndSearchTerminology() {
        assertThat(SubtitleSensitiveDataValidator.containsSensitiveData(
            "The tokenizer emits one token for each searchable term."
        )).isFalse();
        assertThat(SubtitleSensitiveDataValidator.containsSensitiveData(
            "A secret ballot and token authentication are normal course topics."
        )).isFalse();
        assertThat(SubtitleSensitiveDataValidator.containsSensitiveData(
            "The slide defines token: a searchable unit."
        )).isFalse();
        assertThat(SubtitleSensitiveDataValidator.containsSensitiveData(
            "Tokenization and the access token concept are ordinary course content."
        )).isFalse();
        assertThat(SubtitleSensitiveDataValidator.containsSensitiveData(
            "Use token=your-token in this placeholder example."
        )).isFalse();
    }

    @Test
    void stillRejectsCredentialShapedValuesAndPrivatePaths() {
        assertThat(SubtitleSensitiveDataValidator.containsSensitiveData("token=abc123-secret-value")).isTrue();
        assertThat(SubtitleSensitiveDataValidator.containsSensitiveData("Authorization: Bearer abc123secret")).isTrue();
        assertThat(SubtitleSensitiveDataValidator.containsSensitiveData("Authorization Bearer token")).isTrue();
        assertThat(SubtitleSensitiveDataValidator.containsSensitiveData(
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJmaWN0aW9uYWwifQ.fakeSignature123"
        )).isTrue();
        assertThat(SubtitleSensitiveDataValidator.containsSensitiveData("C:\\Users\\alice\\private.txt")).isTrue();
        assertThat(SubtitleSensitiveDataValidator.containsSensitiveData("/home/alice/private.txt")).isTrue();
    }
}
