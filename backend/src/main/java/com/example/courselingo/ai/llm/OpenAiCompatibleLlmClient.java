package com.example.courselingo.ai.llm;

public interface OpenAiCompatibleLlmClient {

    OpenAiCompatibleClientResponse complete(OpenAiCompatibleChatCompletionRequest request);
}
