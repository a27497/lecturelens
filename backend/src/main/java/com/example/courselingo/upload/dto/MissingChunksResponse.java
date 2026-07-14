package com.example.courselingo.upload.dto;

import java.util.List;

public record MissingChunksResponse(
    String uploadId,
    Integer totalChunks,
    List<Integer> uploadedChunks,
    List<Integer> missingChunks,
    Boolean allUploaded,
    String status
) {
}
