package com.example.courselingo.systemmodel;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.UnaryOperator;

public class SystemModelRegistry {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate transactions;
    private final SystemModelSecretCipher cipher;
    private final SystemModelUrlPolicy addresses;
    private final SystemModelEnvironment.Captured environment;
    private final SystemModelConfigCodec codec = new SystemModelConfigCodec();
    private final Map<Long, SystemModelStoredConfig> cache = new ConcurrentHashMap<>();
    private java.util.function.LongConsumer notifier = ignored -> {};

    SystemModelRegistry(
            JdbcTemplate jdbc,
            PlatformTransactionManager manager,
            SystemModelSecretCipher cipher,
            SystemModelUrlPolicy addresses,
            SystemModelEnvironment.Captured environment) {
        this.jdbc = jdbc;
        this.transactions = new TransactionTemplate(manager);
        this.cipher = cipher;
        this.addresses = addresses;
        this.environment = environment;
        if (!cipher.configured())
            throw new BusinessException(ErrorCode.SYSTEM_MODEL_MASTER_KEY_MISSING);
    }

    void initialize() {
        transactions.executeWithoutResult(
                status -> {
                    long version = lockVersion();
                    var current = load(version);
                    if (!environment.fingerprint().equals(current.environmentFingerprint())) {
                        var next =
                                new SystemModelStoredConfig(
                                        current.providers(),
                                        current.models(),
                                        current.bindings(),
                                        environment.defaults(),
                                        environment.fingerprint(),
                                        environment.fullText());
                        commit(
                                version,
                                next,
                                null,
                                "ENVIRONMENT_CAPTURED",
                                "CONFIG",
                                "environment");
                    }
                });
    }

    public long currentVersion() {
        try {
            return jdbc.queryForObject(
                    "SELECT current_version FROM system_model_config_state WHERE id=1", Long.class);
        } catch (RuntimeException ignored) {
            throw SystemModelConfigCodec.unavailable();
        }
    }

    long lockVersion() {
        return jdbc.queryForObject(
                "SELECT current_version FROM system_model_config_state WHERE id=1 FOR UPDATE",
                Long.class);
    }

    SystemModelStoredConfig load(long version) {
        try {
            if (cache.size() > 32) cache.clear();
            return cache.computeIfAbsent(
                    version,
                    number ->
                            jdbc.queryForObject(
                                    "SELECT config_json, config_sha256 FROM"
                                            + " system_model_config_version WHERE version=?",
                                    (row, index) ->
                                            codec.decode(row.getString(1), row.getString(2)),
                                    number));
        } catch (RuntimeException ignored) {
            throw SystemModelConfigCodec.unavailable();
        }
    }

    public void invalidate(long ignoredVersion) {
        cache.clear();
    }

    void notifier(java.util.function.LongConsumer notifier) {
        this.notifier = notifier;
    }

    public SystemModelViews.Catalog catalog() {
        long version = currentVersion();
        return project(version, load(version));
    }

    public SystemModelViews.Version version(long version) {
        var safe = project(version, load(version));
        return jdbc.queryForObject(
                "SELECT parent_version, actor_user_id, reason, created_at FROM"
                        + " system_model_config_version WHERE version=?",
                (row, index) ->
                        new SystemModelViews.Version(
                                version,
                                row.getObject(1, Long.class),
                                row.getObject(2, Long.class),
                                row.getString(3),
                                row.getString(4),
                                safe),
                version);
    }

    public List<SystemModelViews.VersionSummary> versions(long before) {
        return jdbc.query(
                "SELECT version,parent_version,actor_user_id,reason,created_at FROM"
                    + " system_model_config_version WHERE version < ? ORDER BY version DESC LIMIT"
                    + " 50",
                (r, i) ->
                        new SystemModelViews.VersionSummary(
                                r.getLong(1),
                                r.getObject(2, Long.class),
                                r.getObject(3, Long.class),
                                r.getString(4),
                                r.getString(5)),
                before);
    }

