package com.example.courselingo.ai.llm;

import java.time.Duration;

public class JavaHttpOpenAiCompatibleLlmClient implements OpenAiCompatibleLlmClient {

    private final OpenAiCompatibleHttpTransport transport;

    public JavaHttpOpenAiCompatibleLlmClient(Duration connectTimeout) {
        this(new DefaultOpenAiCompatibleHttpTransport(connectTimeout));
    }

    JavaHttpOpenAiCompatibleLlmClient(OpenAiCompatibleHttpTransport transport) {
        this.transport = transport;
    }

    @Override
    public OpenAiCompatibleClientResponse complete(OpenAiCompatibleChatCompletionRequest request) {
        return transport.send(request);
    }
}
