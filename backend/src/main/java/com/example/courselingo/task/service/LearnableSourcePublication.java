package com.example.courselingo.task.service;

/**
 * Publication of derived sources (translation, OCR, visual analysis) that arrive after a running course
 * already opened learning. Implementations extend the evidence of the current revision in place when the
 * change is purely additive, so study sessions bound to that revision stay valid; any other change still
 * advances the revision.
 */
public interface LearnableSourcePublication {
    /**
     * Called inside the source writer's transaction, with the task row locked. Returns true when the
     * revision decision is deferred to commit time; false when the caller must advance the revision now.
     */
    boolean deferIfLearnable(String taskId, Long userId);
}
