package com.example.courselingo.task.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateAnalysisTaskRequest(
    @NotBlank(message = "uploadId cannot be blank")
    @Size(max = 64, message = "uploadId length cannot exceed 64")
    String uploadId,

    @NotBlank(message = "targetLanguage cannot be blank")
    @Size(max = 32, message = "targetLanguage length cannot exceed 32")
    String targetLanguage
) {
}
