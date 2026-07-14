package com.example.courselingo.task.claim;

public interface TaskClaimService {

    TaskClaimResult tryAcquire(String taskId, String requestId);

    boolean refresh(String taskId, String requestId);

    void release(String taskId, String requestId);
}
