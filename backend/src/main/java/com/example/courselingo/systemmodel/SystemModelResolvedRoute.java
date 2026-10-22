package com.example.courselingo.systemmodel;

import java.util.Set;

/**
 * Persistable execution data. Credentials (including ciphertext) belong exclusively to the
 * referenced version.
 */
public record SystemModelResolvedRoute(
        String feature,
        String source,
        SystemModelProtocol protocol,
        @com.fasterxml.jackson.annotation.JsonIgnore String credentialId,
        Long providerId,
        Long modelId,
        String baseUrl,
        String model,
        Set<String> capabilities,
        Double temperature,
        Integer maxTokens,
        Long timeoutMillis,
        Integer maxAttempts,
        boolean hasKey,
        String keyLast4,
        com.example.courselingo.ai.asr.AsrConfigurationSnapshot asr) {
    public SystemModelResolvedRoute(
            String feature,
            String source,
            SystemModelProtocol protocol,
            String credentialId,
            Long providerId,
            Long modelId,
            String baseUrl,
            String model,
            Set<String> capabilities,
            Double temperature,
            Integer maxTokens,
            Long timeoutMillis,
            Integer maxAttempts,
            boolean hasKey,
            String keyLast4) {
        this(
                feature,
                source,
                protocol,
                credentialId,
                providerId,
                modelId,
                baseUrl,
                model,
                capabilities,
                temperature,
                maxTokens,
                timeoutMillis,
                maxAttempts,
                hasKey,
                keyLast4,
                null);
    }

    public SystemModelResolvedRoute {
        capabilities = java.util.Collections.unmodifiableSet(new java.util.TreeSet<>(capabilities));
    }
}
