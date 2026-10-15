package com.example.courselingo.systemmodel;

import com.example.courselingo.auth.entity.UserRole;
import java.io.PrintStream;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.Map;

/** Offline role maintenance: only a deployment operator with MySQL credentials can invoke this entry point. */
public final class SystemModelAdminCli {
    private SystemModelAdminCli() { }

    public static void main(String[] args) {
        System.exit(execute(args, System.getenv(), System.out, System.err));
    }

    static int execute(String[] args, Map<String, String> environment, PrintStream output, PrintStream errors) {
        if (args.length != 3 || !"--user-id".equals(args[1]) || !args[2].matches("[1-9][0-9]{0,18}")
            || !("grant".equals(args[0]) || "revoke".equals(args[0]))) {
            errors.println("Usage: system-model-admin.sh grant|revoke --user-id <positive-id>");
            return 2;
        }
        String url = environment.get("MYSQL_JDBC_URL");
        String username = environment.get("MYSQL_USERNAME");
        String password = environment.get("MYSQL_PASSWORD");
        if (url == null || !url.startsWith("jdbc:mysql://") || username == null || password == null) {
            errors.println("MYSQL_CONFIGURATION_MISSING");
            return 2;
        }
        try (Connection connection = DriverManager.getConnection(url, username, password)) {
            long userId = Long.parseLong(args[2]);
            UserRole role = "grant".equals(args[0]) ? UserRole.ADMIN : UserRole.USER;
            boolean changed = changeRole(connection, userId, role);
            output.println((changed ? "UPDATED" : "UNCHANGED") + " userId=" + userId + " role=" + role);
            return 0;
        } catch (SQLException | RuntimeException exception) {
            // JDBC errors can contain deployment credentials; print a fixed category without message or cause.
            errors.println("ADMIN_COMMAND_FAILED");
            return 1;
        }
    }

    static boolean changeRole(Connection connection, long userId, UserRole desiredRole) throws SQLException {
        if (!connection.getAutoCommit()) throw new IllegalStateException("Dedicated connection required");
        connection.setAutoCommit(false);
        try {
            String previousRole;
            try (var query = connection.prepareStatement("SELECT role, status FROM user_account WHERE id = ? FOR UPDATE")) {
                query.setLong(1, userId);
                try (var rows = query.executeQuery()) {
                    if (!rows.next() || !"ACTIVE".equals(rows.getString("status"))) {
                        throw new IllegalStateException("Active account required");
                    }
                    previousRole = UserRole.valueOf(rows.getString("role")).name();
                }
            }
            if (desiredRole.name().equals(previousRole)) {
                connection.commit();
                return false;
            }
            try (var update = connection.prepareStatement("UPDATE user_account SET role = ? WHERE id = ?")) {
                update.setString(1, desiredRole.name());
                update.setLong(2, userId);
                if (update.executeUpdate() != 1) throw new SQLException("Account update failed");
            }
            try (var audit = connection.prepareStatement("""
                INSERT INTO system_model_audit (actor_type, action, object_type, object_id, safe_changes)
                VALUES ('LOCAL_CLI', ?, 'USER', ?, ?)
                """)) {
                audit.setString(1, desiredRole == UserRole.ADMIN ? "ROLE_GRANTED" : "ROLE_REVOKED");
                audit.setString(2, Long.toString(userId));
                audit.setString(3, "{\"beforeRole\":\"" + previousRole + "\",\"afterRole\":\"" + desiredRole.name() + "\"}");
                audit.executeUpdate();
            }
            connection.commit();
            return true;
        } catch (SQLException | RuntimeException exception) {
            connection.rollback();
            throw exception;
        } finally {
            connection.setAutoCommit(true);
        }
    }
}
