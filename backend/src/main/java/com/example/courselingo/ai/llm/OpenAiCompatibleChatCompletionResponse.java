package com.example.courselingo.ai.llm;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

@JsonIgnoreProperties(ignoreUnknown = true)
record OpenAiCompatibleChatCompletionResponse(
    String id,
    String model,
    List<Choice> choices,
    Usage usage
) {

    @JsonIgnoreProperties(ignoreUnknown = true)
    record Choice(
        Message message,
        @JsonProperty("finish_reason") String finishReason
    ) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    record Message(
        String role,
        String content
    ) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    record Usage(
        @JsonProperty("prompt_tokens") Integer promptTokens,
        @JsonProperty("completion_tokens") Integer completionTokens,
        @JsonProperty("total_tokens") Integer totalTokens
    ) {
    }
}
