package com.example.courselingo.upload.dto;

public record CompleteUploadResponse(
    String uploadId,
    String status,
    Long sizeBytes,
    String fileMd5
) {
}
