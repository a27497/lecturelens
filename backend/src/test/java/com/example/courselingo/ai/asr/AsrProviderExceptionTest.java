package com.example.courselingo.ai.asr;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.net.URI;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Map;
import org.junit.jupiter.api.Test;

class AsrProviderExceptionTest {
    @Test
    void compatibilityTypePreservesClassificationButDropsUnsafeCauseChain() {
        var exception = new SiliconFlowAsrException("Authorization: Bearer fake-credential\n"
            + "data:audio/wav;base64,AAAA", true, 429, new IOException("raw-credential-without-label"));
        AsrProviderException generic = exception;
        assertThat(generic.retryable()).isTrue();
        assertThat(generic.statusCode()).contains(429);
        StringWriter output = new StringWriter();
        exception.printStackTrace(new PrintWriter(output));
        assertThat(output.toString()).doesNotContain("fake-credential", "raw-credential", "AAAA", "Authorization");
        assertThat(generic.getCause()).isNull();
        assertThat(new AsrProviderException("invalid response", false).statusCode()).isEmpty();
    }

    @Test
    void wireObjectsDoNotRenderCredentialsOrBodies() {
        var request = new SiliconFlowAsrClientRequest(URI.create("https://example.com"),
            Map.of("Authorization", "Bearer fake-credential"), Path.of("/private/audio"), "file", Map.of(), Duration.ofSeconds(1));
        var response = new SiliconFlowAsrClientResponse(401, "raw-credential", Map.of(), Duration.ZERO);
        var http = new SiliconFlowHttpRequest(request.uri(), request.headers(), "application/json",
            "data:audio/wav;base64,AAAA".getBytes(), request.timeout());
        var bailian = new BailianAsrTransport.Response(401, "raw-credential");
        for (Object value : new Object[] {request, response, http, bailian}) {
            assertThat(value.toString()).doesNotContain("credential", "Authorization", "AAAA", "/private/audio");
        }
    }
}
