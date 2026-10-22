package com.example.courselingo.systemmodel;

import com.example.courselingo.common.exception.BusinessException;
import org.springframework.boot.sql.init.dependency.DependsOnDatabaseInitialization;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/** Disabling management must not resume a pinned pipeline with today's deployment defaults. */
@Component
@DependsOnDatabaseInitialization
public final class SystemModelDisabledTaskGuard {
    private final JdbcTemplate jdbc;
    private final boolean managed;

    @org.springframework.beans.factory.annotation.Autowired
    public SystemModelDisabledTaskGuard(JdbcTemplate jdbc,
            @org.springframework.beans.factory.annotation.Value("${spring.flyway.enabled:false}") boolean initialized,
            @org.springframework.beans.factory.annotation.Value("${courselingo.ai.system-models.enabled:false}") boolean managed) {
        this.jdbc = jdbc;
        this.managed = managed;
        // Preserve database-free startup without Flyway; execution still checks below.
        if (!managed && initialized) rejectIfPresent(() -> jdbc.queryForObject(
                "SELECT EXISTS(SELECT 1 FROM system_model_execution_snapshot s "
                + "JOIN analysis_task t ON t.id=s.task_id "
                + "WHERE s.operation_type='PIPELINE' "
                + "AND t.status IN ('CREATED','QUEUED','RUNNING','RETRYING'))", Boolean.class));
    }

    SystemModelDisabledTaskGuard(JdbcTemplate jdbc, boolean initialized) { this(jdbc, initialized, false); }
    SystemModelDisabledTaskGuard(JdbcTemplate jdbc) { this(jdbc, true, false); }

    public void requireLegacyTask(String taskId) {
        if (managed) throw SystemModelConfigCodec.unavailable();
        rejectIfPresent(() -> jdbc.queryForObject(
                "SELECT EXISTS(SELECT 1 FROM system_model_execution_snapshot "
                + "WHERE task_id=? AND operation_type='PIPELINE')", Boolean.class, taskId));
    }

    private void rejectIfPresent(java.util.function.Supplier<Boolean> query) {
        try {
            if (!Boolean.FALSE.equals(query.get())) throw SystemModelConfigCodec.unavailable();
        } catch (BusinessException safe) { throw safe;
        } catch (org.springframework.jdbc.BadSqlGrammarException failure) {
            // A pre-V25 schema has no table. Hidden metadata or denied SELECT is not
            // proof of a legacy schema; only an actual missing-table response permits it.
            if (!"42S02".equals(failure.getSQLException().getSQLState()))
                throw SystemModelConfigCodec.unavailable();
        } catch (RuntimeException ignored) { throw SystemModelConfigCodec.unavailable(); }
    }
}
