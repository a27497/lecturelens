package com.example.courselingo.systemmodel;

import java.util.List;
import java.util.Map;
import java.util.Set;

/** HTTP projections deliberately have no payload, ciphertext, or environment fingerprint fields. */
public final class SystemModelViews {
    private SystemModelViews() {}

    public record Provider(
            long id,
            String name,
            SystemModelProtocol protocol,
            String baseUrl,
            boolean enabled,
            boolean hasKey,
            String keyLast4) {}

    public record Model(
            long id,
            long providerId,
            String model,
            Set<String> capabilities,
            Parameters parameters,
            boolean enabled) {}

    public record Parameters(
            Double temperature, Integer maxTokens, Long timeoutMillis, Integer maxAttempts) {}

    public record Catalog(
            long version,
            List<Provider> providers,
            List<Model> models,
            Map<String, Long> bindings,
            Map<String, SystemModelResolvedRoute> effective,
            boolean fullTextTranslation) {}

    public record Version(
            long version,
            Long parentVersion,
            Long actorUserId,
            String reason,
            String createdAt,
            Catalog config) {}

    public record VersionSummary(
            long version, Long parentVersion, Long actorUserId, String reason, String createdAt) {}

    public record Audit(
            long id,
            Long version,
            String actorType,
            Long actorUserId,
            String action,
            String objectType,
            String objectId,
            String createdAt) {}

    public record Execution(
            String id,
            String taskId,
            long userId,
            String operationType,
            String operationId,
            long configVersion,
            Map<String, SystemModelResolvedRoute> routes,
            boolean fullTextTranslation,
            String origin,
            String createdAt) {}
}