    public List<SystemModelViews.Audit> audit(long before) {
        // safe_changes is intentionally not returned: queries never pass through arbitrary stored
        // JSON.
        return jdbc.query(
                "SELECT"
                    + " id,config_version,actor_type,actor_user_id,action,object_type,object_id,created_at"
                    + " FROM system_model_audit WHERE id < ? ORDER BY id DESC LIMIT 50",
                (r, i) ->
                        new SystemModelViews.Audit(
                                r.getLong(1),
                                r.getObject(2, Long.class),
                                r.getString(3),
                                r.getObject(4, Long.class),
                                r.getString(5),
                                r.getString(6),
                                r.getString(7),
                                r.getString(8)),
                before);
    }

    public SystemModelViews.Catalog saveProvider(
            Long id, SystemModelCommands.Provider command, long actor) {
        String name = text(command.name(), 128), base = addresses.normalize(command.baseUrl());
        addresses.checkDestination(java.net.URI.create(base));
        return mutate(
                command.expectedVersion(),
                actor,
                "PROVIDER_SAVED",
                "PROVIDER",
                id == null ? "new" : id.toString(),
                current -> {
                    if (current.providers().size() >= 100 && id == null) throw invalid();
                    var previous = id == null ? null : provider(current, id);
                    if (command.protocol() == null) throw invalid();
                    if (previous != null
                            && (!previous.baseUrl().equals(base)
                                    || previous.protocol() != command.protocol())
                            && command.apiKey() == null
                            && !command.clearKey()) throw invalid();
                    if (command.apiKey() != null && command.clearKey()) throw invalid();
                    long providerId =
                            id == null
                                    ? insertId(
                                            "INSERT INTO system_model_provider"
                                                    + " (name,protocol,base_url) VALUES (?,?,?)",
                                            name,
                                            command.protocol().name(),
                                            base)
                                    : id;
                    String ciphertext = previous == null ? null : previous.ciphertext(),
                            last4 = previous == null ? null : previous.keyLast4();
                    if (command.clearKey()) {
                        ciphertext = null;
                        last4 = null;
                    }
                    if (command.apiKey() != null) {
                        var encrypted = cipher.encrypt(Long.toString(providerId), command.apiKey());
                        ciphertext = encrypted.ciphertext();
                        last4 = encrypted.keyLast4();
                    }
                    var updated =
                            new SystemModelStoredConfig.Provider(
                                    providerId,
                                    name,
                                    command.protocol(),
                                    base,
                                    command.enabled(),
                                    ciphertext,
                                    last4);
                    var providers = new ArrayList<>(current.providers());
                    providers.removeIf(p -> p.id() == providerId);
                    providers.add(updated);
                    var next = copy(current, providers, current.models(), current.bindings());
                    validateBindings(next);
                    jdbc.update(
                            "UPDATE system_model_provider SET"
                                + " name=?,protocol=?,base_url=?,enabled=?,api_key_ciphertext=?,key_last4=?,row_version=row_version+1"
                                + " WHERE id=?",
                            name,
                            command.protocol().name(),
                            base,
                            command.enabled(),
                            ciphertext,
                            last4,
                            providerId);
                    return next;
                });
    }

    public SystemModelViews.Catalog saveModel(
            Long id, long providerId, SystemModelCommands.Model command, long actor) {
        return mutate(
                command.expectedVersion(),
                actor,
                "MODEL_SAVED",
                "MODEL",
                id == null ? "new" : id.toString(),
                current -> {
                    provider(current, providerId);
                    if (current.models().size() >= 500 && id == null) throw invalid();
                    if (id != null && model(current, id).providerId() != providerId)
                        throw invalid();
                    String name = text(command.model(), 128);
                    Set<String> capabilities =
                            command.capabilities() == null
                                    ? Set.of()
                                    : Set.copyOf(command.capabilities());
                    if (!Set.of("TEXT_CHAT", "JSON_OUTPUT", "VISION", "ASR")
                            .containsAll(capabilities)) throw invalid();
                    var params =
                            command.parameters() == null
                                    ? new SystemModelViews.Parameters(null, null, null, null)
                                    : command.parameters();
                    validateParameters(params);
                    long modelId =
                            id == null
                                    ? insertId(
                                            "INSERT INTO system_model"
                                                + " (provider_id,model_id,capabilities,parameters)"
                                                + " VALUES (?,?,?,?)",
                                            providerId,
                                            name,
                                            json(capabilities),
                                            json(params))
                                    : id;
                    var updated =
                            new SystemModelStoredConfig.Model(
                                    modelId,
                                    providerId,
                                    name,
                                    capabilities,
                                    new SystemModelStoredConfig.Parameters(
                                            params.temperature(),
                                            params.maxTokens(),
                                            params.timeoutMillis(),
                                            params.maxAttempts()),
                                    command.enabled());
                    var models = new ArrayList<>(current.models());
                    models.removeIf(m -> m.id() == modelId);
                    models.add(updated);
                    var next = copy(current, current.providers(), models, current.bindings());
                    validateBindings(next);
                    jdbc.update(
                            "UPDATE system_model SET"
                                + " model_id=?,capabilities=?,parameters=?,enabled=?,row_version=row_version+1"
                                + " WHERE id=?",
                            name,
                            json(capabilities),
                            json(params),
                            command.enabled(),
                            modelId);
                    return next;
                });
    }

