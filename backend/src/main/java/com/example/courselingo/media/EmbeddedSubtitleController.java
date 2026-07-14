package com.example.courselingo.media;

import com.example.courselingo.common.response.ApiResponse;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class EmbeddedSubtitleController {

    private final EmbeddedSubtitleService embeddedSubtitleService;

    public EmbeddedSubtitleController(EmbeddedSubtitleService embeddedSubtitleService) {
        this.embeddedSubtitleService = embeddedSubtitleService;
    }

    @GetMapping("/api/uploads/{uploadId}/embedded-subtitles")
    public ApiResponse<EmbeddedSubtitleProbeResponse> probeUpload(
        @RequestHeader(value = "Authorization", required = false) String authorizationHeader,
        @PathVariable String uploadId
    ) {
        return ApiResponse.success(embeddedSubtitleService.probeUpload(authorizationHeader, uploadId));
    }

    @GetMapping("/api/uploads/{uploadId}/embedded-subtitles/{streamIndex}/download")
    public ResponseEntity<byte[]> downloadUpload(
        @RequestHeader(value = "Authorization", required = false) String authorizationHeader,
        @PathVariable String uploadId,
        @PathVariable int streamIndex
    ) {
        return vttResponse(embeddedSubtitleService.downloadUpload(authorizationHeader, uploadId, streamIndex));
    }

    @GetMapping("/api/tasks/{taskId}/embedded-subtitles")
    public ApiResponse<EmbeddedSubtitleProbeResponse> probeTask(
        @RequestHeader(value = "Authorization", required = false) String authorizationHeader,
        @PathVariable String taskId
    ) {
        return ApiResponse.success(embeddedSubtitleService.probeTask(authorizationHeader, taskId));
    }

    @GetMapping("/api/tasks/{taskId}/embedded-subtitles/{streamIndex}/download")
    public ResponseEntity<byte[]> downloadTask(
        @RequestHeader(value = "Authorization", required = false) String authorizationHeader,
        @PathVariable String taskId,
        @PathVariable int streamIndex
    ) {
        return vttResponse(embeddedSubtitleService.downloadTask(authorizationHeader, taskId, streamIndex));
    }

    private ResponseEntity<byte[]> vttResponse(EmbeddedSubtitleFileResponse response) {
        return ResponseEntity.ok()
            .contentType(MediaType.parseMediaType(response.contentType()))
            .header(HttpHeaders.CONTENT_DISPOSITION, "inline; filename=\"" + response.filename() + "\"")
            .body(response.bytes());
    }
}
