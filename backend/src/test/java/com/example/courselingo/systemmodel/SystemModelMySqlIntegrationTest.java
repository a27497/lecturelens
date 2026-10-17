package com.example.courselingo.systemmodel;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.baomidou.mybatisplus.core.MybatisConfiguration;
import com.baomidou.mybatisplus.extension.spring.MybatisSqlSessionFactoryBean;
import com.example.courselingo.auth.entity.UserRole;
import com.example.courselingo.auth.mapper.UserAccountMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@EnabledIfEnvironmentVariable(named = "SYSTEM_MODEL_TEST_JDBC_URL", matches = ".+")
class SystemModelMySqlIntegrationTest {
    private final List<String> allocatedDatabases = new ArrayList<>();
    private String rootUrl;
    private String username;
    private String password;
    private String freshUrl;
    private String upgradedUrl;
    private long legacyUser;
    private String legacyTask;

    @BeforeAll
    void migrateFreshAndUpgradeSeparateDatabases() throws Exception {
        rootUrl = System.getenv("SYSTEM_MODEL_TEST_JDBC_URL");
        username = System.getenv().getOrDefault("SYSTEM_MODEL_TEST_MYSQL_USER", "root");
        password = System.getenv("SYSTEM_MODEL_TEST_MYSQL_PASSWORD");
        URI target = URI.create(rootUrl.substring("jdbc:".length()));
        assertThat(target.getHost()).isIn("127.0.0.1", "localhost");
        assertThat(target.getPath()).endsWith("_test");
        freshUrl = allocateDatabase("fresh");
        upgradedUrl = allocateDatabase("upgrade");
        flyway(freshUrl).migrate();
        Flyway.configure().dataSource(upgradedUrl, username, password).target("24").load().migrate();
        try (Connection connection = open(upgradedUrl)) {
            legacyUser = createUser(connection, "ACTIVE");
            legacyTask = createTask(connection, legacyUser);
        }
        flyway(upgradedUrl).migrate();
    }

    @AfterAll
    void removeOnlyAllocatedTestDatabases() throws SQLException {
        if (allocatedDatabases.isEmpty()) return;
        try (Connection connection = open(rootUrl); var statement = connection.createStatement()) {
            for (String database : allocatedDatabases) statement.execute("DROP DATABASE `" + database + "`");
        }
    }

    @Test
    void freshMigrationAndV24UpgradeBothValidate() throws Exception {
        for (String url : List.of(freshUrl, upgradedUrl)) {
            flyway(url).validate();
            assertThat(flyway(url).info().current().getVersion().toString()).isEqualTo("31");
            try (Connection connection = open(url)) {
                assertThat(scalar(connection, "SELECT current_version FROM system_model_config_state WHERE id=1")).isEqualTo("0");
                assertThat(scalar(connection, "SELECT config_sha256 = SHA2(config_json, 256) FROM system_model_config_version WHERE version=0"))
                    .isEqualTo("1");
                assertThat(scalar(connection, "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='system_model_probe_record'"))
                    .isEqualTo("0");
            }
        }
    }

    @Test
    void upgradeDefaultsExistingUsersWithoutChangingExistingTasks() throws Exception {
        try (Connection connection = open(upgradedUrl)) {
            assertThat(scalar(connection, "SELECT role FROM user_account WHERE id=" + legacyUser)).isEqualTo("USER");
            assertThat(scalar(connection, "SELECT status FROM analysis_task WHERE id='" + legacyTask + "'")).isEqualTo("SUCCEEDED");
            long newUser = createUser(connection, "ACTIVE");
            assertThat(scalar(connection, "SELECT role FROM user_account WHERE id=" + newUser)).isEqualTo("USER");
            assertThatThrownBy(() -> execute(connection, "UPDATE user_account SET role='ROOT' WHERE id=" + newUser))
                .isInstanceOf(SQLException.class);
        }
    }

