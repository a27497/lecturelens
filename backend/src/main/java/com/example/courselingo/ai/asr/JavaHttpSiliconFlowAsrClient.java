package com.example.courselingo.ai.asr;

import java.io.IOException;
import java.time.Duration;

public class JavaHttpSiliconFlowAsrClient implements SiliconFlowAsrClient {

    private final SiliconFlowHttpTransport transport;
    private com.example.courselingo.ai.llm.ModelCallObserver observer=com.example.courselingo.ai.llm.ModelCallObserver.NOOP;
    public JavaHttpSiliconFlowAsrClient observed(com.example.courselingo.ai.llm.ModelCallObserver value){observer=value;return this;}

    public JavaHttpSiliconFlowAsrClient(Duration connectTimeout) {
        this(new DefaultSiliconFlowHttpTransport(connectTimeout));
    }

    JavaHttpSiliconFlowAsrClient(SiliconFlowHttpTransport transport) {
        this.transport = transport;
    }

    @Override
    public SiliconFlowAsrClientResponse transcribe(SiliconFlowAsrClientRequest request) {
        MultipartFormDataBuilder multipart = new MultipartFormDataBuilder();
        request.formFields().forEach(multipart::field);
        try {
            multipart.file(request.fileFieldName(), request.audioFile());
        } catch (IOException exception) {
            throw new SiliconFlowAsrException("audio file cannot be read for ASR upload", false, exception);
        }

        var wire=new SiliconFlowHttpRequest(
            request.uri(),
            request.headers(),
            multipart.contentType(),
            multipart.body(),
            request.timeout()
        );
        var observed=com.example.courselingo.ai.llm.ObservedModelCall.execute(observer,wire.uri(),wire.headers(),wire.body(),false,()->{
            var r=transport.send(wire);return new com.example.courselingo.ai.llm.OpenAiCompatibleClientResponse(r.statusCode(),r.body(),r.headers(),r.duration());
        });
        return new SiliconFlowAsrClientResponse(observed.statusCode(),observed.body(),observed.headers(),observed.duration());
    }
}
