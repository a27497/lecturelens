package com.example.courselingo.chapter.controller;

import com.example.courselingo.chapter.dto.CourseChapterResponse;
import com.example.courselingo.chapter.service.CourseChapterService;
import com.example.courselingo.common.response.ApiResponse;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tasks")
public class CourseChapterController {

    private final CourseChapterService courseChapterService;

    public CourseChapterController(CourseChapterService courseChapterService) {
        this.courseChapterService = courseChapterService;
    }

    @GetMapping("/{taskId}/chapters")
    public ApiResponse<List<CourseChapterResponse>> list(
        @PathVariable String taskId,
        @RequestHeader(value = "Authorization", required = false) String authorizationHeader
    ) {
        return ApiResponse.success(courseChapterService.list(taskId, authorizationHeader));
    }

    @PostMapping("/{taskId}/chapters/generate")
    public ApiResponse<List<CourseChapterResponse>> generate(
        @PathVariable String taskId,
        @RequestHeader(value = "Authorization", required = false) String authorizationHeader
    ) {
        return ApiResponse.success(courseChapterService.generate(taskId, authorizationHeader));
    }
}
