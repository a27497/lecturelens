package com.example.courselingo.subtitle.service;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.courselingo.ai.llm.LlmRequest;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.Test;

class SubtitleTranslationPromptFactoryTest {

    @Test
    void alignedZhCnPromptRequiresNaturalSimplifiedChineseAndCompleteJsonCoverage() {
        LlmRequest request = SubtitleTranslationPromptFactory.buildAlignedBatch(
            command("en", "zh-CN"),
            List.of(segment(0, "Spring Boot course introduction")),
            Duration.ofSeconds(30),
            4096,
            1
        );

        String prompt = combinedPrompt(request);
        assertThat(prompt)
            .contains("Target language is Simplified Chinese (zh-CN).")
            .contains("Translate all normal prose into natural Simplified Chinese.")
            .contains("Do not copy complete English sentences from the source.")
            .contains("Only established technical terms, product names, API names")
            .contains("Do not summarize, omit or merge segments.")
            .contains("Return only one valid JSON object")
            .contains("Return exactly one non-empty text item for every input segment");
        assertThat(request.metadata())
            .containsEntry("translationMode", "alignedBatch")
            .containsEntry("semanticAttempt", 1)
            .containsEntry("semanticRetry", false)
            .containsEntry("sourceSegmentCount", 1);
    }

    @Test
    void semanticRetryPromptRestatesCompleteBatchWithoutPreviousProviderResponse() {
        LlmRequest request = SubtitleTranslationPromptFactory.buildAlignedBatchSemanticRetry(
            command("en", "zh-CN"),
            List.of(segment(0, "Spring Boot course introduction")),
            Duration.ofSeconds(30),
            4096,
            1,
            2,
            "TARGET_LANGUAGE_MISMATCH"
        );

        String prompt = combinedPrompt(request);
        assertThat(prompt)
            .contains("The previous JSON structure was valid")
            .contains("did not satisfy the requested target language")
            .contains("Return the complete batch again.")
            .contains("All normal prose must be natural Simplified Chinese.")
            .contains("Do not copy the English source.")
            .contains("Return exactly one item for every input segment.")
            .contains("Spring Boot course introduction")
            .doesNotContain("PREVIOUS_RAW_RESPONSE_SENTINEL");
        assertThat(request.metadata())
            .containsEntry("translationMode", "alignedBatch")
            .containsEntry("semanticAttempt", 2)
            .containsEntry("semanticRetry", true)
            .containsEntry("semanticRetryReason", "TARGET_LANGUAGE_MISMATCH")
            .containsEntry("sourceSegmentCount", 1);
    }

    @Test
    void knownTargetLanguageCodesUseClearDisplayNamesAndUnknownCodesRemainVisible() {
        assertThat(systemPrompt("zh-TW")).contains("Traditional Chinese (zh-TW)");
        assertThat(systemPrompt("en")).contains("English (en)");
        assertThat(systemPrompt("ja")).contains("Japanese (ja)");
        assertThat(systemPrompt("ko")).contains("Korean (ko)");
        assertThat(systemPrompt("fr-CA")).contains("fr-CA");
    }

    private static String systemPrompt(String targetLanguage) {
        LlmRequest request = SubtitleTranslationPromptFactory.buildAlignedBatch(
            command("en", targetLanguage),
            List.of(segment(0, "source")),
            Duration.ofSeconds(30),
            4096,
            1
        );
        return request.messages().getFirst().content();
    }

    private static String combinedPrompt(LlmRequest request) {
        return request.messages().stream()
            .map(message -> message.content())
            .reduce("", (left, right) -> left + "\n" + right);
    }

    private static ValidatedTranslationCommand command(String sourceLanguage, String targetLanguage) {
        return new ValidatedTranslationCommand("task_1", 42L, sourceLanguage, targetLanguage, "req_1");
    }

    private static SubtitleSegment segment(int index, String text) {
        SubtitleSegment segment = new SubtitleSegment();
        segment.setSegmentIndex(index);
        segment.setText(text);
        return segment;
    }
}
