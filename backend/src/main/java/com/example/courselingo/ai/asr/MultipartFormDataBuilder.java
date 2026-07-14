package com.example.courselingo.ai.asr;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

final class MultipartFormDataBuilder {

    private static final byte[] CRLF = "\r\n".getBytes(StandardCharsets.UTF_8);

    private final String boundary = "courselingo-" + UUID.randomUUID();
    private final ByteArrayOutputStream body = new ByteArrayOutputStream();

    MultipartFormDataBuilder field(String name, String value) {
        writeAscii("--" + boundary + "\r\n");
        writeAscii("Content-Disposition: form-data; name=\"" + escape(name) + "\"\r\n\r\n");
        writeUtf8(value == null ? "" : value);
        write(CRLF);
        return this;
    }

    MultipartFormDataBuilder file(String name, Path file) throws IOException {
        String filename = file.getFileName() == null ? "audio" : file.getFileName().toString();
        writeAscii("--" + boundary + "\r\n");
        writeAscii("Content-Disposition: form-data; name=\"" + escape(name) + "\"; filename=\"" + escape(filename) + "\"\r\n");
        writeAscii("Content-Type: application/octet-stream\r\n\r\n");
        write(Files.readAllBytes(file));
        write(CRLF);
        return this;
    }

    String contentType() {
        return "multipart/form-data; boundary=" + boundary;
    }

    byte[] body() {
        ByteArrayOutputStream finalized = new ByteArrayOutputStream();
        try {
            body.writeTo(finalized);
            finalized.write(("--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8));
        } catch (IOException exception) {
            throw new IllegalStateException("multipart body cannot be built", exception);
        }
        return finalized.toByteArray();
    }

    private void writeAscii(String value) {
        write(value.getBytes(StandardCharsets.US_ASCII));
    }

    private void writeUtf8(String value) {
        write(value.getBytes(StandardCharsets.UTF_8));
    }

    private void write(byte[] bytes) {
        try {
            body.write(bytes);
        } catch (IOException exception) {
            throw new IllegalStateException("multipart body cannot be built", exception);
        }
    }

    private static String escape(String value) {
        return value == null ? "" : value.replace("\\", "\\\\").replace("\"", "\\\"");
    }
}
