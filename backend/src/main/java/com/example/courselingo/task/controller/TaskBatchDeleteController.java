package com.example.courselingo.task.controller;

import com.example.courselingo.common.response.ApiResponse;
import com.example.courselingo.task.dto.TaskBatchDeleteRequest;
import com.example.courselingo.task.dto.TaskBatchDeleteResponse;
import com.example.courselingo.task.service.TaskBatchDeleteService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tasks")
public class TaskBatchDeleteController {

    private final TaskBatchDeleteService taskBatchDeleteService;

    public TaskBatchDeleteController(TaskBatchDeleteService taskBatchDeleteService) {
        this.taskBatchDeleteService = taskBatchDeleteService;
    }

    @PostMapping("/batch-delete")
    public ApiResponse<TaskBatchDeleteResponse> batchDelete(
        @Valid @RequestBody TaskBatchDeleteRequest request,
        @RequestHeader(value = "Authorization", required = false) String authorizationHeader
    ) {
        return ApiResponse.success(taskBatchDeleteService.delete(request, authorizationHeader));
    }
}
