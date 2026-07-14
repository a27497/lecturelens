package com.example.courselingo.upload.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

public record CreateUploadSessionRequest(
    @NotBlank(message = "filename不能为空")
    @Size(max = 255, message = "filename长度不能超过255")
    String filename,

    @NotNull(message = "sizeBytes不能为空")
    @Positive(message = "sizeBytes必须大于0")
    Long sizeBytes,

    @NotNull(message = "chunkSizeBytes不能为空")
    @Positive(message = "chunkSizeBytes必须大于0")
    Long chunkSizeBytes,

    @NotNull(message = "totalChunks不能为空")
    @Positive(message = "totalChunks必须大于0")
    Integer totalChunks,

    @NotBlank(message = "fileMd5不能为空")
    String fileMd5
) {
}
