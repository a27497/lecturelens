package com.example.courselingo.task.claim;

public final class TaskClaimResult {

    private static final TaskClaimResult ACQUIRED = new TaskClaimResult(true);
    private static final TaskClaimResult REJECTED = new TaskClaimResult(false);

    private final boolean acquired;

    private TaskClaimResult(boolean acquired) {
        this.acquired = acquired;
    }

    public static TaskClaimResult acquiredResult() {
        return ACQUIRED;
    }

    public static TaskClaimResult rejectedResult() {
        return REJECTED;
    }

    public boolean acquired() {
        return acquired;
    }
}
