package com.example.courselingo.upload.service;

import com.example.courselingo.upload.dto.UploadChunkResponse;
import org.springframework.web.multipart.MultipartFile;

public interface UploadChunkService {

    UploadChunkResponse upload(
        String authorizationHeader,
        String uploadId,
        Integer chunkIndex,
        MultipartFile file
    );
}
