package com.example.courselingo.learning;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;

class LearningPackageMigrationTest {

    private static final Path MIGRATION = Path.of(
        "src",
        "main",
        "resources",
        "db",
        "migration",
        "V6__create_learning_package_table.sql"
    );

    @Test
    void d9MigrationFileExistsAndIsLoadableFromFlywayClasspathLocation() throws IOException {
        assertThat(MIGRATION).isRegularFile();
        Resource[] resources = new PathMatchingResourcePatternResolver()
            .getResources("classpath:db/migration/V6__create_learning_package_table.sql");

        assertThat(resources).hasSize(1);
        assertThat(resources[0].exists()).isTrue();
    }

    @Test
    void d9MigrationDefinesLearningPackageColumnsConstraintsAndIndexes() throws IOException {
        String sql = readMigrationSql();

        assertThat(sql).contains("CREATE TABLE IF NOT EXISTS learning_package");
        assertThat(sql).contains("id BIGINT NOT NULL AUTO_INCREMENT");
        assertThat(sql).contains("task_id VARCHAR(64) NOT NULL");
        assertThat(sql).contains("user_id BIGINT NOT NULL");
        assertThat(sql).contains("source_language VARCHAR(32) NOT NULL");
        assertThat(sql).contains("target_language VARCHAR(32) NOT NULL");
        assertThat(sql).contains("title VARCHAR(255) NOT NULL");
        assertThat(sql).contains("summary TEXT NOT NULL");
        assertThat(sql).contains("key_points_json JSON NOT NULL");
        assertThat(sql).contains("glossary_json JSON NOT NULL");
        assertThat(sql).contains("qa_json JSON NOT NULL");
        assertThat(sql).contains("provider VARCHAR(64) NULL");
        assertThat(sql).contains("schema_version VARCHAR(32) NOT NULL");
        assertThat(sql).contains("created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)");
        assertThat(sql).contains("updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)");
        assertThat(sql).contains("PRIMARY KEY (id)");
        assertThat(sql).contains("UNIQUE KEY uk_learning_package_task_user_lang (task_id, user_id, target_language)");
        assertThat(sql).contains("KEY idx_learning_package_task_user (task_id, user_id)");
        assertThat(sql).contains("KEY idx_learning_package_user_created (user_id, created_at)");
        assertThat(sql).contains("CONSTRAINT fk_learning_package_task_id");
        assertThat(sql).contains("FOREIGN KEY (task_id) REFERENCES analysis_task (id)");
        assertThat(sql).contains("CONSTRAINT fk_learning_package_user_id");
        assertThat(sql).contains("FOREIGN KEY (user_id) REFERENCES user_account (id)");
    }

    @Test
    void d9MigrationDoesNotCreateArtifactMetadataAiCallOrSecretFields() throws IOException {
        String normalizedSql = readMigrationSql().toLowerCase();

        assertThat(normalizedSql).doesNotContain("artifact");
        assertThat(normalizedSql).doesNotContain("object_key");
        assertThat(normalizedSql).doesNotContain("metadata");
        assertThat(normalizedSql).doesNotContain("raw_response");
        assertThat(normalizedSql).doesNotContain("authorization");
        assertThat(normalizedSql).doesNotContain("access_token");
        assertThat(normalizedSql).doesNotContain("refresh_token");
        assertThat(normalizedSql).doesNotContain("api_key");
        assertThat(normalizedSql).doesNotContain("secret");
        assertThat(normalizedSql).doesNotContain("ai_call_record");
        assertThat(normalizedSql).doesNotContain("insert into");
        assertThat(normalizedSql).doesNotContain("c:\\");
        assertThat(normalizedSql).doesNotContain("/users/");
        assertThat(normalizedSql).doesNotContain("/home/");
    }

    private String readMigrationSql() throws IOException {
        return Files.readString(MIGRATION, StandardCharsets.UTF_8);
    }
}
