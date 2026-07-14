package com.example.courselingo.upload.service;

import java.util.List;
import java.util.Optional;

public interface UploadChunkStateService {

    void markUploaded(String uploadId, int chunkIndex);

    Optional<List<Integer>> findUploadedChunks(String uploadId, int totalChunks);

    void clear(String uploadId);
}
