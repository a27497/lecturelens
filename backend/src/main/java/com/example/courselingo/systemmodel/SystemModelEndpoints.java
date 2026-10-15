package com.example.courselingo.systemmodel;

import java.net.URI;

/** Mirrors the existing protocol adapters without resolving DNS or making a request. */
final class SystemModelEndpoints {
    private SystemModelEndpoints() {}

    static URI finalUri(SystemModelResolvedRoute route) {
        if (route.protocol() == null || route.baseUrl() == null) return null;
        URI base = URI.create(route.baseUrl().strip());
        if (base.getHost() == null
                || base.getRawUserInfo() != null
                || !("http".equalsIgnoreCase(base.getScheme())
                        || "https".equalsIgnoreCase(base.getScheme())))
            throw new IllegalArgumentException("Invalid endpoint");
        String path = base.getRawPath();
        if (route.protocol() == SystemModelProtocol.OPENAI_CHAT) {
            if (path == null || path.isBlank() || path.equals("/"))
                path = "DATABASE".equals(route.source()) ? "" : "/v1";
            path = path.replaceAll("/+$", "") + "/chat/completions";
        } else if (route.protocol() == SystemModelProtocol.SILICONFLOW_ASR) {
            path = "/v1/audio/transcriptions";
        }
        // Do not propagate legacy URL queries/fragments into status responses.
        return URI.create(
                base.getScheme().toLowerCase(java.util.Locale.ROOT)
                        + "://"
                        + base.getRawAuthority()
                        + path);
    }
}
