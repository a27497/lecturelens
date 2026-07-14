package com.example.courselingo.infrastructure;

import org.flywaydb.core.Flyway;
import org.flywaydb.core.api.output.MigrateResult;

public final class DatabaseMigrationRunner {

    private DatabaseMigrationRunner() {
    }

    public static void main(String[] args) {
        String jdbcUrl = requiredEnv("MYSQL_JDBC_URL");
        String username = requiredEnv("MYSQL_USERNAME");
        String password = requiredEnv("MYSQL_PASSWORD");

        Flyway flyway = Flyway.configure()
            .dataSource(jdbcUrl, username, password)
            .locations("classpath:db/migration")
            .validateOnMigrate(true)
            .baselineOnMigrate(false)
            .load();

        MigrateResult result = flyway.migrate();
        System.out.printf(
            "[db-migration] flywayResult=%s migrationsExecuted=%d%n",
            result.success ? "success" : "failure",
            result.migrationsExecuted
        );
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(name + " missing");
        }
        return value;
    }
}
