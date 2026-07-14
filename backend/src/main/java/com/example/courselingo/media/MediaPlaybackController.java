package com.example.courselingo.media;

import com.example.courselingo.common.response.ApiResponse;
import java.io.InputStream;
import org.springframework.core.io.InputStreamResource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MediaPlaybackController {

    private final MediaPlaybackService mediaPlaybackService;

    public MediaPlaybackController(MediaPlaybackService mediaPlaybackService) {
        this.mediaPlaybackService = mediaPlaybackService;
    }

    @PostMapping("/api/uploads/{uploadId}/playback-token")
    public ApiResponse<PlaybackTokenResponse> uploadPlaybackToken(
        @RequestHeader(value = "Authorization", required = false) String authorizationHeader,
        @PathVariable String uploadId
    ) {
        return ApiResponse.success(mediaPlaybackService.requestUploadPlaybackToken(authorizationHeader, uploadId));
    }

    @PostMapping("/api/tasks/{taskId}/playback-token")
    public ApiResponse<PlaybackTokenResponse> taskPlaybackToken(
        @RequestHeader(value = "Authorization", required = false) String authorizationHeader,
        @PathVariable String taskId
    ) {
        return ApiResponse.success(mediaPlaybackService.requestTaskPlaybackToken(authorizationHeader, taskId));
    }

    @GetMapping("/api/media/uploads/{uploadId}/stream")
    public ResponseEntity<InputStreamResource> stream(
        @PathVariable String uploadId,
        @RequestParam(value = "token", required = false) String token,
        @RequestHeader(value = "Range", required = false) String rangeHeader
    ) {
        MediaStreamResponse response = mediaPlaybackService.stream(uploadId, token, rangeHeader);
        InputStream inputStream = response.inputStream();
        ResponseEntity.BodyBuilder builder = ResponseEntity.status(response.status())
            .header(HttpHeaders.ACCEPT_RANGES, "bytes")
            .header(HttpHeaders.CONTENT_DISPOSITION, "inline")
            .contentType(MediaType.parseMediaType(response.contentType()))
            .contentLength(response.contentLength());
        if (response.contentRange() != null) {
            builder.header(HttpHeaders.CONTENT_RANGE, response.contentRange());
        }
        return builder.body(new InputStreamResource(inputStream));
    }

    @ExceptionHandler(MediaRangeNotSatisfiableException.class)
    public ResponseEntity<ApiResponse<Void>> handleRangeNotSatisfiable(MediaRangeNotSatisfiableException exception) {
        return ResponseEntity.status(HttpStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            .header(HttpHeaders.ACCEPT_RANGES, "bytes")
            .header(HttpHeaders.CONTENT_RANGE, "bytes */" + exception.sizeBytes())
            .body(ApiResponse.failure(exception.errorCode().code(), exception.getMessage()));
    }
}
