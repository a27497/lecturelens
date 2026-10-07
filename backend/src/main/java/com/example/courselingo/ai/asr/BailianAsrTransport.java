package com.example.courselingo.ai.asr;

import java.net.URI;
import java.time.Duration;

interface BailianAsrTransport {
    Response send(URI endpoint, String credential, byte[] body, Duration timeout);

    record Response(int statusCode, String body) {
        @Override
        public String toString() { return "BailianAsrResponse[statusCode=" + statusCode + "]"; }
    }
}
