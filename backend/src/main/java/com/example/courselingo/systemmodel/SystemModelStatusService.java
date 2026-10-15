package com.example.courselingo.systemmodel;

import org.springframework.core.env.Environment;

import java.util.*;

/** Local checks only; opening the administrator page never contacts a model provider. */
public final class SystemModelStatusService {
    private final SystemModelRegistry registry;
    private final Environment environment;

    public SystemModelStatusService(SystemModelRegistry registry, Environment environment) {
        this.registry = registry;
        this.environment = environment;
    }

    public record Feature(
            String key,
            boolean connected,
            boolean active,
            String source,
            long version,
            String finalUrl,
            String configurationStatus) {}

    public record Status(long version, List<Feature> features) {}

    public Status inspect(long version) {
        var config = registry.load(version);
        var features = new ArrayList<Feature>();
        for (var feature : SystemModelFeature.values()) {
            if (!feature.connected()) {
                features.add(
                        new Feature(
                                feature.name(),
                                false,
                                false,
                                "UNCONNECTED",
                                version,
                                null,
                                "UNCONNECTED"));
                continue;
            }
            boolean active =
                    switch (feature) {
                        case TRANSLATION_FULL_TEXT -> config.fullTextTranslation();
                        case SUBTITLE_TRANSLATION -> !config.fullTextTranslation();
                        case VISION_FRAME_ANALYSIS ->
                                environment.getProperty(
                                        "courselingo.vision.analysis.enabled",
                                        Boolean.class,
                                        false);
                        case COURSE_CHAPTER ->
                                environment.getProperty(
                                        "courselingo.chapter.enabled", Boolean.class, true);
                        default -> true;
                    };
            String source = "UNCONFIGURED", state = "UNCONFIGURED", endpoint = null;
            try {
                var route = registry.resolve(config, feature.name());
                source = route.source();
                if (source.equals("MOCK")) state = "MOCK";
                else if (source.equals("ENV") || source.equals("DATABASE")) {
                    endpoint = SystemModelEndpoints.finalUri(route).toString();
                    if (!route.hasKey()) state = "MISSING_KEY";
                    else {
                        try {
                            registry.credential(version, route);
                            state = "READY";
                        } catch (RuntimeException ignored) {
                            state = "KEY_UNAVAILABLE";
                        }
                    }
                }
            } catch (RuntimeException ignored) {
                state = "INVALID";
            }
            features.add(
                    new Feature(feature.name(), true, active, source, version, endpoint, state));
        }
        return new Status(version, List.copyOf(features));
    }
}
