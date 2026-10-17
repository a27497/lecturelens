package com.example.courselingo.task.controller;

import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.response.ApiResponse;
import com.example.courselingo.task.service.PipelineResumeService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/tasks")
public class TaskResumeController {
    public record Request(@NotNull @Min(1) Long expectedExecutionEpoch) {}
    private final CurrentUserService users;
    private final PipelineResumeService resumes;
    public TaskResumeController(CurrentUserService users,PipelineResumeService resumes){this.users=users;this.resumes=resumes;}
    @PostMapping("/{taskId}/resume")
    public ApiResponse<PipelineResumeService.Result> resume(@PathVariable String taskId,
        @RequestHeader(value="Authorization",required=false)String authorization,@Valid @RequestBody Request request) {
        return ApiResponse.success(resumes.resume(taskId,users.currentUser(authorization).userId(),request.expectedExecutionEpoch()));
    }
}
