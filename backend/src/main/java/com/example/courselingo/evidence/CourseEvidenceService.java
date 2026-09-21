package com.example.courselingo.evidence;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.task.service.GenerationFence;
import com.example.courselingo.vision.ocr.OcrTextQualityEvaluator;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class CourseEvidenceService {
    public static final String NORMALIZATION_VERSION = "evidence-v1";
    private final JdbcTemplate jdbc;
    private final ObjectMapper json;
    private final GenerationFence fence;
    private final TransactionTemplate read;

    public CourseEvidenceService(JdbcTemplate jdbc, ObjectMapper json, GenerationFence fence, PlatformTransactionManager manager) {
        this.jdbc = jdbc;
        this.json = json;
        this.fence = fence;
        read = new TransactionTemplate(manager);
        read.setReadOnly(true);
    }

    public long ensureSnapshot(String taskId, Long userId) {
        var ticket = fence.begin(taskId, userId, null);
        if (exists(taskId, userId, ticket.revision())) return ticket.revision();
        List<CourseEvidence> sources = read.execute(status -> collect(taskId, userId, ticket.revision()));
        return fence.commit(ticket, () -> {
            if (exists(taskId, userId, ticket.revision())) return ticket.revision();
            for (CourseEvidence item : sources) jdbc.update("""
                INSERT INTO course_evidence(evidence_id,task_id,user_id,revision,source_type,source_id,start_ms,end_ms,payload)
                VALUES (?,?,?,?,?,?,?,?,?)
                """, item.evidenceId(), taskId, userId, item.revision(), item.sourceType(), item.sourceId(),
                item.startMs(), item.endMs(), encode(item));
            String manifest = hash(sources.stream().map(CourseEvidence::evidenceId).sorted().collect(java.util.stream.Collectors.joining()));
            jdbc.update("""
                INSERT INTO course_evidence_snapshot(task_id,revision,user_id,manifest_hash,created_at)
                VALUES (?,?,?,?,CURRENT_TIMESTAMP)
                """, taskId, ticket.revision(), userId, manifest);
            EvidenceChangeLog.append(jdbc, taskId, userId, ticket.revision(), "UPSERT");
            return ticket.revision();
        });
    }

    public Page page(String taskId, Long userId, Long revision, String after, int limit) {
        long current = ensureSnapshot(taskId, userId);
        long selected = revision == null ? current : revision;
        if (!exists(taskId, userId, selected)) throw new BusinessException(ErrorCode.COMMON_NOT_FOUND);
        int size = Math.max(1, Math.min(limit, 200));
        List<CourseEvidence> items = jdbc.query("""
            SELECT payload FROM course_evidence WHERE task_id=? AND user_id=? AND revision=? AND evidence_id>?
            ORDER BY evidence_id LIMIT ?
            """, (rs,n) -> decode(rs.getString(1)), taskId, userId, selected, after == null ? "" : after, size + 1);
        boolean more = items.size() > size;
        if (more) items = items.subList(0, size);
        // Recheck after reading: a concurrent deletion must not make a cached revision readable.
        requireOwned(taskId, userId);
        return new Page(selected, selected != current, List.copyOf(items), more ? items.getLast().evidenceId() : null);
    }

    public List<CourseEvidence> current(String taskId, Long userId) {
        long revision = ensureSnapshot(taskId, userId);
        List<CourseEvidence> result = jdbc.query("""
            SELECT payload FROM course_evidence WHERE task_id=? AND user_id=? AND revision=? ORDER BY start_ms,evidence_id
            """, (rs,n) -> decode(rs.getString(1)), taskId, userId, revision);
        requireOwned(taskId, userId);
        return result;
    }

    public List<Map<String,Object>> changes(Long userId, long after, int limit) {
        return jdbc.queryForList("""
            SELECT sequence_id,task_id,revision,change_type,created_at FROM evidence_change
            WHERE user_id=? AND sequence_id>? ORDER BY sequence_id LIMIT ?
            """, userId, Math.max(0, after), Math.max(1, Math.min(limit, 200)));
    }

    private boolean exists(String taskId, Long userId, long revision) {
        return !jdbc.queryForList("SELECT revision FROM course_evidence_snapshot WHERE task_id=? AND user_id=? AND revision=?",
            taskId, userId, revision).isEmpty();
    }

    private void requireOwned(String taskId, Long userId) {
        if (jdbc.queryForList("SELECT id FROM analysis_task WHERE id=? AND user_id=? AND deleted_at IS NULL", taskId, userId).isEmpty()) {
            throw new BusinessException(ErrorCode.TASK_NOT_FOUND);
        }
    }

    private List<CourseEvidence> collect(String taskId, Long userId, long revision) {
        List<CourseEvidence> result = new ArrayList<>();
        for (var row : rows("subtitle_segment", taskId, userId)) {
            add(result, taskId, userId, revision, "SUBTITLE", row, "text", "language", false, null);
        }
        for (var row : rows("subtitle_translation_segment", taskId, userId)) {
            add(result, taskId, userId, revision, "SUBTITLE_TRANSLATION", row, "translated_text", "target_language", true, null);
        }
        for (var row : rows("video_keyframe_ocr", taskId, userId)) {
            String image = "/api/tasks/" + taskId + "/keyframes/" + row.get("keyframe_id") + "/image";
            add(result, taskId, userId, revision, "OCR", row, "ocr_text", "language_hint", false, image);
        }
        for (var row : rows("video_keyframe_analysis", taskId, userId)) {
            String image = "/api/tasks/" + taskId + "/keyframes/" + row.get("keyframe_id") + "/image";
            add(result, taskId, userId, revision, "VISION", row, "visual_summary", "language_hint", true, image);
        }
        return result;
    }

    private List<Map<String,Object>> rows(String table, String taskId, Long userId) {
        // Table names are literals chosen above, never supplied by a request.
        return jdbc.queryForList("SELECT * FROM " + table + " WHERE task_id=? AND user_id=? ORDER BY id", taskId, userId);
    }

    private void add(List<CourseEvidence> target, String taskId, Long userId, long revision, String type,
                     Map<String,Object> row, String textColumn, String languageColumn, boolean derived, String image) {
        String raw = text(row.get(textColumn));
        if (raw.isBlank()) return;
        String normalized = raw.replaceAll("\\s+", " ").strip();
        String language = text(row.get(languageColumn));
        Double confidence = row.get("confidence") instanceof Number n ? n.doubleValue() : null;
        var quality = OcrTextQualityEvaluator.evaluate(raw, confidence, language, text(row.get("screen_type")));
        boolean succeeded = row.get("status") == null || "SUCCEEDED".equals(row.get("status"));
        boolean useful = succeeded && (!type.equals("OCR") || quality.useful());
        String reason = !succeeded ? "source_not_succeeded" : type.equals("OCR") ? quality.reason() : "source_text";
        long start = number(row.getOrDefault("start_millis", row.get("timestamp_millis")));
        long end = Math.max(start, number(row.getOrDefault("end_millis", start)));
        String id = String.valueOf(row.get("id"));
        String logical = row.get("segment_index") == null ? Long.toString(start) : row.get("segment_index").toString();
        String contentHash = hash(raw);
        String evidenceId = hash(String.join("|", taskId, Long.toString(revision), type, logical, id, language, NORMALIZATION_VERSION, contentHash));
        // Preserve source row provenance, and link derived translations back to the source segment's logical identity.
        List<String> refs = new ArrayList<>();
        refs.add(type + ":" + id + "@" + revision);
        if (type.equals("SUBTITLE_TRANSLATION")) refs.add("SUBTITLE_SEGMENT_INDEX:" + logical + "@" + revision);
        if (image != null) refs.add("KEYFRAME:" + row.get("keyframe_id") + "@" + revision);
        target.add(new CourseEvidence(evidenceId, taskId, userId, revision, type, id, List.copyOf(refs),
            start, end, language, raw, normalized, image, derived, NORMALIZATION_VERSION, contentHash,
            useful, reason, confidence, Boolean.TRUE.equals(row.get("text_truncated"))
                || number(row.get("text_truncated")) == 1));
    }

    private String encode(CourseEvidence item) {
        try { return json.writeValueAsString(item); }
        catch (Exception e) { throw new IllegalStateException("Cannot encode evidence", e); }
    }
    private CourseEvidence decode(String payload) {
        try { return json.readValue(payload, CourseEvidence.class); }
        catch (Exception e) { throw new IllegalStateException("Invalid stored evidence", e); }
    }
    private static String text(Object value) { return value == null ? "" : value.toString(); }
    private static long number(Object value) { return value instanceof Number n ? n.longValue() : 0L; }
    private static String hash(String value) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8))); }
        catch (java.security.NoSuchAlgorithmException e) { throw new IllegalStateException(e); }
    }
    public record Page(long revision, boolean stale, List<CourseEvidence> items, String nextCursor) { }
}
