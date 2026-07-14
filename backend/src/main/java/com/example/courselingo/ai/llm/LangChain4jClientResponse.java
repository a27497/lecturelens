package com.example.courselingo.ai.llm;

import dev.langchain4j.model.chat.response.ChatResponse;
import java.time.Duration;

public record LangChain4jClientResponse(
    ChatResponse response,
    Duration duration
) {

    public LangChain4jClientResponse {
        duration = duration == null ? Duration.ZERO : duration;
    }
}
