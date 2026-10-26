package com.example.courselingo.storage;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import io.minio.MinioClient;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class MinioSdkCompatibilityTest {
    @TempDir Path directory;

    @Test
    void actualSdkSupportsRegionLookupMultipartAndObjectOperationsWithPinnedHttpClient() throws Exception {
        List<String> requests = new CopyOnWriteArrayList<>();
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", exchange -> respond(exchange, requests));
        server.start();
        String endpoint = "http://127.0.0.1:" + server.getAddress().getPort();
        try (MinioClient client = MinioClient.builder().endpoint(endpoint)
                .credentials("synthetic-access", "synthetic-secret").build()) {
            var service = new MinioStorageService(client,
                new MinioStorageProperties(endpoint, "synthetic-access", "synthetic-secret", "test-bucket", ""),
                new StorageObjectKeyValidator());
            Path source = directory.resolve("synthetic.mp4");
            Files.write(source, new byte[6 * 1024 * 1024]);
            service.putObject("synthetic.mp4", source, Files.size(source), "video/mp4");
            assertThat(service.objectExists("synthetic.mp4")).isTrue();
            try (var input = service.openObject("synthetic.mp4")) {
                assertThat(new String(input.readAllBytes(), StandardCharsets.UTF_8)).isEqualTo("synthetic-object");
            }
            service.deleteObject("synthetic.mp4");
            assertThatThrownBy(() -> service.openObject("missing.mp4"))
                .isInstanceOf(com.example.courselingo.common.exception.BusinessException.class);
            assertThat(requests).anyMatch(s -> s.startsWith("GET ") && s.contains("location"));
            assertThat(requests).anyMatch(s -> s.startsWith("POST ") && s.contains("uploads"));
            assertThat(requests.stream().filter(s -> s.startsWith("PUT ") && s.contains("partNumber")).count())
                .isEqualTo(2);
            assertThat(requests).anyMatch(s -> s.startsWith("DELETE "));
        } finally {
            server.stop(0);
        }
    }

    private void respond(HttpExchange exchange, List<String> requests) throws IOException {
        try (exchange) {
            String query = exchange.getRequestURI().getRawQuery();
            String method = exchange.getRequestMethod();
            requests.add(method + " " + exchange.getRequestURI());
            exchange.getRequestBody().transferTo(OutputStream.nullOutputStream());
            exchange.getResponseHeaders().set("Content-Type", "application/xml");
            exchange.getResponseHeaders().set("ETag", "\"synthetic-etag\"");
            exchange.getResponseHeaders().set("Last-Modified", "Mon, 26 Oct 2026 00:00:00 GMT");
            String body;
            int status = 200;
            if (query != null && query.contains("location")) {
                body = "<LocationConstraint xmlns=\"http://s3.amazonaws.com/doc/2006-03-01/\">us-east-1</LocationConstraint>";
            } else if ("POST".equals(method) && query != null && query.contains("uploads")) {
                body = "<InitiateMultipartUploadResult><Bucket>test-bucket</Bucket>"
                    + "<Key>synthetic.mp4</Key><UploadId>synthetic-upload</UploadId></InitiateMultipartUploadResult>";
            } else if ("POST".equals(method)) {
                body = "<CompleteMultipartUploadResult><Location>http://localhost/</Location>"
                    + "<Bucket>test-bucket</Bucket><Key>synthetic.mp4</Key><ETag>synthetic-etag</ETag>"
                    + "</CompleteMultipartUploadResult>";
            } else if (exchange.getRequestURI().getPath().endsWith("missing.mp4")) {
                status = 404;
                body = "<Error><Code>NoSuchKey</Code><Message>synthetic missing</Message>"
                    + "<Resource>/test-bucket/missing.mp4</Resource><RequestId>synthetic</RequestId></Error>";
            } else body = "synthetic-object";
            if ("HEAD".equals(method) || "DELETE".equals(method) || "PUT".equals(method)) {
                exchange.sendResponseHeaders("DELETE".equals(method) ? 204 : status, -1);
            } else {
                byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(status, bytes.length);
                exchange.getResponseBody().write(bytes);
            }
        }
    }
}
