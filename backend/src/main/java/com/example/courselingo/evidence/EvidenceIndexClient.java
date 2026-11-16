package com.example.courselingo.evidence;

import java.util.List;

/** Publishes an authoritative evidence snapshot or deletion to the derived index. */
public interface EvidenceIndexClient {
    boolean enabled();

    /** Returns the acknowledged index version for this revision and sequence. */
    String sync(String taskId, Long ownerId, long revision, long sequence,
                List<CourseEvidence> evidence, boolean deleted) throws Exception;
}
