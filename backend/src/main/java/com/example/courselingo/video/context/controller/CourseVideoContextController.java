package com.example.courselingo.video.context.controller;

import com.example.courselingo.common.response.ApiResponse;
import com.example.courselingo.video.context.dto.CourseVideoContextRebuildResponse;
import com.example.courselingo.video.context.dto.CourseVideoContextResponse;
import com.example.courselingo.video.context.service.CourseVideoContextService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tasks")
public class CourseVideoContextController {

    private final CourseVideoContextService courseVideoContextService;

    public CourseVideoContextController(CourseVideoContextService courseVideoContextService) {
        this.courseVideoContextService = courseVideoContextService;
    }

    @GetMapping("/{taskId}/video-context")
    public ApiResponse<CourseVideoContextResponse> get(
        @PathVariable String taskId,
        @RequestHeader(value = "Authorization", required = false) String authorizationHeader
    ) {
        return ApiResponse.success(courseVideoContextService.get(taskId, authorizationHeader));
    }

    @PostMapping("/{taskId}/video-context/rebuild")
    public ApiResponse<CourseVideoContextRebuildResponse> rebuild(
        @PathVariable String taskId,
        @RequestHeader(value = "Authorization", required = false) String authorizationHeader
    ) {
        return ApiResponse.success(courseVideoContextService.rebuild(taskId, authorizationHeader));
    }
}
