package com.example.courselingo.upload.service;

import com.example.courselingo.upload.dto.CreateUploadSessionRequest;
import com.example.courselingo.upload.dto.CreateUploadSessionResponse;

public interface UploadSessionService {

    CreateUploadSessionResponse create(String authorizationHeader, CreateUploadSessionRequest request);
}
