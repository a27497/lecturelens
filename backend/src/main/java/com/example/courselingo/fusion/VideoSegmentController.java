package com.example.courselingo.fusion;

import com.example.courselingo.common.response.ApiResponse;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tasks")
public class VideoSegmentController {

    private final VideoSegmentService videoSegmentService;

    public VideoSegmentController(VideoSegmentService videoSegmentService) {
        this.videoSegmentService = videoSegmentService;
    }

    @GetMapping("/{taskId}/video-segments")
    public ApiResponse<List<VideoSegmentResponse>> listVideoSegments(
        @PathVariable String taskId,
        @RequestHeader(value = "Authorization", required = false) String authorizationHeader,
        @RequestParam(defaultValue = "100") Integer limit,
        @RequestParam(defaultValue = "0") Integer offset,
        @RequestParam(defaultValue = "") String keyword
    ) {
        return ApiResponse.success(videoSegmentService.listForCurrentUser(
            authorizationHeader,
            taskId,
            limit,
            offset,
            keyword
        ));
    }

    @PostMapping("/{taskId}/video-segments/rebuild")
    public ApiResponse<VideoSegmentFusionResult> rebuildVideoSegments(
        @PathVariable String taskId,
        @RequestHeader(value = "Authorization", required = false) String authorizationHeader
    ) {
        return ApiResponse.success(videoSegmentService.rebuildForCurrentUser(authorizationHeader, taskId));
    }
}
