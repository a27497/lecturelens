package com.example.courselingo.qa.controller;

import com.example.courselingo.common.response.ApiResponse;
import com.example.courselingo.qa.dto.CourseQaAskRequest;
import com.example.courselingo.qa.dto.CourseQaResponse;
import com.example.courselingo.qa.service.CourseQaService;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tasks")
public class CourseQaController {

    private final CourseQaService courseQaService;

    public CourseQaController(CourseQaService courseQaService) {
        this.courseQaService = courseQaService;
    }

    @PostMapping("/{taskId}/qa")
    public ApiResponse<CourseQaResponse> ask(
        @PathVariable String taskId,
        @RequestHeader(value = "Authorization", required = false) String authorizationHeader,
        @RequestBody CourseQaAskRequest request
    ) {
        return ApiResponse.success(courseQaService.ask(taskId, authorizationHeader, request));
    }
}
