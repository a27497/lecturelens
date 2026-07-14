package com.example.courselingo.ai.llm;

import dev.langchain4j.data.message.AiMessage;
import dev.langchain4j.data.message.ChatMessage;
import dev.langchain4j.data.message.SystemMessage;
import dev.langchain4j.data.message.UserMessage;
import java.util.List;

final class LangChain4jMessageMapper {

    private LangChain4jMessageMapper() {
    }

    static List<ChatMessage> toLangChain4jMessages(LlmRequest request) {
        return request.messages().stream()
            .map(LangChain4jMessageMapper::toLangChain4jMessage)
            .toList();
    }

    private static ChatMessage toLangChain4jMessage(LlmMessage message) {
        return switch (message.role()) {
            case SYSTEM -> SystemMessage.from(message.content());
            case USER -> UserMessage.from(message.content());
            case ASSISTANT -> AiMessage.from(message.content());
        };
    }
}