    public SystemModelViews.Catalog bindings(SystemModelCommands.Bindings command, long actor) {
        return saveBindings(command, actor, "BINDINGS_SAVED", "features");
    }

    private SystemModelViews.Catalog saveBindings(
            SystemModelCommands.Bindings command, long actor, String action, String objectId) {
        if (command.bindings() == null
                || command.bindings().isEmpty()
                || command.bindings().size() > 7) throw invalid();
        return mutate(
                command.expectedVersion(),
                actor,
                action,
                "BINDING",
                objectId,
                current -> {
                    var bindings = new LinkedHashMap<>(current.bindings());
                    command.bindings()
                            .forEach(
                                    (key, value) -> {
                                        bindable(key);
                                        if (value == null) bindings.remove(key);
                                        else bindings.put(key, value);
                                    });
                    var next = copy(current, current.providers(), current.models(), bindings);
                    validateBindings(next);
                    jdbc.update("DELETE FROM system_model_binding");
                    bindings.forEach(
                            (key, id) ->
                                    jdbc.update(
                                            "INSERT INTO system_model_binding"
                                                    + " (feature_key,model_id) VALUES (?,?)",
                                            key,
                                            id));
                    return next;
                });
    }

    public SystemModelViews.Catalog rollback(SystemModelCommands.Rollback command, long actor) {
        bindable(command.feature());
        var historical = load(command.targetVersion());
        var bindings = new LinkedHashMap<String, Long>();
        bindings.put(command.feature(), historical.bindings().get(command.feature()));
        return saveBindings(
                new SystemModelCommands.Bindings(command.expectedVersion(), bindings),
                actor,
                "BINDING_ROLLED_BACK",
                command.feature() + ":" + command.targetVersion());
    }

    public SystemModelViews.Catalog delete(String type, long id, long expected, long actor) {
        return mutate(
                expected,
                actor,
                type.equals("PROVIDER") ? "PROVIDER_DELETED" : "MODEL_DELETED",
                type,
                Long.toString(id),
                current -> {
                    if (type.equals("PROVIDER")) {
                        provider(current, id);
                        if (current.models().stream().anyMatch(m -> m.providerId() == id))
                            throw conflict();
                        var providers = new ArrayList<>(current.providers());
                        providers.removeIf(p -> p.id() == id);
                        jdbc.update("DELETE FROM system_model_provider WHERE id=?", id);
                        return copy(current, providers, current.models(), current.bindings());
                    }
                    model(current, id);
                    if (current.bindings().containsValue(id)) throw conflict();
                    var models = new ArrayList<>(current.models());
                    models.removeIf(m -> m.id() == id);
                    jdbc.update("DELETE FROM system_model WHERE id=?", id);
                    return copy(current, current.providers(), models, current.bindings());
                });
    }

    SystemModelResolvedRoute resolve(SystemModelStoredConfig config, String feature) {
        Long id = config.bindings().get(feature);
        if (id == null) {
            var fallback = config.defaults().get(feature);
            if (fallback == null) throw SystemModelConfigCodec.unavailable();
            return fallback.route();
        }
        var model = model(config, id);
        var provider = provider(config, model.providerId());
        requireUsable(feature, model, provider);
        var p = model.parameters();
        return new SystemModelResolvedRoute(
                feature,
                "DATABASE",
                provider.protocol(),
                Long.toString(provider.id()),
                provider.id(),
                model.id(),
                provider.baseUrl(),
                model.model(),
                model.capabilities(),
                p.temperature(),
                p.maxTokens(),
                p.timeoutMillis(),
                p.maxAttempts(),
                provider.ciphertext() != null,
                provider.keyLast4());
    }

