package com.example.courselingo.ai.asr;

import java.net.URI;
import java.time.Duration;

interface BailianAsrTransport {
    Response send(URI endpoint, String credential, byte[] body, Duration timeout);

    record Response(int statusCode, String body,long retryAfterMillis) {
        Response(int statusCode,String body){this(statusCode,body,0);}
        @Override
        public String toString() { return "BailianAsrResponse[statusCode=" + statusCode + "]"; }
    }
}
