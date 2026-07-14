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
class AuthSchemaMigrationTest {

    private static final Path AUTH_MIGRATION = Path.of(
        "src",
        "main",
        "resources",
        "db",
        "migration",
        "V1__init_user_and_auth.sql"
    );

    @Autowired
    private Environment environment;

    @Autowired
    private ObjectProvider<Flyway> flywayProvider;

    @Test
    void authMigrationFileExists() {
        assertThat(AUTH_MIGRATION).isRegularFile();
    }

    @Test
    void authMigrationCreatesUserAccountAndRefreshTokenTables() throws IOException {
        String sql = readMigrationSql();

        assertThat(sql).contains("CREATE TABLE IF NOT EXISTS user_account");
        assertThat(sql).contains("CREATE TABLE IF NOT EXISTS refresh_token");
    }

    @Test
    void authMigrationDefinesRequiredIndexesAndForeignKey() throws IOException {
        String sql = readMigrationSql();

        assertThat(sql).contains("UNIQUE KEY uk_user_account_email (email)");
        assertThat(sql).contains("CONSTRAINT fk_refresh_token_user_id");
        assertThat(sql).contains("FOREIGN KEY (user_id) REFERENCES user_account (id)");
        assertThat(sql).contains("ON DELETE CASCADE");
        assertThat(sql).contains("ON UPDATE RESTRICT");
    }

    @Test
    void authMigrationDoesNotSeedUserCredentialsOrTokens() throws IOException {
        String normalizedSql = readMigrationSql().toLowerCase();

        assertThat(normalizedSql).doesNotContain("insert into");
        assertThat(normalizedSql).doesNotContain("example.com");
        assertThat(normalizedSql).doesNotContain("plain_password");
        assertThat(normalizedSql).doesNotContain("raw_password");
        assertThat(normalizedSql).doesNotContain("raw_token");
        assertThat(normalizedSql).doesNotContain("token_value");
    }

    @Test
    void defaultContextStillStartsWithoutLocalMysql() {
        assertThat(environment.getProperty("spring.flyway.enabled")).isEqualTo("false");
        assertThat(flywayProvider.getIfAvailable()).isNull();
    }

    private String readMigrationSql() throws IOException {
        return Files.readString(AUTH_MIGRATION, StandardCharsets.UTF_8);
    }
}