    String credential(long version, SystemModelResolvedRoute route) {
        var config = load(version);
        String encrypted;
        if ("DATABASE".equals(route.source())) {
            var provider = provider(config, route.providerId());
            encrypted = provider.ciphertext();
        } else {
            var fallback = config.defaults().get(route.feature());
            if (fallback == null) throw SystemModelConfigCodec.unavailable();
            encrypted = fallback.ciphertext();
        }
        if (encrypted == null) throw SystemModelConfigCodec.unavailable();
        return cipher.decrypt(route.credentialId(), encrypted);
    }

    boolean fullText(SystemModelStoredConfig config) {
        return config.fullTextTranslation();
    }

    private SystemModelViews.Catalog project(long version, SystemModelStoredConfig config) {
        var providers =
                config.providers().stream()
                        .map(
                                p ->
                                        new SystemModelViews.Provider(
                                                p.id(),
                                                p.name(),
                                                p.protocol(),
                                                p.baseUrl(),
                                                p.enabled(),
                                                p.ciphertext() != null,
                                                p.keyLast4()))
                        .toList();
        var models =
                config.models().stream()
                        .map(
                                m ->
                                        new SystemModelViews.Model(
                                                m.id(),
                                                m.providerId(),
                                                m.model(),
                                                m.capabilities(),
                                                new SystemModelViews.Parameters(
                                                        m.parameters().temperature(),
                                                        m.parameters().maxTokens(),
                                                        m.parameters().timeoutMillis(),
                                                        m.parameters().maxAttempts()),
                                                m.enabled()))
                        .toList();
        var effective = new LinkedHashMap<String, SystemModelResolvedRoute>();
        config.defaults().keySet().stream()
                .filter(k -> !k.startsWith("TRANSLATION_MODE_"))
                .sorted()
                .forEach(k -> effective.put(k, resolve(config, k)));
        return new SystemModelViews.Catalog(
                version,
                providers,
                models,
                Map.copyOf(config.bindings()),
                Map.copyOf(effective),
                fullText(config));
    }

    private SystemModelViews.Catalog mutate(
            long expected,
            long actor,
            String action,
            String type,
            String id,
            UnaryOperator<SystemModelStoredConfig> change) {
        try {
            return transactions.execute(
                    status -> {
                        long current = lockVersion();
                        if (current != expected) throw conflict();
                        var next = change.apply(load(current));
                        String objectId = id;
                        if ("new".equals(id))
                            objectId =
                                    Long.toString(
                                            "PROVIDER".equals(type)
                                                    ? next.providers().getLast().id()
                                                    : next.models().getLast().id());
                        long version = commit(current, next, actor, action, type, objectId);
                        return project(version, next);
                    });
        } catch (BusinessException safe) {
            throw safe;
        } catch (RuntimeException ignored) {
            throw SystemModelConfigCodec.unavailable();
        }
    }

