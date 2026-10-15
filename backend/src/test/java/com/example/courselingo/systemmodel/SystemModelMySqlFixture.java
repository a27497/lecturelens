package com.example.courselingo.systemmodel;

import org.flywaydb.core.Flyway;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import java.net.URI;
import java.sql.DriverManager;
import java.util.UUID;

final class SystemModelMySqlFixture implements AutoCloseable {
    final String base = System.getenv("SYSTEM_MODEL_TEST_JDBC_URL");
    final String username = System.getenv().getOrDefault("SYSTEM_MODEL_TEST_MYSQL_USER", "root");
    final String password = System.getenv("SYSTEM_MODEL_TEST_MYSQL_PASSWORD");
    final String database =
            "lecturelens_p14_phase2_" + UUID.randomUUID().toString().replace("-", "");
    final String url;
    final DriverManagerDataSource dataSource;
    final JdbcTemplate jdbc;
    final DataSourceTransactionManager transactions;

    SystemModelMySqlFixture() throws Exception {
        var uri = URI.create(base.substring(5));
        if (!java.util.Set.of("localhost", "127.0.0.1").contains(uri.getHost())
                || !uri.getPath().endsWith("_test"))
            throw new IllegalArgumentException("Isolated local test database required");
        try (var connection = DriverManager.getConnection(base, username, password);
                var statement = connection.createStatement()) {
            statement.execute(
                    "CREATE DATABASE `"
                            + database
                            + "` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci");
        }
        int start = base.indexOf('/', "jdbc:mysql://".length()), query = base.indexOf('?');
        url = base.substring(0, start + 1) + database + (query < 0 ? "" : base.substring(query));
        dataSource = new DriverManagerDataSource(url, username, password);
        jdbc = new JdbcTemplate(dataSource);
        transactions = new DataSourceTransactionManager(dataSource);
        Flyway.configure().dataSource(dataSource).load().migrate();
    }

    long user() {
        String email = UUID.randomUUID() + "@example.invalid";
        jdbc.update(
                "INSERT INTO user_account (email,password_hash,status) VALUES"
                    + " (?,'unused-test-hash','ACTIVE')",
                email);
        return jdbc.queryForObject("SELECT id FROM user_account WHERE email=?", Long.class, email);
    }

    String task(long user) {
        String id = UUID.randomUUID().toString();
        jdbc.update(
                "INSERT INTO upload_session"
                    + " (id,user_id,filename,ext,total_chunks,chunk_size_bytes,size_bytes,file_md5,status,storage_type,object_key)"
                    + " VALUES (?,?,'test.mp4','mp4',1,1,1,'test','STORED','MINIO','test')",
                id,
                user);
        jdbc.update(
                "INSERT INTO analysis_task (id,user_id,upload_id,target_language,status) VALUES"
                    + " (?,?,?,'zh-CN','SUCCEEDED')",
                id,
                user,
                id);
        return id;
    }

    @Override
    public void close() throws Exception {
        try (var connection = DriverManager.getConnection(base, username, password);
                var statement = connection.createStatement()) {
            statement.execute("DROP DATABASE `" + database + "`");
        }
    }
}
