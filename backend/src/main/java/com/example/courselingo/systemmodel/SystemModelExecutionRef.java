package com.example.courselingo.systemmodel;

public record SystemModelExecutionRef(
        String snapshotId, long configVersion, String taskId, long userId) {}
