package com.example.courselingo.systemmodel;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.Map;
import org.flywaydb.core.api.Location;
import org.flywaydb.core.api.configuration.ClassicConfiguration;
import org.flywaydb.core.internal.parser.ParsingContext;
import org.flywaydb.core.internal.resource.filesystem.FileSystemResource;
import org.flywaydb.core.internal.resolver.ChecksumCalculator;
import org.flywaydb.database.mysql.MySQLParser;

/** Offline parser/checksum only: no Spring application, datasource or migration execution. */
public final class FrozenMigrationCheck {
    public static void main(String[] args) throws Exception {
        var directory = Path.of(args[0]);
        var results = new ArrayList<Map<String, Object>>();
        try (var files = Files.list(directory)) {
            for (Path file : files.filter(p -> p.getFileName().toString().matches("V[0-9]+__.*\\.sql")).sorted().toList()) {
                var row = new LinkedHashMap<String, Object>();
                row.put("version", file.getFileName().toString().split("__")[0]);
                try {
                    var resource = new FileSystemResource(new Location("filesystem:" + directory),
                            file.toString(), StandardCharsets.UTF_8, false);
                    row.put("flyway_checksum", ChecksumCalculator.calculate(resource));
                    var config = new ClassicConfiguration();
                    config.setPlaceholderReplacement(false);
                    var parser = new MySQLParser(config, new ParsingContext());
                    int count = 0;
                    try (var statements = parser.parse(resource)) {
                        while (statements.hasNext()) { statements.next(); count++; }
                    }
                    row.put("statements", count);
                    row.put("parser_passed", count > 0);
                } catch (Throwable failure) {
                    row.put("parser_passed", false);
                    // Never propagate parser messages, SQL, filenames or stack traces.
                    row.put("fixed_causes", P21StartupDiagnostics.classify(failure));
                }
                results.add(row);
            }
        }
        System.out.println("P21_OFFLINE_MIGRATIONS " + new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(results));
    }
}
