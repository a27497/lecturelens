package com.example.courselingo.systemmodel;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import com.example.courselingo.common.exception.BusinessException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.beans.factory.support.StaticListableBeanFactory;
import java.nio.file.*;
import java.util.*;

@EnabledIfEnvironmentVariable(named = "SYSTEM_MODEL_TEST_JDBC_URL", matches = ".+")
class CourseModelUsageMySqlTest {
    @TempDir Path temp;

    @Test
    void ownerProjectionRejectsForeignAndDeletedTasksAndForgedSnapshotLinks() throws Exception {
        try (var db = new SystemModelMySqlFixture()) {
            long owner = db.user(), other = db.user();
            String task = db.task(owner), foreign = db.task(other);
            var registry = mock(SystemModelRegistry.class);
            var route = new SystemModelResolvedRoute("COURSE_QA", "DATABASE", SystemModelProtocol.OPENAI_CHAT,
                    "PRIVATE_CREDENTIAL_ID", 10L, 20L, "https://private-endpoint.invalid", "model-a",
                    Set.of("TEXT_CHAT"), 0.0, 123, 1000L, 1, true, "9876");
            when(registry.currentVersion()).thenReturn(0L);
            when(registry.load(0L)).thenReturn(new SystemModelStoredConfig(List.of(), List.of(), Map.of(), Map.of(), "private", false));
            when(registry.resolve(any(), anyString())).thenReturn(route);
            var executions = new SystemModelExecutionService(db.jdbc, registry, db.transactions);
            var beans = new StaticListableBeanFactory(Map.of("registry", registry, "executions", executions));
            var service = new CourseModelUsageService(db.jdbc, beans.getBeanProvider(SystemModelRegistry.class), beans.getBeanProvider(SystemModelExecutionService.class));
            var json = com.fasterxml.jackson.databind.json.JsonMapper.builder().disable(com.fasterxml.jackson.databind.MapperFeature.USE_ANNOTATIONS).build();
            String payload = json.writeValueAsString(new SystemModelExecutionService.Payload(Map.of("COURSE_QA", route), false));
            snapshot(db, "own-snapshot", task, owner, payload, "PIPELINE", "ADOPTED");
            snapshot(db, "qa-snapshot", task, owner, payload, "COURSE_QA", "CREATED");
            snapshot(db, "foreign-snapshot", foreign, other, payload, "COURSE_QA", "CREATED");
            qa(db, task, owner, null, null);
            qa(db, task, owner, "qa-snapshot", "RESPONSE_RECEIVED");
            qa(db, task, owner, "foreign-snapshot", "DISPATCHED");
            var view = service.read(task, owner);
            assertThat(view.pipeline()).singleElement().satisfies(s -> assertThat(s.origin()).isEqualTo("ADOPTED"));
            assertThat(view.qa()).filteredOn(q -> q.selection() != null).singleElement()
                    .satisfies(q -> assertThat(q.selection().snapshotId()).isEqualTo("qa-snapshot"));
            assertThat(view.qa()).allMatch(q -> q.totalTokens() == null);
            String publicJson = new ObjectMapper().writeValueAsString(view);
            assertThat(publicJson).contains("model-a", "own-snapshot").doesNotContain("PRIVATE_CREDENTIAL", "private-endpoint", "9876", "providerId", "baseUrl", "credential", "foreign-snapshot", "config_json");
            assertThatThrownBy(() -> service.read(task, other)).isInstanceOf(BusinessException.class);
            assertThatThrownBy(() -> service.read(foreign, owner)).isInstanceOf(BusinessException.class);
            db.jdbc.update("UPDATE analysis_task SET deleted_at=CURRENT_TIMESTAMP WHERE id=?", task);
            assertThatThrownBy(() -> service.read(task, owner)).isInstanceOf(BusinessException.class);
        }
    }

    @Test
    void disabledSystemManagementDoesNotReadSnapshotOrCatalogTables() throws Exception {
        try (var db = new SystemModelMySqlFixture()) {
            long owner = db.user(); String task = db.task(owner);
            qa(db, task, owner, null, null);
            db.jdbc.execute("RENAME TABLE system_model_execution_snapshot TO hidden_snapshot");
            var beans = new StaticListableBeanFactory();
            var service = new CourseModelUsageService(db.jdbc, beans.getBeanProvider(SystemModelRegistry.class), beans.getBeanProvider(SystemModelExecutionService.class));
            assertThat(service.read(task, owner).qa()).singleElement().satisfies(q -> assertThat(q.selection()).isNull());
        }
    }

