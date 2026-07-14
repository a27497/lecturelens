package com.example.courselingo.upload.controller;

import com.example.courselingo.common.response.ApiResponse;
import com.example.courselingo.upload.dto.CompleteUploadResponse;
import com.example.courselingo.upload.dto.CreateUploadSessionRequest;
import com.example.courselingo.upload.dto.CreateUploadSessionResponse;
import com.example.courselingo.upload.dto.MissingChunksResponse;
import com.example.courselingo.upload.dto.UploadChunkResponse;
import com.example.courselingo.upload.service.CompleteUploadService;
import com.example.courselingo.upload.service.MissingChunksService;
import com.example.courselingo.upload.service.UploadChunkService;
import com.example.courselingo.upload.service.UploadSessionService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
public class UploadSessionController {

    private final UploadSessionService uploadSessionService;
    private final UploadChunkService uploadChunkService;
    private final MissingChunksService missingChunksService;
    private final CompleteUploadService completeUploadService;

    public UploadSessionController(
        UploadSessionService uploadSessionService,
        UploadChunkService uploadChunkService,
        MissingChunksService missingChunksService,
        CompleteUploadService completeUploadService
    ) {
        this.uploadSessionService = uploadSessionService;
        this.uploadChunkService = uploadChunkService;
        this.missingChunksService = missingChunksService;
        this.completeUploadService = completeUploadService;
    }

    @PostMapping("/api/uploads/sessions")
    public ApiResponse<CreateUploadSessionResponse> create(
        @RequestHeader(value = "Authorization", required = false) String authorizationHeader,
        @Valid @RequestBody CreateUploadSessionRequest request
    ) {
        return ApiResponse.success(uploadSessionService.create(authorizationHeader, request));
    }

    @PostMapping("/api/uploads/sessions/{uploadId}/chunks/{chunkIndex}")
    public ApiResponse<UploadChunkResponse> uploadChunk(
        @RequestHeader(value = "Authorization", required = false) String authorizationHeader,
        @PathVariable String uploadId,
        @PathVariable Integer chunkIndex,
        @RequestPart(value = "file", required = false) MultipartFile file
    ) {
        return ApiResponse.success(uploadChunkService.upload(authorizationHeader, uploadId, chunkIndex, file));
    }

    @GetMapping("/api/uploads/sessions/{uploadId}/missing-chunks")
    public ApiResponse<MissingChunksResponse> missingChunks(
        @RequestHeader(value = "Authorization", required = false) String authorizationHeader,
        @PathVariable String uploadId
    ) {
        return ApiResponse.success(missingChunksService.findMissingChunks(authorizationHeader, uploadId));
    }

    @PostMapping("/api/uploads/sessions/{uploadId}/complete")
    public ApiResponse<CompleteUploadResponse> complete(
        @RequestHeader(value = "Authorization", required = false) String authorizationHeader,
        @PathVariable String uploadId
    ) {
        return ApiResponse.success(completeUploadService.complete(authorizationHeader, uploadId));
    }
}
