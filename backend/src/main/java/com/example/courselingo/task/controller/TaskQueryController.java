package com.example.courselingo.task.controller;

import com.example.courselingo.common.response.ApiResponse;
import com.example.courselingo.task.dto.TaskDetailResponse;
import com.example.courselingo.task.dto.TaskListQuery;
import com.example.courselingo.task.dto.TaskListResponse;
import com.example.courselingo.task.service.TaskQueryService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tasks")
public class TaskQueryController {

    private final TaskQueryService taskQueryService;

    public TaskQueryController(TaskQueryService taskQueryService) {
        this.taskQueryService = taskQueryService;
    }

    @GetMapping
    public ApiResponse<TaskListResponse> list(
        @RequestParam(value = "status", required = false) String status,
        @RequestParam(value = "page", required = false) Integer page,
        @RequestParam(value = "pageSize", required = false) Integer pageSize,
        @RequestHeader(value = "Authorization", required = false) String authorizationHeader
    ) {
        return ApiResponse.success(taskQueryService.list(new TaskListQuery(status, page, pageSize), authorizationHeader));
    }

    @GetMapping("/{taskId}")
    public ApiResponse<TaskDetailResponse> detail(
        @PathVariable String taskId,
        @RequestHeader(value = "Authorization", required = false) String authorizationHeader
    ) {
        return ApiResponse.success(taskQueryService.detail(taskId, authorizationHeader));
    }
}
