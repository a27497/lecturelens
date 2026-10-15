package com.example.courselingo.systemmodel;

import com.fasterxml.jackson.annotation.JsonIgnore;

import java.util.List;
import java.util.Map;
import java.util.Set;

record SystemModelStoredConfig(
        List<Provider> providers,
        List<Model> models,
        Map<String, Long> bindings,
        Map<String, Default> defaults,
        @JsonIgnore String environmentFingerprint,
        boolean fullTextTranslation) {
    record Provider(
            long id,
            String name,
            SystemModelProtocol protocol,
            String baseUrl,
            boolean enabled,
            @JsonIgnore String ciphertext,
            String keyLast4) {
        @Override
        public String toString() {
            return "StoredProvider[redacted]";
        }
    }

    record Model(
            long id,
            long providerId,
            String model,
            Set<String> capabilities,
            Parameters parameters,
            boolean enabled) {}

    record Parameters(
            Double temperature, Integer maxTokens, Long timeoutMillis, Integer maxAttempts) {}

    record Default(SystemModelResolvedRoute route, @JsonIgnore String ciphertext) {
        @Override
        public String toString() {
            return "StoredDefault[redacted]";
        }
    }

    @Override
    public String toString() {
        return "StoredConfig[redacted]";
    }
}