    @Test
    void databaseRejectsUnknownProtocolInvalidCredentialPairsAndUnconnectedFusion() throws Exception {
        try (Connection connection = open(freshUrl)) {
            assertThatThrownBy(() -> execute(connection, "INSERT INTO system_model_provider (name, protocol, base_url) VALUES ('bad', 'ANTHROPIC', 'https://example.com')"))
                .isInstanceOf(SQLException.class);
            for (String values : List.of("NULL, '1234'", "'v1.test', NULL", "'plain-key', '1234'")) {
                assertThatThrownBy(() -> execute(connection, "INSERT INTO system_model_provider (name, protocol, base_url, api_key_ciphertext, key_last4) VALUES ('bad', 'OPENAI_CHAT', 'https://example.com', " + values + ")"))
                    .isInstanceOf(SQLException.class);
            }
            long provider = createProvider(connection, null, null);
            long model = insert(connection, "INSERT INTO system_model (provider_id, model_id, capabilities, parameters) VALUES (?, 'test-model', JSON_ARRAY('TEXT_CHAT'), JSON_OBJECT())", provider);
            assertThatThrownBy(() -> execute(connection, "INSERT INTO system_model_binding (feature_key, model_id) VALUES ('FUSION_SUMMARY', " + model + ")"))
                .isInstanceOf(SQLException.class);
            execute(connection, "INSERT INTO system_model_binding (feature_key, model_id) VALUES ('TRANSLATION_FULL_TEXT', " + model + ")");
            assertThatThrownBy(() -> execute(connection, "DELETE FROM system_model WHERE id=" + model)).isInstanceOf(SQLException.class);
            assertThatThrownBy(() -> execute(connection, "DELETE FROM system_model_provider WHERE id=" + provider)).isInstanceOf(SQLException.class);
        }
    }

    @Test
    void versionsAndAuditRejectUpdatesAndDeletes() throws Exception {
        try (Connection connection = open(freshUrl)) {
            for (String sql : List.of("UPDATE system_model_config_version SET reason='changed' WHERE version=0",
                "DELETE FROM system_model_config_version WHERE version=0")) {
                assertThatThrownBy(() -> execute(connection, sql)).isInstanceOf(SQLException.class);
            }
            long audit = insert(connection, "INSERT INTO system_model_audit (actor_type, action, object_type, object_id, safe_changes) VALUES ('TEST', 'CHECK', 'CONFIG', '0', '{}')");
            assertThatThrownBy(() -> execute(connection, "UPDATE system_model_audit SET action='changed' WHERE id=" + audit))
                .isInstanceOf(SQLException.class);
            assertThatThrownBy(() -> execute(connection, "DELETE FROM system_model_audit WHERE id=" + audit))
                .isInstanceOf(SQLException.class);
        }
    }

    @Test
    void credentialsPersistAsCiphertextAndPublicProjectionContainsOnlyMask() throws Exception {
        var cipher = new SystemModelSecretCipher(SystemModelSecretCipherTest.TEST_KEY);
        String secret = "test-only-database-secret-8472";
        try (Connection connection = open(freshUrl)) {
            long provider = createProvider(connection, null, null);
            var encrypted = cipher.encrypt(Long.toString(provider), secret);
            try (var update = connection.prepareStatement("UPDATE system_model_provider SET api_key_ciphertext=?, key_last4=? WHERE id=?")) {
                update.setString(1, encrypted.ciphertext());
                update.setString(2, encrypted.keyLast4());
                update.setLong(3, provider);
                update.executeUpdate();
            }
            String stored = scalar(connection, "SELECT api_key_ciphertext FROM system_model_provider WHERE id=" + provider);
            assertThat(stored).isNotEqualTo(secret).doesNotContain(secret);
            assertThat(cipher.decrypt(Long.toString(provider), stored)).isEqualTo(secret);
            assertThat(scalar(connection, "SELECT key_last4 FROM system_model_provider WHERE id=" + provider)).isEqualTo("8472");
            String publicJson = new ObjectMapper().writeValueAsString(encrypted);
            assertThat(publicJson).doesNotContain(secret, stored).contains("8472", "hasKey");
        }
    }

