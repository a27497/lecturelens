package com.example.courselingo.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

@SpringBootTest
class UploadSessionMigrationTest {

    private static final Path UPLOAD_SESSION_MIGRATION = Path.of(
        "src",
        "main",
        "resources",
        "db",
        "migration",
        "V2__init_upload_session.sql"
    );

    @Autowired
    private Environment environment;

    @Autowired
    private ObjectProvider<Flyway> flywayProvider;

    @Test
    void uploadSessionMigrationFileExists() {
        assertThat(UPLOAD_SESSION_MIGRATION).isRegularFile();
    }

    @Test
    void uploadSessionMigrationCreatesUploadSessionTableAndRequiredColumns() throws IOException {
        String sql = readMigrationSql();

        assertThat(sql).contains("CREATE TABLE IF NOT EXISTS upload_session");
        assertThat(sql).contains("id VARCHAR(64) NOT NULL COMMENT");
        assertThat(sql).contains("user_id BIGINT NOT NULL COMMENT");
        assertThat(sql).contains("filename VARCHAR(255) NOT NULL COMMENT");
        assertThat(sql).contains("ext VARCHAR(32) NOT NULL COMMENT");
        assertThat(sql).contains("total_chunks INT NOT NULL COMMENT");
        assertThat(sql).contains("chunk_size_bytes BIGINT NOT NULL COMMENT");
        assertThat(sql).contains("size_bytes BIGINT NOT NULL COMMENT");
        assertThat(sql).contains("file_md5 VARCHAR(64) NOT NULL COMMENT");
        assertThat(sql).contains("status VARCHAR(32) NOT NULL COMMENT");
        assertThat(sql).contains("storage_type VARCHAR(32) NOT NULL COMMENT");
        assertThat(sql).contains("object_key VARCHAR(255) NOT NULL COMMENT");
        assertThat(sql).contains("created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT");
        assertThat(sql).contains("updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT");
    }

    @Test
    void uploadSessionMigrationDefinesPrimaryKeyForeignKeyAndIndexes() throws IOException {
        String sql = readMigrationSql();

        assertThat(sql).contains("PRIMARY KEY (id)");
        assertThat(sql).contains("CONSTRAINT fk_upload_session_user_id");
        assertThat(sql).contains("FOREIGN KEY (user_id) REFERENCES user_account (id)");
        assertThat(sql).contains("ON DELETE CASCADE");
        assertThat(sql).contains("ON UPDATE RESTRICT");
        assertThat(sql).contains("KEY idx_upload_session_user_created (user_id, created_at)");
        assertThat(sql).contains("KEY idx_upload_session_md5 (file_md5)");
        assertThat(sql).contains("KEY idx_upload_session_user_status_created (user_id, status, created_at)");
    }

    @Test
    void uploadSessionMigrationUsesMysqlUtf8mb4AndDocumentsTable() throws IOException {
        String sql = readMigrationSql();

        assertThat(sql).contains("ENGINE=InnoDB");
        assertThat(sql).contains("DEFAULT CHARSET=utf8mb4");
        assertThat(sql).contains("COLLATE=utf8mb4_unicode_ci");
        assertThat(sql).contains("COMMENT='上传会话表'");
    }

    @Test
    void uploadSessionMigrationDoesNotSeedDataOrLeakLocalPaths() throws IOException {
        String normalizedSql = readMigrationSql().toLowerCase();

        assertThat(normalizedSql).doesNotContain("insert into");
        assertThat(normalizedSql).doesNotContain("c:\\");
        assertThat(normalizedSql).doesNotContain("/users/");
        assertThat(normalizedSql).doesNotContain("/home/");
        assertThat(normalizedSql).doesNotContain("demo.mp4");
        assertThat(normalizedSql).doesNotContain("example.mp4");
        assertThat(normalizedSql).doesNotContain("uploads/");
        assertThat(normalizedSql).doesNotContain("real-object-key");
    }

    @Test
    void defaultContextStillStartsWithoutLocalMysql() {
        assertThat(environment.getProperty("spring.flyway.enabled")).isEqualTo("false");
        assertThat(flywayProvider.getIfAvailable()).isNull();
    }

    private String readMigrationSql() throws IOException {
        return Files.readString(UPLOAD_SESSION_MIGRATION, StandardCharsets.UTF_8);
    }
}
