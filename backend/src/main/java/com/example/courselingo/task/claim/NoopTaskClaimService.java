package com.example.courselingo.task.claim;

public class NoopTaskClaimService implements TaskClaimService {

    @Override
    public TaskClaimResult tryAcquire(String taskId, String requestId) {
        return TaskClaimResult.acquiredResult();
    }

    @Override
    public boolean refresh(String taskId, String requestId) {
        return true;
    }

    @Override
    public void release(String taskId, String requestId) {
        // Redis task claim is disabled.
    }
}