    @Test
    void offlineGrantAndRevokeCommitRoleWithAuditAndMybatisMapsRole() throws Exception {
        try (Connection connection = open(upgradedUrl)) {
            long user = createUser(connection, "ACTIVE");
            assertThat(SystemModelAdminCli.changeRole(connection, user, UserRole.ADMIN)).isTrue();
            assertThat(SystemModelAdminCli.changeRole(connection, user, UserRole.ADMIN)).isFalse();
            assertThat(scalar(connection, "SELECT COUNT(*) FROM system_model_audit WHERE object_type='USER' AND object_id='" + user + "'"))
                .isEqualTo("1");
            var configuration = new MybatisConfiguration();
            configuration.addMapper(UserAccountMapper.class);
            var factory = new MybatisSqlSessionFactoryBean();
            factory.setDataSource(new DriverManagerDataSource(upgradedUrl, username, password));
            factory.setConfiguration(configuration);
            try (var session = factory.getObject().openSession()) {
                assertThat(session.getMapper(UserAccountMapper.class).selectById(user).getRole()).isEqualTo(UserRole.ADMIN);
            }
            assertThat(SystemModelAdminCli.changeRole(connection, user, UserRole.USER)).isTrue();
            assertThat(scalar(connection, "SELECT role FROM user_account WHERE id=" + user)).isEqualTo("USER");
            assertThat(scalar(connection, "SELECT COUNT(*) FROM system_model_audit WHERE object_type='USER' AND object_id='" + user + "'"))
                .isEqualTo("2");
        }
    }

    @Test
    void roleChangeRollsBackIfAuditCannotBeWritten() throws Exception {
        try (Connection connection = open(upgradedUrl)) {
            long user = createUser(connection, "ACTIVE");
            execute(connection, "CREATE TRIGGER phase1_reject_audit BEFORE INSERT ON system_model_audit FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='test rejection'");
            try {
                assertThatThrownBy(() -> SystemModelAdminCli.changeRole(connection, user, UserRole.ADMIN)).isInstanceOf(SQLException.class);
                assertThat(scalar(connection, "SELECT role FROM user_account WHERE id=" + user)).isEqualTo("USER");
            } finally {
                execute(connection, "DROP TRIGGER phase1_reject_audit");
            }
            long disabled = createUser(connection, "DISABLED");
            assertThatThrownBy(() -> SystemModelAdminCli.changeRole(connection, disabled, UserRole.ADMIN)).isInstanceOf(IllegalStateException.class);
            assertThat(scalar(connection, "SELECT role FROM user_account WHERE id=" + disabled)).isEqualTo("USER");
        }
    }

    @Test
    void snapshotsReferenceVersionWithoutCredentialColumnsAndFollowTaskDeletion() throws Exception {
        try (Connection connection = open(upgradedUrl)) {
            long user = createUser(connection, "ACTIVE");
            String task = createTask(connection, user);
            try (var statement = connection.prepareStatement("INSERT INTO system_model_execution_snapshot (id, task_id, user_id, operation_type, operation_id, config_version, resolved_config_json) VALUES (?, ?, ?, 'PIPELINE', ?, 0, '{}')")) {
                statement.setString(1, task);
                statement.setString(2, task);
                statement.setLong(3, user);
                statement.setString(4, task);
                statement.executeUpdate();
            }
            try (var columns = connection.getMetaData().getColumns(connection.getCatalog(), null, "system_model_execution_snapshot", null)) {
                while (columns.next()) assertThat(columns.getString("COLUMN_NAME")).doesNotContain("cipher", "secret", "credential");
            }
            execute(connection, "DELETE FROM analysis_task WHERE id='" + task + "'");
            assertThat(scalar(connection, "SELECT COUNT(*) FROM system_model_execution_snapshot WHERE task_id='" + task + "'")).isEqualTo("0");
            assertThat(scalar(connection, "SELECT COUNT(*) FROM system_model_config_version WHERE version=0")).isEqualTo("1");
        }
    }

