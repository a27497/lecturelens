package com.example.courselingo.systemmodel;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.fasterxml.jackson.databind.MapperFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Map;

final class SystemModelConfigCodec {
    // Only this private persistence mapper bypasses secret annotations. HTTP uses explicit
    // projection records.
    private final JsonMapper storage =
            JsonMapper.builder().disable(MapperFeature.USE_ANNOTATIONS).build();

    String encode(SystemModelStoredConfig config) {
        try {
            return storage.writeValueAsString(config);
        } catch (Exception ignored) {
            throw unavailable();
        }
    }

    SystemModelStoredConfig decode(String json, String checksum) {
        if (!sha256(json).equals(checksum)) throw unavailable();
        try {
            var config = storage.readValue(json, SystemModelStoredConfig.class);
            return new SystemModelStoredConfig(
                    config.providers(),
                    config.models(),
                    config.bindings(),
                    config.defaults() == null ? Map.of() : config.defaults(),
                    config.environmentFingerprint(),
                    config.fullTextTranslation());
        } catch (Exception ignored) {
            throw unavailable();
        }
    }

    static String sha256(String value) {
        try {
            return HexFormat.of()
                    .formatHex(
                            MessageDigest.getInstance("SHA-256")
                                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException ignored) {
            throw unavailable();
        }
    }

    static BusinessException unavailable() {
        return new BusinessException(ErrorCode.SYSTEM_MODEL_CONFIG_UNAVAILABLE);
    }
}
