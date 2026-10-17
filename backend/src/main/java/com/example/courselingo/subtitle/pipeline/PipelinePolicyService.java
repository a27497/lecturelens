package com.example.courselingo.subtitle.pipeline;

import com.example.courselingo.ai.llm.TranslationFailure;

import com.example.courselingo.subtitle.service.SubtitleTranslationProperties;
import com.example.courselingo.systemmodel.SystemModelExecutionRef;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PostConstruct;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.*;

@Service
@EnableConfigurationProperties(PipelineTranslationProperties.class)
public class PipelinePolicyService {
    public record Frozen(TranslationPolicy policy, String hash, Instant deadline, SystemModelExecutionRef execution) {}
    private final JdbcTemplate jdbc;
    private final PipelineTranslationProperties settings;
    private final SubtitleTranslationProperties translation;
    private final ObjectMapper json = new ObjectMapper();
    private int sampleRate=16000,channels=1;
    private com.example.courselingo.task.runner.AsrChunkingProperties chunking=new com.example.courselingo.task.runner.AsrChunkingProperties();

    @org.springframework.beans.factory.annotation.Autowired(required=false)
    public void configureAudioOptions(com.example.courselingo.task.runner.AsrChunkingProperties chunking,
            org.springframework.core.env.Environment environment) {
        this.chunking=chunking;
        sampleRate=environment.getProperty("courselingo.media.ffmpeg.sample-rate",Integer.class,16000);
        channels=environment.getProperty("courselingo.media.ffmpeg.channels",Integer.class,1);
    }

    public PipelinePolicyService(JdbcTemplate jdbc, PipelineTranslationProperties settings, SubtitleTranslationProperties translation) {
        this.jdbc = jdbc; this.settings = settings; this.translation = translation;
    }
    @PostConstruct public void validate() { if (settings.isEnabled()) policy(); }
    public boolean enabledForNewTasks() { return settings.isEnabled(); }
    private TranslationPolicy policy() {
        var f = translation.getFullText();
        return settings.freezePipeline(f.getRequestTimeout(), f.getTotalTimeout(), f.getBatchMaxSegments(), f.getBatchMaxInputChars(),
            sampleRate,channels,chunking.effectiveConcurrency(),Math.min(chunking.effectiveMaxChunkFileSizeBytes(),chunking.effectiveMaxAudioFileSizeBytes()),
            chunking.getChunkRetry().getMaxAttempts(),chunking.getChunkRetry().getBackoff().stream()
                .map(d->d==null?0L:d.toMillis()).toList());
    }

    /** Called in the task creation transaction, before the outbox message is visible. */
    public void freeze(SystemModelExecutionRef ref) {
        if (!settings.isEnabled()) return;
        if (ref == null) throw TranslationFailure.of(TranslationFailure.Reason.SNAPSHOT_INVALID);
        try {
            var owner = jdbc.queryForList("""
                SELECT t.created_at,u.file_md5,u.size_bytes,u.object_key FROM analysis_task t
                JOIN upload_session u ON u.id=t.upload_id AND u.user_id=t.user_id
                JOIN system_model_execution_snapshot s ON s.id=? AND s.task_id=t.id AND s.user_id=t.user_id
                WHERE t.id=? AND t.user_id=? AND t.status='CREATED' AND t.deleted_at IS NULL AND s.config_version=?
                """, ref.snapshotId(), ref.taskId(), ref.userId(), ref.configVersion());
            if (owner.size() != 1) throw TranslationFailure.of(TranslationFailure.Reason.SNAPSHOT_INVALID);
            var row = owner.getFirst();
            var p = policy();
            String encoded = json.writeValueAsString(p);
            Instant created = instant(row.get("created_at"));
            String identity = json.writeValueAsString(Arrays.asList(row.get("file_md5"), row.get("size_bytes"), row.get("object_key")));
            jdbc.update("""
                INSERT INTO pipeline_policy_snapshot(task_id,user_id,snapshot_id,config_version,engine_version,
                policy_json,policy_hash,prompt_hash,tokenizer_identity,media_identity_hash,deadline)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, ref.taskId(),ref.userId(),ref.snapshotId(),ref.configVersion(),p.engineVersion(),
                encoded, hash(encoded), hash(com.example.courselingo.subtitle.service.SubtitleTranslationPromptFactory.policyTemplate()),
                p.tokenCounter(),hash(identity),Timestamp.from(created.plusSeconds(1800)));
        } catch (TranslationFailure safe) { throw safe; }
        catch (Exception ignored) { throw TranslationFailure.of(TranslationFailure.Reason.SNAPSHOT_INVALID); }
    }

    public Optional<Frozen> find(String taskId, long userId) {
        try {
            var rows = jdbc.queryForList("""
                SELECT p.* FROM pipeline_policy_snapshot p JOIN analysis_task t ON t.id=p.task_id AND t.user_id=p.user_id
                WHERE p.task_id=? AND p.user_id=? AND t.deleted_at IS NULL
                """, taskId,userId);
            if (rows.isEmpty()) return Optional.empty();
            var row = rows.getFirst();
            var policy = json.readValue((String) row.get("policy_json"), TranslationPolicy.class);
            String canonical = json.writeValueAsString(policy);
            if (!hash(canonical).equals(row.get("policy_hash"))
                || !hash(com.example.courselingo.subtitle.service.SubtitleTranslationPromptFactory.policyTemplate()).equals(row.get("prompt_hash")))
                throw TranslationFailure.of(TranslationFailure.Reason.SNAPSHOT_INVALID);
            return Optional.of(new Frozen(policy, (String) row.get("policy_hash"), instant(row.get("deadline")),
                new SystemModelExecutionRef((String) row.get("snapshot_id"),((Number)row.get("config_version")).longValue(),taskId,userId)));
        } catch (TranslationFailure safe) { throw safe; }
        catch (Exception ignored) { throw TranslationFailure.of(TranslationFailure.Reason.SNAPSHOT_INVALID); }
    }
    public static String hash(String text) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(text.getBytes(StandardCharsets.UTF_8))); }
        catch (Exception ignored) { throw new IllegalStateException("SHA-256 unavailable"); }
    }
    private static Instant instant(Object value) {
        if (value instanceof Timestamp timestamp) return timestamp.toInstant();
        if (value instanceof java.time.LocalDateTime local) return local.toInstant(java.time.ZoneOffset.UTC);
        throw TranslationFailure.of(TranslationFailure.Reason.SNAPSHOT_INVALID);
    }
}
