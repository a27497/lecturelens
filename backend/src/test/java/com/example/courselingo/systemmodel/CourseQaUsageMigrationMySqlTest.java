package com.example.courselingo.systemmodel;

import static org.assertj.core.api.Assertions.*;
import java.nio.file.*;
import java.util.*;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

@EnabledIfEnvironmentVariable(named = "SYSTEM_MODEL_TEST_JDBC_URL", matches = ".+")
class CourseQaUsageMigrationMySqlTest {
    @TempDir Path temp;
    private static final String[] COLUMNS = {"execution_snapshot_id", "invocation_state", "ai_call_record_id"};
    private static final String[] TYPES = {"VARCHAR(64)", "VARCHAR(32)", "BIGINT"};

    @ParameterizedTest
    @ValueSource(ints = {0, 1, 2, 3, 4, 5, 6, 7})
    void everyPartialV25SchemaIsCompletedWithoutRewritingExistingFacts(int present) throws Exception {
        Path baseline = temp.resolve("baseline"); Files.createDirectories(baseline);
        try (var files = Files.list(Path.of("src/main/resources/db/migration"))) {
            for (var f : files.filter(p -> p.getFileName().toString().startsWith("V")).toList()) Files.copy(f, baseline.resolve(f.getFileName()));
        }
        try (var db = new SystemModelMySqlFixture("filesystem:" + baseline)) {
            long owner = db.user(); String task = db.task(owner);
            db.jdbc.update("INSERT INTO course_qa_record(task_id,user_id,question,answer,evidence_json,status,provider,model) VALUES (?,?,'legacy','legacy','[]','SUCCEEDED','legacy-provider','legacy-model')", task, owner);
            for (int i = 0; i < COLUMNS.length; i++) {
                if ((present & (1 << i)) == 0) continue;
                db.jdbc.execute("ALTER TABLE course_qa_record ADD COLUMN " + COLUMNS[i] + " " + TYPES[i] + " NULL");
                db.jdbc.update("UPDATE course_qa_record SET " + COLUMNS[i] + "=? WHERE task_id=?", i == 2 ? 731L : "existing-fact", task);
            }
            Files.copy(Path.of("src/main/resources/db/migration/R__course_qa_model_usage.sql"), baseline.resolve("R__course_qa_model_usage.sql"));
            var flyway = Flyway.configure().dataSource(db.dataSource).locations("filesystem:" + baseline).outOfOrder(false).load();
            flyway.migrate(); flyway.validate();
            assertThat(flyway.info().current().getVersion().toString()).isEqualTo("25");
            var row = db.jdbc.queryForMap("SELECT execution_snapshot_id,invocation_state,ai_call_record_id,provider,model,total_tokens FROM course_qa_record WHERE task_id=?", task);
            for (int i = 0; i < COLUMNS.length; i++) {
                Object expected = (present & (1 << i)) == 0 ? null : i == 2 ? 731L : "existing-fact";
                assertThat(row.get(COLUMNS[i])).as(COLUMNS[i]).isEqualTo(expected);
            }
            assertThat(row).containsEntry("provider", "legacy-provider").containsEntry("model", "legacy-model").containsEntry("total_tokens", null);
            assertThat(flyway.migrate().migrationsExecuted).isZero();
        }
    }
    @Test
    void previouslyAppliedRepeatableGetsAnAppendOnlyUpgradeAndSupportsBaselineRollback() throws Exception {
        Path migrations = temp.resolve("applied-original"); Files.createDirectories(migrations);
        try (var files = Files.list(Path.of("src/main/resources/db/migration"))) {
            for (var f : files.filter(p -> p.getFileName().toString().startsWith("V")).toList()) Files.copy(f, migrations.resolve(f.getFileName()));
        }
        Path original = Path.of("src/test/resources/pr41-migrations/R__course_qa_model_usage.sql");
        Files.copy(original, migrations.resolve(original.getFileName()));
        try (var db = new SystemModelMySqlFixture("filesystem:" + migrations)) {
            long owner = db.user(); String task = db.task(owner);
            db.jdbc.update("INSERT INTO course_qa_record(task_id,user_id,question,answer,evidence_json,status,execution_snapshot_id,invocation_state,ai_call_record_id) VALUES (?,?,'existing','existing','[]','SUCCEEDED','exact-ref','RESPONSE_RECEIVED',731)", task, owner);
            Integer oldChecksum = db.jdbc.queryForObject("SELECT checksum FROM flyway_schema_history WHERE script='R__course_qa_model_usage.sql' AND success=1", Integer.class);
            Files.copy(Path.of("src/main/resources/db/migration/R__course_qa_model_usage.sql"), migrations.resolve(original.getFileName()), StandardCopyOption.REPLACE_EXISTING);
            var upgrade = Flyway.configure().dataSource(db.dataSource).locations("filesystem:" + migrations).outOfOrder(false).load();
            assertThat(upgrade.migrate().migrationsExecuted).isEqualTo(1);
            upgrade.validate();
            assertThat(db.jdbc.queryForList("SELECT checksum FROM flyway_schema_history WHERE script='R__course_qa_model_usage.sql' AND success=1 ORDER BY installed_rank", Integer.class))
                    .hasSize(2).contains(oldChecksum).doesNotHaveDuplicates();
            assertThat(db.jdbc.queryForMap("SELECT execution_snapshot_id,invocation_state,ai_call_record_id FROM course_qa_record WHERE task_id=?", task))
                    .containsEntry("execution_snapshot_id", "exact-ref").containsEntry("invocation_state", "RESPONSE_RECEIVED").containsEntry("ai_call_record_id", 731L);
            Path baseline = temp.resolve("rollback-baseline"), bundle = temp.resolve("rollback-bundle");
            Files.createDirectories(baseline); Files.createDirectories(bundle);
            try (var files = Files.list(migrations)) {
                for (var f : files.toList()) Files.copy(f, (f.getFileName().toString().startsWith("V") ? baseline : bundle).resolve(f.getFileName()));
            }
            var missingBundle = Flyway.configure().dataSource(db.dataSource).locations("filesystem:" + baseline).outOfOrder(false).load();
            assertThatThrownBy(missingBundle::validate).isInstanceOf(org.flywaydb.core.api.FlywayException.class);
            var rollback = Flyway.configure().dataSource(db.dataSource).locations("filesystem:" + baseline, "filesystem:" + bundle).outOfOrder(false).load();
            rollback.validate(); assertThat(rollback.migrate().migrationsExecuted).isZero();
            assertThat(rollback.info().current().getVersion().toString()).isEqualTo("25");
        }
    }

