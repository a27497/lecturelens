package com.example.courselingo.ai.llm;

import dev.langchain4j.data.message.AiMessage;
import dev.langchain4j.model.chat.response.ChatResponse;
import dev.langchain4j.model.output.FinishReason;
import dev.langchain4j.model.output.TokenUsage;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

final class LangChain4jResultMapper {

    private static final String UNKNOWN_FINISH_REASON = "UNKNOWN";

    private LangChain4jResultMapper() {
    }

    static LlmResult toLlmResult(
        String providerName,
        String fallbackModel,
        LangChain4jClientResponse clientResponse
    ) {
        if (clientResponse == null || clientResponse.response() == null) {
            throw new LangChain4jLlmException("LangChain4j LLM response is empty", false);
        }

        ChatResponse response = clientResponse.response();
        AiMessage aiMessage = response.aiMessage();
        TokenUsage tokenUsage = response.tokenUsage();
        FinishReason finishReason = response.finishReason();

        var usage = tokenUsage == null ? new LlmUsage(null, null, null)
            : new LlmUsage(tokenUsage.inputTokenCount(), tokenUsage.outputTokenCount(), tokenUsage.totalTokenCount());
        Integer reasoning = tokenUsage instanceof dev.langchain4j.model.openai.OpenAiTokenUsage openAi
            && openAi.outputTokensDetails() != null ? openAi.outputTokensDetails().reasoningTokens() : null;
        // SDK responses do not expose the exact successful transport status; do not invent 200.
        if (finishReason == FinishReason.LENGTH)
            throw new LlmOutputException(new LlmOutputDiagnostics(LlmOutputDiagnostics.Reason.TRUNCATED,
                null, usage, "length", reasoning));
        if (OpenAiCompatibleRequestOptionsAdapter.supportsDeepSeekThinkingToggle(fallbackModel)
            && (aiMessage == null || aiMessage.text() == null || aiMessage.text().isBlank()))
            throw new LlmOutputException(new LlmOutputDiagnostics(LlmOutputDiagnostics.Reason.EMPTY_OUTPUT,
                null, usage, finishReason == FinishReason.STOP ? "stop" : null, reasoning));

        Map<String, Object> metadata = new HashMap<>();
        safeResponseId(response).ifPresent(traceId -> metadata.put("providerTraceId", traceId));

        return new LlmResult(
            providerName,
            textOrDefault(response.modelName(), fallbackModel),
            aiMessage == null || aiMessage.text() == null ? "" : aiMessage.text(),
            finishReason == null ? UNKNOWN_FINISH_REASON : finishReason.name(),
            usage,
            clientResponse.duration(),
            metadata
        );
    }

    private static Optional<String> safeResponseId(ChatResponse response) {
        String id = response.id();
        if (id == null || id.isBlank() || LlmErrorSanitizer.containsSensitiveData(id)) {
            return Optional.empty();
        }
        return Optional.of(id.strip());
    }

    private static String textOrDefault(String value, String fallback) {
        return value == null || value.isBlank() ? fallback : value.strip();
    }
}
