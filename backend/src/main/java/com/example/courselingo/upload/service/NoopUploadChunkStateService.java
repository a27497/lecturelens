package com.example.courselingo.upload.service;

import java.util.List;
import java.util.Optional;

public class NoopUploadChunkStateService implements UploadChunkStateService {

    @Override
    public void markUploaded(String uploadId, int chunkIndex) {
        // Redis chunk state is disabled.
    }

    @Override
    public Optional<List<Integer>> findUploadedChunks(String uploadId, int totalChunks) {
        return Optional.empty();
    }

    @Override
    public void clear(String uploadId) {
        // Redis chunk state is disabled.
    }
}
