package com.example.courselingo.task.runner;

record VisionPipelineBranchResult(Status status, Throwable failure) {

    enum Status {
        SUCCEEDED,
        FAILED,
        TIMED_OUT,
        CANCELLED
    }

    static VisionPipelineBranchResult succeeded() {
        return new VisionPipelineBranchResult(Status.SUCCEEDED, null);
    }

    static VisionPipelineBranchResult failed(Throwable failure) {
        return new VisionPipelineBranchResult(Status.FAILED, failure);
    }

    static VisionPipelineBranchResult timedOut(Throwable failure) {
        return new VisionPipelineBranchResult(Status.TIMED_OUT, failure);
    }

    static VisionPipelineBranchResult cancelled(Throwable failure) {
        return new VisionPipelineBranchResult(Status.CANCELLED, failure);
    }

    boolean isSucceeded() {
        return status == Status.SUCCEEDED;
    }
}