    @Test
    void aPreviouslyFailedRepeatableRemainsBlockedWithoutHistoryRepair() throws Exception {
        Path migrations = temp.resolve("failed-original"); Files.createDirectories(migrations);
        try (var files = Files.list(Path.of("src/main/resources/db/migration"))) {
            for (var f : files.filter(p -> p.getFileName().toString().startsWith("V")).toList()) Files.copy(f, migrations.resolve(f.getFileName()));
        }
        try (var db = new SystemModelMySqlFixture("filesystem:" + migrations)) {
            db.jdbc.execute("ALTER TABLE course_qa_record ADD COLUMN invocation_state VARCHAR(32) NULL");
            Files.copy(Path.of("src/test/resources/pr41-migrations/R__course_qa_model_usage.sql"), migrations.resolve("R__course_qa_model_usage.sql"));
            var original = Flyway.configure().dataSource(db.dataSource).locations("filesystem:" + migrations).outOfOrder(false).load();
            assertThatThrownBy(original::migrate).isInstanceOf(org.flywaydb.core.api.FlywayException.class);
            var failure = db.jdbc.queryForList("SELECT installed_rank,checksum,success FROM flyway_schema_history WHERE script='R__course_qa_model_usage.sql'");
            assertThat(failure).hasSize(1);
            Files.copy(Path.of("src/main/resources/db/migration/R__course_qa_model_usage.sql"), migrations.resolve("R__course_qa_model_usage.sql"), StandardCopyOption.REPLACE_EXISTING);
            var fixed = Flyway.configure().dataSource(db.dataSource).locations("filesystem:" + migrations).outOfOrder(false).load();
            assertThatThrownBy(fixed::migrate).isInstanceOf(org.flywaydb.core.api.FlywayException.class);
            assertThat(db.jdbc.queryForList("SELECT installed_rank,checksum,success FROM flyway_schema_history WHERE script='R__course_qa_model_usage.sql'"))
                    .isEqualTo(failure);
            assertThat(db.jdbc.queryForObject("SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='course_qa_record' AND column_name IN ('execution_snapshot_id','invocation_state','ai_call_record_id')", Integer.class)).isEqualTo(1);
        }
    }

    @ParameterizedTest
    @ValueSource(strings = {"execution_snapshot_id VARCHAR(32) NULL", "invocation_state VARCHAR(32) NOT NULL DEFAULT 'NOT_STARTED'", "ai_call_record_id BIGINT UNSIGNED NULL"})
    void incompatibleExistingDefinitionsFailBeforeAddingOrRewritingColumns(String definition) throws Exception {
        Path baseline = temp.resolve("incompatible"); Files.createDirectories(baseline);
        try (var files = Files.list(Path.of("src/main/resources/db/migration"))) {
            for (var f : files.filter(p -> p.getFileName().toString().startsWith("V")).toList()) Files.copy(f, baseline.resolve(f.getFileName()));
        }
        try (var db = new SystemModelMySqlFixture("filesystem:" + baseline)) {
            db.jdbc.execute("ALTER TABLE course_qa_record ADD COLUMN " + definition);
            Files.copy(Path.of("src/main/resources/db/migration/R__course_qa_model_usage.sql"), baseline.resolve("R__course_qa_model_usage.sql"));
            var flyway = Flyway.configure().dataSource(db.dataSource).locations("filesystem:" + baseline).outOfOrder(false).load();
            assertThatThrownBy(flyway::migrate).isInstanceOf(org.flywaydb.core.api.FlywayException.class);
            assertThat(db.jdbc.queryForObject("SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='course_qa_record' AND column_name IN ('execution_snapshot_id','invocation_state','ai_call_record_id')", Integer.class)).isEqualTo(1);
        }
    }

}
