package com.example.courselingo.common.logging;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class SafeLogSanitizerTest {

    @Test
    void sanitizeRedactsSensitiveHeadersTokensPathsAndPromptFields() {
        String value = """
            Authorization: Bearer secret-token
            Cookie: session=abc
            Set-Cookie: refresh=abc
            api_key=abc
            apiKey=def
            api key=space
            token=ghi
            secret=jkl
            secretKey=compact
            secret key=space
            access token=raw
            password=pass
            refreshToken=refresh
            objectKey=internal/key
            object_key=internal/key
            password should not appear as a bare sensitive word
            raw prompt: user subtitle full text
            raw_response: model output
            C:\\Users\\demo\\audio\\source.wav
            /home/app/audio/source.wav
            /tmp/courselingo/audio.wav
            """;

        String sanitized = SafeLogSanitizer.sanitize(value);

        assertThat(sanitized)
            .doesNotContain("secret-token")
            .doesNotContain("session=abc")
            .doesNotContain("refresh=abc")
            .doesNotContain("api_key=abc")
            .doesNotContain("apiKey=def")
            .doesNotContain("api key=space")
            .doesNotContain("token=ghi")
            .doesNotContain("secret=jkl")
            .doesNotContain("secretKey=compact")
            .doesNotContain("secret key=space")
            .doesNotContain("access token=raw")
            .doesNotContain("password=pass")
            .doesNotContain("password should not appear")
            .doesNotContain("refreshToken=refresh")
            .doesNotContain("objectKey")
            .doesNotContain("object_key")
            .doesNotContain("internal/key")
            .doesNotContain("raw prompt")
            .doesNotContain("raw_response")
            .doesNotContain("user subtitle full text")
            .doesNotContain("model output")
            .doesNotContain("C:\\Users\\demo")
            .doesNotContain("/home/app")
            .doesNotContain("/tmp/courselingo")
            .contains("[redacted]");
    }

    @Test
    void sanitizeAndLimitTruncatesAfterRedaction() {
        String value = "token=secret " + "x".repeat(600);

        String sanitized = SafeLogSanitizer.sanitizeAndLimit(value, 64);

        assertThat(sanitized).hasSize(64);
        assertThat(sanitized).doesNotContain("secret");
    }
}
