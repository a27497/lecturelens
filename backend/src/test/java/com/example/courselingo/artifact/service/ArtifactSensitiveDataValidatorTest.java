package com.example.courselingo.artifact.service;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class ArtifactSensitiveDataValidatorTest {

    @Test
    void keepsTeachingExamplesAndOrdinaryTechnicalContent() {
        String examples = """
            Run docker compose up and send an HTTP request to /api/orders.
            On Windows use C:\\Users\\demo\\project\\compose.yaml.
            On Linux use /home/example/project/compose.yaml.
            API_KEY=your-api-key
            Authorization: Bearer your-example-token
            """;

        assertThat(ArtifactSensitiveDataValidator.containsSensitiveData(examples)).isFalse();
        assertThat(ArtifactSensitiveDataValidator.redactSensitiveData(examples)).isEqualTo(examples);
    }

    @Test
    void blocksRealisticCredentialsPrivatePathsKeysAndObjectKeys() {
        String unsafe = """
            api_key=sk_live_1234567890abcdef
            Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc123.signature
            C:\\Users\\alice\\Videos\\private.mp4
            /home/alice/private.mp4
            -----BEGIN PRIVATE KEY-----
            uploads/123e4567-e89b-12d3-a456-426614174000/source.mp4
            """;

        assertThat(ArtifactSensitiveDataValidator.containsSensitiveData(unsafe)).isTrue();
        assertThat(ArtifactSensitiveDataValidator.redactSensitiveData(unsafe))
            .doesNotContain(
                "sk_live_1234567890abcdef",
                "eyJhbGciOiJIUzI1NiJ9",
                "alice",
                "/home/alice",
                "BEGIN PRIVATE KEY",
                "123e4567-e89b-12d3-a456-426614174000"
            );
    }
}
