package com.example.courselingo.task.controller;

import com.example.courselingo.common.response.ApiResponse;
import com.example.courselingo.task.dto.CreateAnalysisTaskRequest;
import com.example.courselingo.task.dto.CreateAnalysisTaskResponse;
import com.example.courselingo.task.service.TaskCreationService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tasks")
public class TaskController {

    private final TaskCreationService taskCreationService;

    public TaskController(TaskCreationService taskCreationService) {
        this.taskCreationService = taskCreationService;
    }

    @PostMapping
    public ApiResponse<CreateAnalysisTaskResponse> create(
        @Valid @RequestBody CreateAnalysisTaskRequest request,
        @RequestHeader(value = "Authorization", required = false) String authorizationHeader
    ) {
        return ApiResponse.success(taskCreationService.create(request, authorizationHeader));
    }
}
