package com.example.courselingo.task.service;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class PipelineCheckpointDeletion {
    private final JdbcTemplate jdbc;
    public PipelineCheckpointDeletion(JdbcTemplate jdbc){this.jdbc=jdbc;}
    /** Called only after authorized logical deletion, inside the cleanup outbox transaction. */
    public void clearDeleted(String task,long user) {
        if(jdbc.queryForList("SELECT id FROM analysis_task WHERE id=? AND user_id=? AND deleted_at IS NOT NULL FOR UPDATE",task,user).isEmpty())return;
        for(String table:java.util.List.of("model_call_attempt","translation_batch","translation_plan","pipeline_step_checkpoint",
            "translation_scheduler_event","translation_scheduler_state","transcript_paragraph","transcript_timing_plan",
            "transcript_alignment_publication","pipeline_policy_snapshot"))jdbc.update("DELETE FROM "+table+" WHERE task_id=?",task);
    }
}