    private long commit(
            long previous,
            SystemModelStoredConfig config,
            Long actor,
            String action,
            String type,
            String id) {
        long next = Math.addExact(previous, 1);
        String json = codec.encode(config);
        jdbc.update(
                "INSERT INTO system_model_config_version"
                        + " (version,parent_version,config_json,config_sha256,actor_user_id,reason)"
                        + " VALUES (?,?,?,?,?,?)",
                next,
                previous,
                json,
                SystemModelConfigCodec.sha256(json),
                actor,
                action);
        jdbc.update("UPDATE system_model_config_state SET current_version=? WHERE id=1", next);
        jdbc.update(
                "INSERT INTO system_model_audit"
                    + " (config_version,actor_type,actor_user_id,action,object_type,object_id,safe_changes)"
                    + " VALUES (?,?,?,?,?,?,?)",
                next,
                actor == null ? "SYSTEM" : "ADMIN",
                actor,
                action,
                type,
                id,
                "{\"previousVersion\":" + previous + ",\"newVersion\":" + next + "}");
        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        cache.clear();
                        try {
                            notifier.accept(next);
                        } catch (RuntimeException ignored) {
                            /* DB version check remains authoritative. */
                        }
                    }
                });
        return next;
    }

    private void validateBindings(SystemModelStoredConfig config) {
        config.bindings()
                .forEach(
                        (feature, id) -> {
                            bindable(feature);
                            var model = model(config, id);
                            requireUsable(feature, model, provider(config, model.providerId()));
                        });
    }

    private void requireUsable(
            String feature,
            SystemModelStoredConfig.Model model,
            SystemModelStoredConfig.Provider provider) {
        if (!model.enabled()
                || !provider.enabled()
                || provider.ciphertext() == null
                || provider.protocol() != SystemModelProtocol.OPENAI_CHAT) throw conflict();
        Set<String> required =
                feature.equals("VISION_FRAME_ANALYSIS")
                        ? Set.of("VISION", "JSON_OUTPUT")
                        : Set.of("TEXT_CHAT", "JSON_OUTPUT");
        if (!model.capabilities().containsAll(required)) throw invalid();
    }

    private static void bindable(String key) {
        try {
            var feature = SystemModelFeature.valueOf(key);
            if (!feature.connected() || feature == SystemModelFeature.ASR_TRANSCRIPTION)
                throw invalid();
        } catch (RuntimeException ignored) {
            throw invalid();
        }
    }

    private static SystemModelStoredConfig.Provider provider(SystemModelStoredConfig c, long id) {
        return c.providers().stream()
                .filter(p -> p.id() == id)
                .findFirst()
                .orElseThrow(SystemModelRegistry::conflict);
    }

    private static SystemModelStoredConfig.Model model(SystemModelStoredConfig c, long id) {
        return c.models().stream()
                .filter(m -> m.id() == id)
                .findFirst()
                .orElseThrow(SystemModelRegistry::conflict);
    }

    private static SystemModelStoredConfig copy(
            SystemModelStoredConfig c,
            List<SystemModelStoredConfig.Provider> p,
            List<SystemModelStoredConfig.Model> m,
            Map<String, Long> b) {
        return new SystemModelStoredConfig(
                List.copyOf(p),
                List.copyOf(m),
                Map.copyOf(b),
                c.defaults(),
                c.environmentFingerprint(),
                c.fullTextTranslation());
    }

    private static void validateParameters(SystemModelViews.Parameters p) {
        if (p.temperature() != null
                        && (!Double.isFinite(p.temperature())
                                || p.temperature() < 0
                                || p.temperature() > 2)
                || p.maxTokens() != null && (p.maxTokens() < 1 || p.maxTokens() > 32768)
                || p.timeoutMillis() != null
                        && (p.timeoutMillis() < 100 || p.timeoutMillis() > 180000)
                || p.maxAttempts() != null && (p.maxAttempts() < 1 || p.maxAttempts() > 3))
            throw invalid();
    }

    private long insertId(String sql, Object... values) {
        var holder = new GeneratedKeyHolder();
        jdbc.update(
                connection -> {
                    var statement =
                            connection.prepareStatement(
                                    sql, java.sql.Statement.RETURN_GENERATED_KEYS);
                    for (int i = 0; i < values.length; i++) statement.setObject(i + 1, values[i]);
                    return statement;
                },
                holder);
        return holder.getKey().longValue();
    }

    private static String json(Object value) {
        try {
            return new ObjectMapper().writeValueAsString(value);
        } catch (Exception ignored) {
            throw invalid();
        }
    }

    private static String text(String value, int max) {
        if (value == null
                || value.isBlank()
                || value.length() > max
                || value.chars().anyMatch(Character::isISOControl)) throw invalid();
        return value.strip();
    }

    private static BusinessException invalid() {
        return new BusinessException(ErrorCode.SYSTEM_MODEL_CONFIG_INVALID);
    }

    private static BusinessException conflict() {
        return new BusinessException(ErrorCode.SYSTEM_MODEL_CONFIG_CONFLICT);
    }
}
