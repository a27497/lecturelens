package com.example.courselingo.evidence;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.util.*;

/** A selection within an already authorized canonical course snapshot, never an access grant. */
public record LearningScope(int version, String kind, String policy, long revision, List<String> evidence_ids) {
    public static LearningScope validate(LearningScope scope, long revision, List<CourseEvidence> authorized) {
        if (scope == null) return null; // Legacy callers retain the existing whole-course contract.
        if (scope.version != 1 || scope.revision != revision || !Set.of("course", "segments").contains(Objects.toString(scope.kind, ""))
                || !Set.of("strict", "course").contains(Objects.toString(scope.policy, "")) || scope.evidence_ids == null
                || scope.evidence_ids.size() > 16 || scope.evidence_ids.stream().anyMatch(id -> id == null || id.isBlank() || id.length() > 128)) {
            throw new BusinessException(ErrorCode.COMMON_BAD_REQUEST);
        }
        var ids = new TreeSet<>(scope.evidence_ids);
        if (ids.size() != scope.evidence_ids.size() || (scope.kind.equals("course") && (!ids.isEmpty() || !scope.policy.equals("strict")))
                || (scope.kind.equals("segments") && ids.isEmpty())) throw new BusinessException(ErrorCode.COMMON_BAD_REQUEST);
        var available = new HashSet<String>();
        for (var item : authorized) if (item.revision() == revision && item.retrievable() && item.endMs() > item.startMs()) available.add(item.evidenceId());
        if (!available.containsAll(ids)) throw new BusinessException(ErrorCode.STUDY_NOT_FOUND);
        return new LearningScope(1, scope.kind, scope.policy, revision, List.copyOf(ids));
    }
    public boolean permitsExpansion() { return kind.equals("segments") && policy.equals("course"); }
    public boolean contains(String id) { return kind.equals("course") || evidence_ids.contains(id); }
    public List<CourseEvidence> select(List<CourseEvidence> authorized, boolean expand) {
        if (expand && !permitsExpansion()) throw new BusinessException(ErrorCode.COMMON_BAD_REQUEST);
        return authorized.stream().filter(e -> expand || contains(e.evidenceId())).toList();
    }
}
