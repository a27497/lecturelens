package com.example.courselingo.ai.llm;

import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;

class LlmProviderFailureClassifierTest {
    @Test void recognizesObservedContextCodeAndKeepsRateAndAccessErrorsDistinct() {
        assertThat(LlmProviderFailureClassifier.classify(400,
            "{\"error\":{\"code\":\"exceed_context_size_error\"}}", null).category())
            .isEqualTo(LlmProviderFailureCategory.CONTEXT_TOO_LARGE);
        assertThat(LlmProviderFailureClassifier.classify(429, "", null).category())
            .isEqualTo(LlmProviderFailureCategory.RATE_LIMIT);
        assertThat(LlmProviderFailureClassifier.classify(403, "", null).category())
            .isEqualTo(LlmProviderFailureCategory.AUTHENTICATION);
    }

    @Test void preservesTypedStageDetailsWithoutParsingItsMessageOrCause() {
        var details = new LlmProviderFailureDetails(LlmProviderFailureCategory.CONTEXT_TOO_LARGE, 400, null, false);
        assertThat(LlmProviderFailureClassifier.from(new LlmStageException("LEARNING_PACKAGE", details, null)))
            .isEqualTo(details);
    }
}
