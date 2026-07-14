package com.example.courselingo.fusion;

public record VideoSegmentFusionResult(
    int windows,
    int saved,
    int empty,
    int skipped
) {
}
