package com.example.courselingo.artifact.controller;

import com.example.courselingo.artifact.service.ArtifactFileDownloadResponse;
import com.example.courselingo.artifact.service.ArtifactFileDownloadService;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.InputStreamResource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ArtifactFileDownloadController {

    private final ArtifactFileDownloadService artifactFileDownloadService;

    public ArtifactFileDownloadController(ArtifactFileDownloadService artifactFileDownloadService) {
        this.artifactFileDownloadService = artifactFileDownloadService;
    }

    @GetMapping("/api/tasks/{taskId}/artifacts/{artifactType}/{language}/download")
    public ResponseEntity<InputStreamResource> download(
        @RequestHeader(value = "Authorization", required = false) String authorizationHeader,
        @PathVariable String taskId,
        @PathVariable String artifactType,
        @PathVariable String language
    ) {
        ArtifactFileDownloadResponse response = artifactFileDownloadService.download(
            authorizationHeader,
            taskId,
            artifactType,
            language
        );
        InputStream inputStream = response.inputStream();
        return ResponseEntity.ok()
            .contentType(MediaType.parseMediaType(response.contentType()))
            .contentLength(response.sizeBytes())
            .header(HttpHeaders.CONTENT_DISPOSITION, contentDisposition(response.fileName()))
            .body(new InputStreamResource(inputStream));
    }

    private static String contentDisposition(String fileName) {
        return ContentDisposition.inline()
            .filename(fileName, StandardCharsets.UTF_8)
            .build()
            .toString();
    }
}
