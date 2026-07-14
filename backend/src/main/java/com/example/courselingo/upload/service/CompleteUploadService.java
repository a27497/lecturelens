package com.example.courselingo.upload.service;

import com.example.courselingo.upload.dto.CompleteUploadResponse;

public interface CompleteUploadService {

    CompleteUploadResponse complete(String authorizationHeader, String uploadId);
}
