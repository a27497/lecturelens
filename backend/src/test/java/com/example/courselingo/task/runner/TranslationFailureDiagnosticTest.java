package com.example.courselingo.task.runner;

import com.example.courselingo.ai.llm.TranslationFailure;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.*;

class TranslationFailureDiagnosticTest {
    @Test void taskDiagnosticPreservesTheSafeSpecificTranslationCategory() {
        var failure=new TranslationFailure(TranslationFailure.Reason.TRUNCATED,200,null,"length",0,TranslationFailure.Check.OUTPUT_TRUNCATED);
        var record=LlmFailureDiagnostic.from(failure,null,"mock");
        assertThat(record.errorCode()).isEqualTo("TRUNCATED");
        assertThat(record.errorMessage()).contains("OUTPUT_TRUNCATED");
        assertThat(record.retryable()).isFalse();
    }
}