    @Test
    void cliEntryPointReturnsSafeErrorsAndCanGrantAnExistingAccount() throws Exception {
        var output = new ByteArrayOutputStream();
        var errors = new ByteArrayOutputStream();
        Map<String, String> environment = Map.of("MYSQL_JDBC_URL", upgradedUrl, "MYSQL_USERNAME", username, "MYSQL_PASSWORD", password);
        try (Connection connection = open(upgradedUrl)) {
            long user = createUser(connection, "ACTIVE");
            assertThat(SystemModelAdminCli.execute(new String[] {"grant", "--user-id", Long.toString(user)}, environment,
                new PrintStream(output), new PrintStream(errors))).isZero();
            assertThat(output.toString(StandardCharsets.UTF_8)).contains("role=ADMIN");
            assertThat(errors.size()).isZero();
            assertThat(SystemModelAdminCli.execute(new String[] {"grant", "--user-id", "9223372036854775808"}, environment,
                new PrintStream(output), new PrintStream(errors))).isEqualTo(1);
            assertThat(errors.toString(StandardCharsets.UTF_8)).isEqualTo("ADMIN_COMMAND_FAILED\n");
            assertThat(SystemModelAdminCli.execute(new String[] {"grant", "--user-id", "1;DROP TABLE user_account"}, environment,
                new PrintStream(output), new PrintStream(errors))).isEqualTo(2);
        }
    }

    private String allocateDatabase(String scenario) throws SQLException {
        String name = "lecturelens_p14_" + scenario + "_" + UUID.randomUUID().toString().replace("-", "");
        try (Connection connection = open(rootUrl)) {
            execute(connection, "CREATE DATABASE `" + name + "` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci");
        }
        allocatedDatabases.add(name);
        int start = rootUrl.indexOf('/', "jdbc:mysql://".length());
        int query = rootUrl.indexOf('?');
        return rootUrl.substring(0, start + 1) + name + (query < 0 ? "" : rootUrl.substring(query));
    }

    private Flyway flyway(String url) { return Flyway.configure().dataSource(url, username, password).load(); }
    private Connection open(String url) throws SQLException { return DriverManager.getConnection(url, username, password); }

    private long createUser(Connection connection, String status) throws SQLException {
        return insert(connection, "INSERT INTO user_account (email, password_hash, status) VALUES (?, 'test-only-unused-hash', ?)",
            UUID.randomUUID() + "@example.invalid", status);
    }

    private String createTask(Connection connection, long user) throws SQLException {
        String task = UUID.randomUUID().toString();
        try (var upload = connection.prepareStatement("INSERT INTO upload_session (id, user_id, filename, ext, total_chunks, chunk_size_bytes, size_bytes, file_md5, status, storage_type, object_key) VALUES (?, ?, 'test.mp4', 'mp4', 1, 1, 1, 'test', 'STORED', 'MINIO', 'test')")) {
            upload.setString(1, task); upload.setLong(2, user); upload.executeUpdate();
        }
        try (var statement = connection.prepareStatement("INSERT INTO analysis_task (id, user_id, upload_id, target_language, status) VALUES (?, ?, ?, 'zh-CN', 'SUCCEEDED')")) {
            statement.setString(1, task); statement.setLong(2, user); statement.setString(3, task); statement.executeUpdate();
        }
        return task;
    }

    private long createProvider(Connection connection, String ciphertext, String last4) throws SQLException {
        return insert(connection, "INSERT INTO system_model_provider (name, protocol, base_url, api_key_ciphertext, key_last4) VALUES ('test', 'OPENAI_CHAT', 'https://example.com', ?, ?)", ciphertext, last4);
    }

    private static long insert(Connection connection, String sql, Object... values) throws SQLException {
        try (var statement = connection.prepareStatement(sql, java.sql.Statement.RETURN_GENERATED_KEYS)) {
            for (int index = 0; index < values.length; index++) statement.setObject(index + 1, values[index]);
            statement.executeUpdate();
            try (var keys = statement.getGeneratedKeys()) { keys.next(); return keys.getLong(1); }
        }
    }

    private static void execute(Connection connection, String sql) throws SQLException {
        try (var statement = connection.createStatement()) { statement.execute(sql); }
    }

    private static String scalar(Connection connection, String sql) throws SQLException {
        try (var statement = connection.createStatement(); var result = statement.executeQuery(sql)) {
            result.next(); return result.getString(1);
        }
    }
}
