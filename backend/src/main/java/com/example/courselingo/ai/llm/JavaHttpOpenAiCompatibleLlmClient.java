package com.example.courselingo.ai.llm;

import java.time.Duration;

public class JavaHttpOpenAiCompatibleLlmClient implements OpenAiCompatibleLlmClient {

    private final OpenAiCompatibleHttpTransport transport;
    private ModelCallObserver observer=ModelCallObserver.NOOP;
    public JavaHttpOpenAiCompatibleLlmClient observed(ModelCallObserver observer){this.observer=observer;return this;}

    public JavaHttpOpenAiCompatibleLlmClient(Duration connectTimeout) {
        this(new DefaultOpenAiCompatibleHttpTransport(connectTimeout));
    }

    JavaHttpOpenAiCompatibleLlmClient(OpenAiCompatibleHttpTransport transport) {
        this.transport = transport;
    }

    @Override
    public OpenAiCompatibleClientResponse complete(OpenAiCompatibleChatCompletionRequest request) {
        return ObservedModelCall.execute(observer,request.uri(),request.headers(),request.body().getBytes(java.nio.charset.StandardCharsets.UTF_8),true,()->transport.send(request));
    }
}
