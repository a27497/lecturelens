package com.example.courselingo.qa.controller;

import com.example.courselingo.common.response.ApiResponse;
import com.example.courselingo.qa.dto.CourseQaHistoryPage;
import com.example.courselingo.qa.service.CourseQaHistoryService;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/tasks")
public class CourseQaHistoryController {
    private final CourseQaHistoryService history;
    public CourseQaHistoryController(CourseQaHistoryService history) { this.history = history; }
    @GetMapping("/{taskId}/qa/history")
    public ApiResponse<CourseQaHistoryPage> read(@PathVariable String taskId,
            @RequestHeader(value="Authorization", required=false) String authorization,
            @RequestParam(required=false) Long before,
            @RequestParam(defaultValue="20") int limit) {
        return ApiResponse.success(history.read(taskId, authorization, before, limit));
    }
}
