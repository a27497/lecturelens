package com.example.courselingo.ai.llm;

import dev.langchain4j.data.message.ChatMessage;
import java.time.Duration;
import java.util.List;

public record LangChain4jClientRequest(
    List<ChatMessage> messages,
    String model,
    Duration timeout,
    Double temperature,
    Integer maxTokens
) {

    public LangChain4jClientRequest {
        messages = messages == null ? List.of() : List.copyOf(messages);
        timeout = timeout == null ? Duration.ZERO : timeout;
    }
}