    @Test
    void baselineCodeCanValidateWithTheOriginalRepeatableInARollbackBundle() throws Exception {
        try (var db = new SystemModelMySqlFixture()) {
            Path baseline = temp.resolve("baseline"), bundle = temp.resolve("rollback-migrations");
            Files.createDirectories(baseline); Files.createDirectories(bundle);
            try (var files = Files.list(Path.of("src/main/resources/db/migration"))) {
                for (var f : files.filter(p -> p.getFileName().toString().startsWith("V")).toList()) Files.copy(f, baseline.resolve(f.getFileName()));
            }
            Files.copy(Path.of("src/main/resources/db/migration/R__course_qa_model_usage.sql"), bundle.resolve("R__course_qa_model_usage.sql"));
            var rollback = Flyway.configure().dataSource(db.dataSource)
                    .locations("filesystem:" + baseline, "filesystem:" + bundle).outOfOrder(false).load();
            rollback.validate();
            assertThat(rollback.migrate().migrationsExecuted).isZero();
            assertThat(rollback.info().current().getVersion().toString()).isEqualTo("25");
        }
    }

    @Test
    void bothFuturePr35MigrationOrdersAndLegacyNullUpgradeWorkWithoutOutOfOrder() throws Exception {
        for (boolean pr35First : List.of(false, true)) {
            try (var db = new SystemModelMySqlFixture()) {
                // Recreate an actual pre-PR3 database, including its Flyway history.
                db.jdbc.execute("ALTER TABLE course_qa_record DROP COLUMN execution_snapshot_id, DROP COLUMN invocation_state, DROP COLUMN ai_call_record_id");
                db.jdbc.update("DELETE FROM flyway_schema_history WHERE version IS NULL AND script='R__course_qa_model_usage.sql'");
                long owner = db.user(); String task = db.task(owner);
                db.jdbc.update("INSERT INTO course_qa_record(task_id,user_id,question,answer,evidence_json,status) VALUES (?,?,'legacy','legacy','[]','SUCCEEDED')", task, owner);
                Path base = temp.resolve(UUID.randomUUID().toString()); Files.createDirectories(base);
                try (var files = Files.list(Path.of("src/main/resources/db/migration"))) {
                    for (var f : files.filter(p -> p.getFileName().toString().startsWith("V")).toList()) Files.copy(f, base.resolve(f.getFileName()));
                }
                if (pr35First) copyFuture(base);
                migrate(db, base).migrate();
                Files.copy(Path.of("src/main/resources/db/migration/R__course_qa_model_usage.sql"), base.resolve("R__course_qa_model_usage.sql"));
                migrate(db, base).migrate();
                if (!pr35First) { copyFuture(base); migrate(db, base).migrate(); }
                var flyway = migrate(db, base);
                flyway.validate(); assertThat(flyway.info().current().getVersion().toString()).isEqualTo("31");
                assertThat(flyway.migrate().migrationsExecuted).isZero();
                assertThat(db.jdbc.queryForMap("SELECT execution_snapshot_id,invocation_state,ai_call_record_id FROM course_qa_record WHERE task_id=?", task).values()).containsOnlyNulls();
                qa(db, task, owner, "new-exact-reference", "SKIPPED_NO_EVIDENCE");
                assertThat(db.jdbc.queryForObject("SELECT COUNT(*) FROM course_qa_record WHERE execution_snapshot_id='new-exact-reference'", Integer.class)).isEqualTo(1);
            }
        }
    }

    private void copyFuture(Path destination) throws Exception {
        try (var files = Files.list(Path.of("src/test/resources/pr35-migrations"))) {
            for (var f : files.filter(p -> p.toString().endsWith(".sql")).toList()) Files.copy(f, destination.resolve(f.getFileName()));
        }
    }
    private Flyway migrate(SystemModelMySqlFixture db, Path folder) {
        return Flyway.configure().dataSource(db.dataSource).locations("filesystem:" + folder).outOfOrder(false).load();
    }
    private void snapshot(SystemModelMySqlFixture db, String id, String task, long owner, String payload, String type, String origin) {
        db.jdbc.update("INSERT INTO system_model_execution_snapshot(id,task_id,user_id,operation_type,operation_id,config_version,resolved_config_json,snapshot_origin) VALUES (?,?,?,?,?,0,?,?)", id, task, owner, type, id, payload, origin);
    }
    private void qa(SystemModelMySqlFixture db, String task, long owner, String snapshot, String state) {
        db.jdbc.update("INSERT INTO course_qa_record(task_id,user_id,question,answer,evidence_json,status,execution_snapshot_id,invocation_state) VALUES (?,?,'synthetic','synthetic','[]','SUCCEEDED',?,?)", task, owner, snapshot, state);
    }
}
