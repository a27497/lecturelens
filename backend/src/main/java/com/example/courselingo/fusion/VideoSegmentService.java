package com.example.courselingo.fusion;

import java.util.List;

@FunctionalInterface
public interface VideoSegmentService extends VideoSegmentFusionService {

    default VideoSegmentFusionResult rebuildForCurrentUser(String authorizationHeader, String taskId) {
        throw new UnsupportedOperationException("Owner-scoped video segment rebuild is not implemented");
    }

    default List<VideoSegmentResponse> listByTaskId(
        String taskId,
        Long userId,
        Integer limit,
        Integer offset,
        String keyword
    ) {
        throw new UnsupportedOperationException("Video segment query is not implemented");
    }

    default List<VideoSegmentResponse> listForCurrentUser(
        String authorizationHeader,
        String taskId,
        Integer limit,
        Integer offset,
        String keyword
    ) {
        throw new UnsupportedOperationException("Video segment query is not implemented");
    }
}
