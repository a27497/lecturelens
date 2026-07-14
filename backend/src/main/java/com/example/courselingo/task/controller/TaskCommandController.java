package com.example.courselingo.task.controller;

import com.example.courselingo.common.response.ApiResponse;
import com.example.courselingo.task.dto.TaskCommandResponse;
import com.example.courselingo.task.dto.TaskRetryResponse;
import com.example.courselingo.task.service.TaskCommandService;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tasks")
public class TaskCommandController {

    private final TaskCommandService taskCommandService;

    public TaskCommandController(TaskCommandService taskCommandService) {
        this.taskCommandService = taskCommandService;
    }

    @PostMapping("/{taskId}/retry")
    public ApiResponse<TaskRetryResponse> retry(
        @PathVariable String taskId,
        @RequestHeader(value = "Authorization", required = false) String authorizationHeader
    ) {
        return ApiResponse.success(taskCommandService.retry(taskId, authorizationHeader));
    }

    @PostMapping("/{taskId}/cancel")
    public ApiResponse<TaskCommandResponse> cancel(
        @PathVariable String taskId,
        @RequestHeader(value = "Authorization", required = false) String authorizationHeader
    ) {
        return ApiResponse.success(taskCommandService.cancel(taskId, authorizationHeader));
    }
}
