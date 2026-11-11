package com.example.courselingo.qa.service;

import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.evidence.CourseEvidence;
import com.example.courselingo.qa.dto.CourseQaEvidenceItem;
import com.example.courselingo.qa.dto.CourseQaHistoryPage;
import com.example.courselingo.qa.mapper.CourseQaRecordMapper;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CourseQaHistoryService {
    private final CurrentUserService users;
    private final CourseQaRecordMapper records;
    private final JdbcTemplate jdbc;
    private final ObjectMapper json;

    public CourseQaHistoryService(CurrentUserService users, CourseQaRecordMapper records, JdbcTemplate jdbc, ObjectMapper json) {
        this.users = users; this.records = records; this.jdbc = jdbc; this.json = json;
    }

    @Transactional(readOnly = true, isolation = Isolation.READ_COMMITTED)
    public CourseQaHistoryPage read(String taskId, String authorization, Long before, int limit) {
        if (taskId == null || taskId.isBlank() || taskId.length() > 128 || limit < 1 || limit > 50
                || (before != null && before < 1)) throw new BusinessException(ErrorCode.COMMON_BAD_REQUEST);
        Long owner = users.currentUser(authorization).userId();
        long revision = owned(taskId, owner);
        var rows = records.selectHistory(taskId, owner, before, limit + 1);
        boolean more = rows.size() > limit;
        if (more) rows = rows.subList(0, limit);
        var citations = rows.stream().map(row -> decode(row.getEvidenceJson())).toList();
        var ids = new LinkedHashSet<String>();
        for (var saved : citations) for (var citation : saved) {
            if (citation.evidenceId() != null && citation.revision() != null && citation.revision() == revision) ids.add(citation.evidenceId());
        }
        // At most 50 records x 8 citations. Never materialize sources or share validation across reads.
        var sources = sources(taskId, owner, revision, ids);
        List<CourseQaHistoryPage.Item> items = new ArrayList<>();
        int recordIndex = 0;
        for (var row : rows) {
            var saved = citations.get(recordIndex++);
            List<CourseQaEvidenceItem> valid = new ArrayList<>();
            for (var citation : saved) {
                if (citation.evidenceId() == null || citation.revision() == null || citation.revision() != revision) continue;
                var source = sources.get(citation.evidenceId());
                if (source == null) continue;
                valid.add(new CourseQaEvidenceItem(source.sourceType(), source.sourceId(), source.startMs(), source.endMs(),
                    null, bounded(source.rawText()), "", source.extractionConfidence(), source.evidenceId(), revision));
            }
            String status = "SUCCEEDED".equals(row.getStatus()) ? "SUCCEEDED" : "FAILED";
            items.add(new CourseQaHistoryPage.Item(String.valueOf(row.getId()), row.getQuestion(),
                "SUCCEEDED".equals(status) ? row.getAnswer() : "", status, row.getCreatedAt() == null ? null : row.getCreatedAt().toInstant(java.time.ZoneOffset.UTC), List.copyOf(valid),
                valid.isEmpty() ? (saved.isEmpty() ? "none" : "unavailable") : valid.size() == saved.size() ? "current" : "partial"));
        }
        // READ_COMMITTED makes this a fresh ownership/revision check after the bounded read, including concurrent deletion.
        if (owned(taskId, owner) != revision) throw new BusinessException(ErrorCode.STUDY_CONFLICT);
        return new CourseQaHistoryPage(List.copyOf(items), more ? String.valueOf(rows.getLast().getId()) : null);
    }
    private Map<String, CourseEvidence> sources(String taskId, Long owner, long revision, Set<String> ids) {
        if (ids.isEmpty()) return Map.of();
        String placeholders = String.join(",", Collections.nCopies(ids.size(), "?"));
        var args = new ArrayList<Object>(List.of(taskId, owner, revision)); args.addAll(ids);
        var rows = jdbc.queryForList("""
            SELECT e.evidence_id,e.payload FROM course_evidence e JOIN analysis_task t ON t.id=e.task_id AND t.user_id=e.user_id
            AND t.content_revision=e.revision AND t.deleted_at IS NULL AND t.status='SUCCEEDED'
            WHERE e.task_id=? AND e.user_id=? AND e.revision=? AND e.evidence_id IN (""" + placeholders + ")", args.toArray());
        var counts = new HashMap<String, Integer>();
        for (var row : rows) counts.merge((String) row.get("evidence_id"), 1, Integer::sum);
        var valid = new HashMap<String, CourseEvidence>();
        for (var row : rows) {
            String id = (String) row.get("evidence_id");
            if (!ids.contains(id) || counts.get(id) != 1) continue;
            try {
                var source = json.readValue((String) row.get("payload"), CourseEvidence.class);
                if (source == null || !source.retrievable() || source.revision() != revision || !owner.equals(source.ownerId())
                        || !taskId.equals(source.courseId()) || !id.equals(source.evidenceId())) continue;
                valid.put(id, source);
            } catch (com.fasterxml.jackson.core.JsonProcessingException ignored) { /* Corrupt legacy sources are not trusted. */ }
        }
        return valid;
    }
    private long owned(String taskId, Long owner) {
        var revisions = jdbc.queryForList("SELECT content_revision FROM analysis_task WHERE id=? AND user_id=? AND deleted_at IS NULL", Long.class, taskId, owner);
        if (revisions.isEmpty()) throw new BusinessException(ErrorCode.TASK_NOT_FOUND);
        return revisions.getFirst();
    }
    private List<CourseQaEvidenceItem> decode(String value) {
        if (value == null || value.length() > 131072) return List.of();
        try {
            List<CourseQaEvidenceItem> items = json.readValue(value, new TypeReference<>() { });
            return items == null ? List.of() : items.stream().filter(Objects::nonNull).limit(8).toList();
        } catch (com.fasterxml.jackson.core.JsonProcessingException ignored) { return List.of(); }
    }
    private static String bounded(String text) { return text == null ? "" : text.substring(0, Math.min(1200, text.length())); }
}
