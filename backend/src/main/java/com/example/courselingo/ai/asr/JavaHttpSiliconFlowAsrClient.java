package com.example.courselingo.ai.asr;

import java.io.IOException;
import java.time.Duration;

public class JavaHttpSiliconFlowAsrClient implements SiliconFlowAsrClient {

    private final SiliconFlowHttpTransport transport;

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

        return transport.send(new SiliconFlowHttpRequest(
            request.uri(),
            request.headers(),
            multipart.contentType(),
            multipart.body(),
            request.timeout()
        ));
    }
}
