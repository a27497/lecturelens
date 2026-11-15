package com.example.courselingo.systemmodel;

import java.sql.SQLException;
import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.List;

/** Proposed next-start instrumentation; never print throwable messages or stacks. */
public final class P21StartupDiagnostics {
    static List<String> classify(Throwable failure) {
        var rows = new ArrayList<String>();
        var seen = new IdentityHashMap<Throwable, Boolean>();
        for (Throwable cause = failure; cause != null && rows.size() < 16 && seen.put(cause, true) == null;
                cause = cause.getCause()) {
            String kind = switch (cause.getClass().getName()) {
                case "org.springframework.beans.factory.BeanCreationException" -> "BEAN_CREATION";
                case "org.springframework.beans.factory.UnsatisfiedDependencyException" -> "DEPENDENCY";
                case "org.springframework.beans.BeanInstantiationException" -> "BEAN_INSTANTIATION";
                case "org.springframework.beans.factory.NoSuchBeanDefinitionException" -> "MISSING_BEAN";
                case "org.springframework.beans.factory.NoUniqueBeanDefinitionException" -> "AMBIGUOUS_BEAN";
                case "org.springframework.boot.context.properties.ConfigurationPropertiesBindException" -> "CONFIGURATION_BINDING";
                case "org.springframework.boot.context.properties.bind.BindException" -> "PROPERTY_BINDING";
                case "org.springframework.boot.context.properties.bind.validation.BindValidationException" -> "PROPERTY_VALIDATION";
                case "org.springframework.context.ApplicationContextException" -> "CONTEXT";
                case "org.springframework.boot.web.server.WebServerException" -> "WEB_SERVER";
                case "java.net.BindException" -> "BIND";
                case "java.net.ConnectException" -> "CONNECT";
                case "java.net.SocketTimeoutException" -> "SOCKET_TIMEOUT";
                case "java.lang.NoClassDefFoundError", "java.lang.ClassNotFoundException" -> "MISSING_CLASS";
                case "java.lang.NoSuchMethodError" -> "MISSING_METHOD";
                case "java.lang.NoSuchMethodException" -> "MISSING_REFLECTIVE_METHOD";
                case "java.lang.IllegalArgumentException" -> "ILLEGAL_ARGUMENT";
                case "java.lang.IllegalStateException" -> "ILLEGAL_STATE";
                case "org.flywaydb.core.api.FlywayException", "org.flywaydb.core.api.exception.FlywayValidateException" -> "FLYWAY";
                default -> cause instanceof SQLException ? "SQL" : "OTHER";
            };
            String row = "P21_STARTUP_CAUSE index=" + rows.size() + " kind=" + kind;
            if (cause instanceof SQLException sql) {
                String state = sql.getSQLState();
                if (state != null && state.matches("[A-Z0-9]{5}")) row += " sqlState=" + state;
                row += " vendorCode=" + sql.getErrorCode();
            }
            rows.add(row);
        }
        return rows;
    }

    static void selftest() {
        String privateText = "SYNTHETIC_PRIVATE_CONFIGURATION_AND_RESPONSE";
        var sql = new SQLException(privateText, "28000", 1045);
        var failure = new org.springframework.beans.factory.BeanCreationException(privateText, sql);
        var rows = classify(failure);
        if (rows.size() != 2 || !rows.get(0).endsWith("kind=BEAN_CREATION")
                || !rows.get(1).endsWith("kind=SQL sqlState=28000 vendorCode=1045")
                || rows.toString().contains(privateText)) throw new AssertionError();
        var cycle = new IllegalStateException(privateText);
        var other = new IllegalArgumentException(privateText, cycle);
        cycle.initCause(other);
        if (classify(cycle).size() != 2) throw new AssertionError();
        var invalidState = new SQLException(privateText, privateText, 7);
        if (classify(invalidState).toString().contains(privateText)) throw new AssertionError();
        var instantiation = new org.springframework.beans.BeanInstantiationException(Object.class, privateText,
                new NoSuchMethodException(privateText));
        var constructorRows = classify(instantiation);
        if (!constructorRows.get(0).endsWith("kind=BEAN_INSTANTIATION")
                || !constructorRows.get(1).endsWith("kind=MISSING_REFLECTIVE_METHOD")
                || constructorRows.toString().contains(privateText)) throw new AssertionError();
        System.out.println("P21_STARTUP_DIAGNOSTICS_SELFTEST_PASS sql_classification,message_exclusion,cycle_bound,invalid_state_exclusion");
    }

    public static void main(String[] args) {
        if (args.length == 1 && args[0].equals("selftest-startup-diagnostics")) {
            selftest();
            return;
        }
        try {
            P21Bootstrap.main(args);
        } catch (Throwable failure) {
            for (String row : classify(failure)) System.err.println(row);
            System.exit(45);
        }
    }
}
