package com.example.courselingo.systemmodel;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.List;

/** Owner projection only. Never serialize registry/catalog or resolved-route objects here. */
@Service
public class CourseModelUsageService {
    private final JdbcTemplate jdbc;
    private final SystemModelRegistry registry;
    private final SystemModelExecutionService executions;

    public CourseModelUsageService(JdbcTemplate jdbc, ObjectProvider<SystemModelRegistry> registry,
            ObjectProvider<SystemModelExecutionService> executions) {
        this.jdbc = jdbc;
        this.registry = registry.getIfAvailable();
        this.executions = executions.getIfAvailable();
    }

    @Transactional(readOnly = true)
    public Usage read(String task, long owner) {
        if (task == null || task.isBlank() || task.length() > 64) throw missing();
        // Hold ownership through projection; deletion/transfer serializes with this read.
        var owned = jdbc.queryForList("SELECT id FROM analysis_task WHERE id=? AND user_id=?"
                + " AND deleted_at IS NULL FOR SHARE", String.class, task, owner);
        if (owned.isEmpty()) throw missing();
        Selection current = null;
        List<Selection> pipeline = List.of();
        if (registry != null && executions != null) {
            long version = registry.currentVersion();
            var config = registry.load(version);
            current = new Selection(null, version, "CURRENT", null,
                    java.util.Arrays.stream(SystemModelFeature.values()).filter(SystemModelFeature::connected)
                            .map(f -> route(registry.resolve(config, f.name()))).toList());
            pipeline = jdbc.queryForList("SELECT id FROM system_model_execution_snapshot WHERE task_id=?"
                    + " AND user_id=? AND operation_type='PIPELINE' ORDER BY created_at DESC,id DESC LIMIT 50",
                    String.class, task, owner).stream().map(executions::query).map(e -> selection(e, null)).toList();
        }
        var qa = jdbc.query("SELECT q.id,q.execution_snapshot_id,q.invocation_state,q.ai_call_record_id,"
                + "q.provider,q.model,q.status,q.total_tokens,q.created_at,"
                + (executions == null ? "NULL AS linked_snapshot FROM course_qa_record q" : "s.id AS linked_snapshot "
                + "FROM course_qa_record q LEFT JOIN system_model_execution_snapshot s ON s.id=q.execution_snapshot_id"
                + " AND s.task_id=q.task_id AND s.user_id=q.user_id AND s.operation_type='COURSE_QA'")
                + " WHERE q.task_id=? AND q.user_id=? ORDER BY q.created_at DESC,q.id DESC LIMIT 50",
                (r, i) -> new Qa(r.getString("id"), r.getString("invocation_state"),
                        r.getString("ai_call_record_id"), r.getString("provider"), r.getString("model"),
                        r.getString("status"), (Integer) r.getObject("total_tokens"), r.getString("created_at"),
                        executions == null || r.getString("linked_snapshot") == null ? null
                                : selection(executions.query(r.getString("linked_snapshot")), "COURSE_QA")), task, owner);
        var calls = jdbc.query("SELECT id,stage,provider,model,status,total_tokens,started_at FROM ai_call_record"
                + " WHERE task_id=? AND user_id=? ORDER BY started_at DESC,id DESC LIMIT 100",
                (r, i) -> new Call(r.getString("id"), r.getString("stage"), r.getString("provider"),
                        r.getString("model"), r.getString("status"), (Integer) r.getObject("total_tokens"),
                        r.getString("started_at")), task, owner);
        return new Usage(task, current, pipeline, qa, calls);
    }

    private static Selection selection(SystemModelViews.Execution e, String feature) {
        return new Selection(e.id(), e.configVersion(), e.origin(), e.createdAt(),
                e.routes().values().stream().filter(r -> feature == null || r.feature().equals(feature))
                        .sorted(java.util.Comparator.comparing(SystemModelResolvedRoute::feature))
                        .map(CourseModelUsageService::route).toList());
    }

    private static Route route(SystemModelResolvedRoute r) {
        return new Route(r.feature(), r.source(), r.model());
    }
    private static BusinessException missing() { return new BusinessException(ErrorCode.TASK_NOT_FOUND); }
    public record Route(String feature, String source, String model) {}
    public record Selection(String snapshotId, long configVersion, String origin, String recordedAt, List<Route> routes) {}
    public record Qa(String recordId, String invocationState, String callRecordId, String provider, String model,
                     String status, Integer totalTokens, String recordedAt, Selection selection) {}
    public record Call(String recordId, String stage, String provider, String model, String status, Integer totalTokens, String startedAt) {}
    public record Usage(String taskId, Selection current, List<Selection> pipeline, List<Qa> qa, List<Call> calls) {}
}
