package com.example.courselingo.artifact;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;

class ArtifactFileMigrationTest {

    private static final Path MIGRATION = Path.of(
        "src",
        "main",
        "resources",
        "db",
        "migration",
        "V7__create_artifact_file_table.sql"
    );

    @Test
    void d10MigrationFileExistsAndIsLoadableFromFlywayClasspathLocation() throws IOException {
        assertThat(MIGRATION).isRegularFile();
        Resource[] resources = new PathMatchingResourcePatternResolver()
            .getResources("classpath:db/migration/V7__create_artifact_file_table.sql");

        assertThat(resources).hasSize(1);
        assertThat(resources[0].exists()).isTrue();
    }

    @Test
    void d10MigrationDefinesArtifactFileColumnsConstraintsAndIndexes() throws IOException {
        String sql = readMigrationSql();

        assertThat(sql).contains("CREATE TABLE IF NOT EXISTS artifact_file");
        assertThat(sql).contains("id BIGINT NOT NULL AUTO_INCREMENT");
        assertThat(sql).contains("task_id VARCHAR(64) NOT NULL");
        assertThat(sql).contains("user_id BIGINT NOT NULL");
        assertThat(sql).contains("artifact_type VARCHAR(32) NOT NULL");
        assertThat(sql).contains("language VARCHAR(32) NOT NULL");
        assertThat(sql).contains("file_name VARCHAR(255) NOT NULL");
        assertThat(sql).contains("content_type VARCHAR(128) NOT NULL");
        assertThat(sql).contains("storage_backend VARCHAR(32) NOT NULL");
        assertThat(sql).contains("object_key VARCHAR(512) NOT NULL");
        assertThat(sql).contains("size_bytes BIGINT NOT NULL");
        assertThat(sql).contains("sha256 VARCHAR(64) NOT NULL");
        assertThat(sql).contains("created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)");
        assertThat(sql).contains("updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)");
        assertThat(sql).contains("PRIMARY KEY (id)");
        assertThat(sql).contains("UNIQUE KEY uk_artifact_file_task_user_type_lang (task_id, user_id, artifact_type, language)");
        assertThat(sql).contains("UNIQUE KEY uk_artifact_file_object_key (object_key)");
        assertThat(sql).contains("KEY idx_artifact_file_task_user (task_id, user_id)");
        assertThat(sql).contains("KEY idx_artifact_file_user_created (user_id, created_at)");
        assertThat(sql).contains("CONSTRAINT fk_artifact_file_task_id");
        assertThat(sql).contains("FOREIGN KEY (task_id) REFERENCES analysis_task (id)");
        assertThat(sql).contains("CONSTRAINT fk_artifact_file_user_id");
        assertThat(sql).contains("FOREIGN KEY (user_id) REFERENCES user_account (id)");
    }

    @Test
    void d10MigrationDoesNotCreateAiCallMetadataOrSecretFields() throws IOException {
        String normalizedSql = readMigrationSql().toLowerCase();

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
