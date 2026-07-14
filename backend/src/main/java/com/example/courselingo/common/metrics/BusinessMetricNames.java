package com.example.courselingo.common.metrics;

public final class BusinessMetricNames {

    public static final String TASK_CREATED_TOTAL = "courselingo.task.created.total";
    public static final String TASK_STATE_TRANSITION_TOTAL = "courselingo.task.state.transition.total";
    public static final String TASK_RUNNER_TOTAL = "courselingo.task.runner.total";
    public static final String TASK_RUNNER_DURATION = "courselingo.task.runner.duration";
    public static final String MQ_PRODUCE_TOTAL = "courselingo.mq.produce.total";
    public static final String MQ_CONSUME_TOTAL = "courselingo.mq.consume.total";
    public static final String UPLOAD_SESSION_CREATED_TOTAL = "courselingo.upload.session.created.total";
    public static final String UPLOAD_CHUNK_RECEIVED_TOTAL = "courselingo.upload.chunk.received.total";
    public static final String UPLOAD_COMPLETED_TOTAL = "courselingo.upload.completed.total";
    public static final String ARTIFACT_SAVED_TOTAL = "courselingo.artifact.saved.total";
    public static final String ARTIFACT_BYTES = "courselingo.artifact.bytes";

    private BusinessMetricNames() {
    }
}
