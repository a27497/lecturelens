package com.example.courselingo.upload.dto;

public record UploadChunkResponse(
    String uploadId,
    Integer chunkIndex,
    Boolean uploaded,
    String status
) {
}
