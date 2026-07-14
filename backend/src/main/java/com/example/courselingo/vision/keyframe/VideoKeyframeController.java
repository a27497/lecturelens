package com.example.courselingo.vision.keyframe;

import com.example.courselingo.common.response.ApiResponse;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.core.io.InputStreamResource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class VideoKeyframeController {

    private final VideoKeyframeService videoKeyframeService;

    public VideoKeyframeController(VideoKeyframeService videoKeyframeService) {
        this.videoKeyframeService = videoKeyframeService;
    }

    @GetMapping("/api/tasks/{taskId}/keyframes")
    public ApiResponse<List<VideoKeyframeView>> list(
        @RequestHeader(value = "Authorization", required = false) String authorizationHeader,
        @PathVariable String taskId
    ) {
        return ApiResponse.success(videoKeyframeService.listKeyframes(authorizationHeader, taskId));
    }

    @GetMapping("/api/tasks/{taskId}/keyframes/{frameId}/image")
    public ResponseEntity<InputStreamResource> image(
        @RequestHeader(value = "Authorization", required = false) String authorizationHeader,
        @PathVariable String taskId,
        @PathVariable Long frameId
    ) {
        VideoKeyframeImage response = videoKeyframeService.downloadKeyframeImage(authorizationHeader, taskId, frameId);
        InputStream inputStream = response.inputStream();
        return ResponseEntity.ok()
            .contentType(MediaType.parseMediaType(response.contentType()))
            .contentLength(response.sizeBytes())
            .header(HttpHeaders.CONTENT_DISPOSITION, contentDisposition(response.fileName()))
            .body(new InputStreamResource(inputStream));
    }

    private static String contentDisposition(String fileName) {
        return ContentDisposition.inline()
            .filename(fileName, StandardCharsets.UTF_8)
            .build()
            .toString();
    }
}
