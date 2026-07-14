package com.example.courselingo.task.progress;

import java.util.Optional;

public interface TaskProgressSnapshotService {

    void save(TaskProgressSnapshot snapshot);

    Optional<TaskProgressSnapshot> find(String taskId);

    void delete(String taskId);
}
