package com.example.courselingo.systemmodel;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public class SystemModelExecutionService {
    private final JdbcTemplate jdbc;
    private final SystemModelRegistry registry;
    private final TransactionTemplate transactions;
    private final ObjectMapper json =
            com.fasterxml.jackson.databind.json.JsonMapper.builder()
                    .disable(com.fasterxml.jackson.databind.MapperFeature.USE_ANNOTATIONS)
                    .build();

    SystemModelExecutionService(
            JdbcTemplate jdbc, SystemModelRegistry registry, PlatformTransactionManager manager) {
        this.jdbc = jdbc;
        this.registry = registry;
        this.transactions = new TransactionTemplate(manager);
    }

    public SystemModelExecutionRef freezePipeline(String taskId, long userId) {
        return freeze(taskId, userId, "PIPELINE", taskId, "CREATED");
    }

    public SystemModelExecutionRef pipeline(String taskId, long userId) {
        // Legacy tasks are pinned once on adoption, never relabelled as frozen at their original
        // creation time.
        return freeze(taskId, userId, "PIPELINE", taskId, "ADOPTED");
    }

    public SystemModelExecutionRef operation(String taskId, long userId, String feature) {
        return freeze(taskId, userId, feature, UUID.randomUUID().toString(), "CREATED");
    }

    private SystemModelExecutionRef freeze(
            String taskId, long userId, String type, String operation, String origin) {
        try {
            return transactions.execute(
                    status -> {
                        // Shared lock ordering serializes creation and configuration commits;
                        // notification loss cannot reuse a stale head.
                        long current = registry.lockVersion();
                        requireOwnedTask(taskId, userId);
                        List<SystemModelExecutionRef> existing =
                                jdbc.query(
                                        "SELECT id,config_version FROM"
                                            + " system_model_execution_snapshot WHERE task_id=? AND"
                                            + " user_id=? AND operation_type=? AND operation_id=?",
                                        (r, i) ->
                                                new SystemModelExecutionRef(
                                                        r.getString(1),
                                                        r.getLong(2),
                                                        taskId,
                                                        userId),
                                        taskId,
                                        userId,
                                        type,
                                        operation);
                        if (!existing.isEmpty()) return existing.getFirst();
                        var config = registry.load(current);
                        var routes = new LinkedHashMap<String, SystemModelResolvedRoute>();
                        for (String feature : config.defaults().keySet())
                            routes.put(feature, registry.resolve(config, feature));
                        String id = UUID.randomUUID().toString();
                        var snapshot = new Payload(Map.copyOf(routes), registry.fullText(config));
                        jdbc.update(
                                "INSERT INTO system_model_execution_snapshot"
                                    + " (id,task_id,user_id,operation_type,operation_id,config_version,resolved_config_json,snapshot_origin)"
                                    + " VALUES (?,?,?,?,?,?,?,?)",
                                id,
                                taskId,
                                userId,
                                type,
                                operation,
                                current,
                                encode(snapshot),
                                origin);
                        return new SystemModelExecutionRef(id, current, taskId, userId);
                    });
        } catch (BusinessException safe) {
            throw safe;
        } catch (RuntimeException ignored) {
            throw SystemModelConfigCodec.unavailable();
        }
    }

    public SystemModelResolvedRoute route(SystemModelExecutionRef ref, String feature) {
        var payload = read(ref);
        var route = payload.routes().get(feature);
        if (route == null) throw invalid();
        // The version is authority; persisted resolved data is an observation, not authority to
        // choose a key or endpoint.
        var authoritative = registry.resolve(registry.load(ref.configVersion()), feature);
        if (!authoritative.equals(route)) throw invalid();
        return route;
    }

    public String credential(SystemModelExecutionRef ref, String feature) {
        return registry.credential(ref.configVersion(), route(ref, feature));
    }

    public boolean fullText(SystemModelExecutionRef ref) {
        return read(ref).fullTextTranslation();
    }

    public com.example.courselingo.modelrouting.AiModelRoute visionRoute(
            SystemModelExecutionRef ref) {
        return SystemModelVisionProvider.route(this, ref);
    }

    public SystemModelViews.Execution query(String id) {
        try {
            return jdbc.queryForObject(
                    "SELECT * FROM system_model_execution_snapshot WHERE id=?",
                    (r, i) -> {
                        var payload = decode(r.getString("resolved_config_json"));
                        return new SystemModelViews.Execution(
                                r.getString("id"),
                                r.getString("task_id"),
                                r.getLong("user_id"),
                                r.getString("operation_type"),
                                r.getString("operation_id"),
                                r.getLong("config_version"),
                                Map.copyOf(payload.routes()),
                                payload.fullTextTranslation(),
                                r.getString("snapshot_origin"),
                                r.getString("created_at"));
                    },
                    id);
        } catch (RuntimeException ignored) {
            throw invalid();
        }
    }

    public java.util.List<SystemModelViews.Execution> list(String taskId) {
        if (taskId == null || taskId.length() > 64) throw invalid();
        try {
            return jdbc
                    .queryForList(
                            "SELECT id FROM system_model_execution_snapshot WHERE task_id=? ORDER"
                                + " BY created_at DESC,id DESC LIMIT 50",
                            String.class,
                            taskId)
                    .stream()
                    .map(this::query)
                    .toList();
        } catch (RuntimeException ignored) {
            throw invalid();
        }
    }

    private Payload read(SystemModelExecutionRef ref) {
        if (ref == null) throw invalid();
        try {
            requireOwnedTask(ref.taskId(), ref.userId());
            return jdbc.queryForObject(
                    "SELECT resolved_config_json FROM system_model_execution_snapshot WHERE id=?"
                            + " AND config_version=? AND task_id=? AND user_id=?",
                    (r, i) -> decode(r.getString(1)),
                    ref.snapshotId(),
                    ref.configVersion(),
                    ref.taskId(),
                    ref.userId());
        } catch (RuntimeException ignored) {
            throw invalid();
        }
    }

    private void requireOwnedTask(String task, long owner) {
        Integer count =
                jdbc.queryForObject(
                        "SELECT COUNT(*) FROM analysis_task WHERE id=? AND user_id=? AND deleted_at"
                                + " IS NULL AND status NOT IN ('CANCELED','FAILED')",
                        Integer.class,
                        task,
                        owner);
        if (count == null || count != 1) throw invalid();
    }

    private String encode(Payload payload) {
        try {
            return json.writeValueAsString(payload);
        } catch (Exception ignored) {
            throw invalid();
        }
    }

    private Payload decode(String value) {
        try {
            return json.readValue(value, Payload.class);
        } catch (Exception ignored) {
            throw invalid();
        }
    }

    record Payload(Map<String, SystemModelResolvedRoute> routes, boolean fullTextTranslation) {}

    private static BusinessException invalid() {
        return new BusinessException(ErrorCode.SYSTEM_MODEL_SNAPSHOT_INVALID);
    }
}
