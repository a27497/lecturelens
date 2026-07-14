package com.example.courselingo.ai.llm;

public interface OpenAiCompatibleHttpTransport {

    OpenAiCompatibleClientResponse send(OpenAiCompatibleChatCompletionRequest request);
}
