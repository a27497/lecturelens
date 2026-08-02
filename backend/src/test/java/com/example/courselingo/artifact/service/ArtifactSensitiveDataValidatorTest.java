package com.example.courselingo.artifact.service;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class ArtifactSensitiveDataValidatorTest {

    private static final String FAKE_PRIVATE_KEY_BODY = "FAKE_PRIVATE_KEY_BODY_FOR_TESTING_ONLY";
    private static final String SECOND_FAKE_LINE = "SECOND_FAKE_LINE";

    @Test
    void keepsTeachingExamplesAndOrdinaryTechnicalContent() {
        String examples = """
            Run docker compose up and send an HTTP request to /api/orders.
            On Windows use C:\\Users\\demo\\project\\compose.yaml.
            On Linux use /home/example/project/compose.yaml.
            API_KEY=your-api-key
            Authorization: Bearer your-example-token
            The tokenizer emits a token stream, and token: a searchable unit.
            Tokenization and the access token concept are ordinary teaching topics.
            """;

        assertThat(ArtifactSensitiveDataValidator.containsSensitiveData(examples)).isFalse();
        assertThat(ArtifactSensitiveDataValidator.redactSensitiveData(examples)).isEqualTo(examples);
    }

    @Test
    void blocksRealisticCredentialsPrivatePathsKeysAndObjectKeys() {
        String unsafe = """
            api_key=sk_live_1234567890abcdef
            Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc123.signature
            eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJmaWN0aW9uYWwifQ.fakeSignature123
            C:\\Users\\alice\\Videos\\private.mp4
            /home/alice/private.mp4
            uploads/123e4567-e89b-12d3-a456-426614174000/source.mp4
            -----BEGIN PRIVATE KEY-----
            FAKE_PRIVATE_KEY_BODY_FOR_TESTING_ONLY
            -----END PRIVATE KEY-----
            """;

        assertThat(ArtifactSensitiveDataValidator.containsSensitiveData(unsafe)).isTrue();
        assertThat(ArtifactSensitiveDataValidator.redactSensitiveData(unsafe))
            .doesNotContain(
                "sk_live_1234567890abcdef",
                "eyJhbGciOiJIUzI1NiJ9",
                "fakeSignature123",
                "alice",
                "/home/alice",
                "BEGIN PRIVATE KEY",
                "123e4567-e89b-12d3-a456-426614174000"
            );
    }

    @Test
    void redactsCompletePkcs8PrivateKeyBlock() {
        assertPrivateKeyBlockRedacted("PRIVATE KEY");
    }

    @Test
    void redactsCompleteRsaPrivateKeyBlock() {
        assertPrivateKeyBlockRedacted("RSA PRIVATE KEY");
    }

    @Test
    void redactsCompleteEcPrivateKeyBlock() {
        assertPrivateKeyBlockRedacted("EC PRIVATE KEY");
    }

    @Test
    void redactsCompleteOpenSshPrivateKeyBlock() {
        assertPrivateKeyBlockRedacted("OPENSSH PRIVATE KEY");
    }

    @Test
    void redactsCompleteEncryptedPrivateKeyBlock() {
        assertPrivateKeyBlockRedacted("ENCRYPTED PRIVATE KEY");
    }

    @Test
    void redactsOtherSingleTokenPrivateKeyTypesSupportedByPreviousDetection() {
        assertPrivateKeyBlockRedacted("DSA PRIVATE KEY");
    }

    @Test
    void redactsPrivateKeyBlockWithCrLfLineEndings() {
        String input = "before\r\n" + pemBlock("PRIVATE KEY", "\r\n") + "\r\nafter";

        assertThat(ArtifactSensitiveDataValidator.redactSensitiveData(input))
            .isEqualTo("before\r\n[redacted]\r\nafter");
    }

    @Test
    void redactsMultiplePrivateKeyBlocksInOneText() {
        String input = "first\n"
            + pemBlock("PRIVATE KEY", "\n")
            + "\nmiddle\n"
            + pemBlock("RSA PRIVATE KEY", "\n")
            + "\nlast";

        assertThat(ArtifactSensitiveDataValidator.redactSensitiveData(input))
            .isEqualTo("first\n[redacted]\nmiddle\n[redacted]\nlast");
    }

    @Test
    void preservesCourseTextAroundIndentedPrivateKeyBlock() {
        String indentedBlock = pemBlock("EC PRIVATE KEY", "\n").replace("\n", "\n    ");
        String input = "course introduction\n    "
            + indentedBlock
            + "\ncourse conclusion";

        assertThat(ArtifactSensitiveDataValidator.redactSensitiveData(input))
            .isEqualTo("course introduction\n    [redacted]\ncourse conclusion");
    }

    @Test
    void redactsIncompletePrivateKeyFromBeginMarkerToEndOfText() {
        String input = "normal content\n"
            + "-----BEGIN PRIVATE KEY-----\n"
            + FAKE_PRIVATE_KEY_BODY
            + "\nsubsequent sensitive content";

        assertThat(ArtifactSensitiveDataValidator.redactSensitiveData(input))
            .isEqualTo("normal content\n[redacted]");
    }

    @Test
    void mismatchedEndMarkerDoesNotTerminatePrivateKeyRedaction() {
        String input = "normal content\n"
            + "-----BEGIN RSA PRIVATE KEY-----\n"
            + FAKE_PRIVATE_KEY_BODY
            + "\n-----END PRIVATE KEY-----\n"
            + "subsequent sensitive content";

        assertThat(ArtifactSensitiveDataValidator.redactSensitiveData(input))
            .isEqualTo("normal content\n[redacted]");
    }

    @Test
    void removesPrivateKeyBase64Body() {
        assertThat(ArtifactSensitiveDataValidator.redactSensitiveData(pemBlock("PRIVATE KEY", "\n")))
            .doesNotContain(FAKE_PRIVATE_KEY_BODY, SECOND_FAKE_LINE);
    }

    @Test
    void removesPrivateKeyEndMarker() {
        assertThat(ArtifactSensitiveDataValidator.redactSensitiveData(pemBlock("PRIVATE KEY", "\n")))
            .doesNotContain("END PRIVATE KEY");
    }

    @Test
    void keepsPublicKeyBlocks() {
        String publicKey = """
            -----BEGIN PUBLIC KEY-----
            FAKE_PUBLIC_KEY_BODY_FOR_TESTING_ONLY
            -----END PUBLIC KEY-----
            """;

        assertThat(ArtifactSensitiveDataValidator.containsSensitiveData(publicKey)).isFalse();
        assertThat(ArtifactSensitiveDataValidator.redactSensitiveData(publicKey)).isEqualTo(publicKey);
    }

    @Test
    void keepsCertificateBlocks() {
        String certificate = """
            -----BEGIN CERTIFICATE-----
            FAKE_CERTIFICATE_BODY_FOR_TESTING_ONLY
            -----END CERTIFICATE-----
            """;

        assertThat(ArtifactSensitiveDataValidator.containsSensitiveData(certificate)).isFalse();
        assertThat(ArtifactSensitiveDataValidator.redactSensitiveData(certificate)).isEqualTo(certificate);
    }

    @Test
    void keepsOrdinaryPrivateKeyTeachingExplanationWithoutPemMarkers() {
        String explanation = "PEM private keys generally begin with BEGIN PRIVATE KEY.";

        assertThat(ArtifactSensitiveDataValidator.containsSensitiveData(explanation)).isFalse();
        assertThat(ArtifactSensitiveDataValidator.redactSensitiveData(explanation)).isEqualTo(explanation);
    }

    @Test
    void handlesLongOrdinaryCourseTextWithoutFalsePositive() {
        String ordinaryText = "Docker, Java, and HTTP architecture lesson content.\n".repeat(20_000);

        assertThat(ArtifactSensitiveDataValidator.containsSensitiveData(ordinaryText)).isFalse();
        assertThat(ArtifactSensitiveDataValidator.redactSensitiveData(ordinaryText)).isEqualTo(ordinaryText);
    }

    private static void assertPrivateKeyBlockRedacted(String type) {
        String input = pemBlock(type, "\n");

        assertThat(ArtifactSensitiveDataValidator.containsSensitiveData(input)).isTrue();
        assertThat(ArtifactSensitiveDataValidator.redactSensitiveData(input)).isEqualTo("[redacted]");
    }

    private static String pemBlock(String type, String lineSeparator) {
        return "-----BEGIN " + type + "-----" + lineSeparator
            + "Comment: fictional test fixture" + lineSeparator
            + FAKE_PRIVATE_KEY_BODY + lineSeparator
            + lineSeparator
            + SECOND_FAKE_LINE + lineSeparator
            + "-----END " + type + "-----";
    }
}
