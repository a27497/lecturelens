package com.example.courselingo.upload.service;

import com.example.courselingo.upload.dto.MissingChunksResponse;

public interface MissingChunksService {

    MissingChunksResponse findMissingChunks(String authorizationHeader, String uploadId);
}
