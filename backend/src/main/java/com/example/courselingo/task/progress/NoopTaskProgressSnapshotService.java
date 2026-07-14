package com.example.courselingo.task.progress;

import java.util.Optional;

public class NoopTaskProgressSnapshotService implements TaskProgressSnapshotService {

    @Override
    public void save(TaskProgressSnapshot snapshot) {
        // Redis task progress snapshots are disabled.
    }

    @Override
    public Optional<TaskProgressSnapshot> find(String taskId) {
        return Optional.empty();
    }

    @Override
    public void delete(String taskId) {
        // Redis task progress snapshots are disabled.
    }
}
