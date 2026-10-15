package com.example.courselingo.systemmodel;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.Map;
import java.util.Set;

public final class SystemModelCommands {
    private SystemModelCommands() {}

    public record Provider(
            long expectedVersion,
            String name,
            SystemModelProtocol protocol,
            String baseUrl,
            boolean enabled,
            @JsonProperty(access = JsonProperty.Access.WRITE_ONLY) String apiKey,
            boolean clearKey) {
        @Override
        public String toString() {
            return "ProviderCommand[redacted]";
        }
    }

    public record Model(
            long expectedVersion,
            String model,
            Set<String> capabilities,
            SystemModelViews.Parameters parameters,
            boolean enabled) {}

    public record Bindings(long expectedVersion, Map<String, Long> bindings) {}

    public record Rollback(long expectedVersion, String feature, long targetVersion) {}
}
