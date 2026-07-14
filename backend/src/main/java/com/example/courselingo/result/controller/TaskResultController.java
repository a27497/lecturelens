package com.example.courselingo.result.controller;

import com.example.courselingo.common.response.ApiResponse;
import com.example.courselingo.result.dto.TaskResultResponse;
import com.example.courselingo.result.service.TaskResultService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tasks")
public class TaskResultController {

    private final TaskResultService taskResultService;

    public TaskResultController(TaskResultService taskResultService) {
        this.taskResultService = taskResultService;
    }

    @GetMapping("/{taskId}/results")
    public ApiResponse<TaskResultResponse> getResult(
        @PathVariable String taskId,
        @RequestHeader(value = "Authorization", required = false) String authorizationHeader
    ) {
        return ApiResponse.success(taskResultService.getResult(taskId, authorizationHeader));
    }
}
