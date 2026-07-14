package com.example.courselingo.task.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;

public record TaskBatchDeleteRequest(
    @NotNull
    @Size(min = 1, max = 100)
    List<@NotBlank @Size(max = 64) String> taskIds
) {
}
