package com.example.courselingo.fusion;

@FunctionalInterface
public interface VideoSegmentFusionService {

    VideoSegmentFusionResult fuse(String taskId, Long userId);
}
