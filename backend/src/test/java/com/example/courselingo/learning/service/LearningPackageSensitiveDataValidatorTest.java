package com.example.courselingo.learning.service;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class LearningPackageSensitiveDataValidatorTest {

    @Test
    void allowsOrdinarySecurityAndSearchTerminology() {
        assertThat(LearningPackageSensitiveDataValidator.containsSensitiveData(
            "Full-text search converts the query into a token stream."
        )).isFalse();
        assertThat(LearningPackageSensitiveDataValidator.containsSensitiveData(
            "The lecture compares public-key and secret-sharing algorithms."
        )).isFalse();
        assertThat(LearningPackageSensitiveDataValidator.containsSensitiveData(
            "The glossary defines token: a searchable unit."
        )).isFalse();
        assertThat(LearningPackageSensitiveDataValidator.containsSensitiveData(
            "Tokenization and the access token concept are covered in this lesson."
        )).isFalse();
        assertThat(LearningPackageSensitiveDataValidator.containsSensitiveData(
            "Set api_key=example-value in the sample configuration."
        )).isFalse();
    }

    @Test
    void stillRejectsCredentialShapedValuesAndPrivatePaths() {
        assertThat(LearningPackageSensitiveDataValidator.containsSensitiveData("api_key=sk-1234567890")).isTrue();
        assertThat(LearningPackageSensitiveDataValidator.containsSensitiveData("secret abc123-value")).isTrue();
        assertThat(LearningPackageSensitiveDataValidator.containsSensitiveData("Authorization Bearer abc123")).isTrue();
        assertThat(LearningPackageSensitiveDataValidator.containsSensitiveData(
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJmaWN0aW9uYWwifQ.fakeSignature123"
        )).isTrue();
        assertThat(LearningPackageSensitiveDataValidator.containsSensitiveData("C:\\Users\\alice\\private.txt")).isTrue();
        assertThat(LearningPackageSensitiveDataValidator.containsSensitiveData("/home/alice/private.txt")).isTrue();
    }
}
