package com.example.courselingo.modelrouting;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "courselingo.ai.model-routing")
public class AiModelRoutingProperties {

    private boolean enabled = true;
    private Map<AiModelStage, String> routes = new LinkedHashMap<>();
    private Map<String, AiModelProfile> profiles = new LinkedHashMap<>();

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public Map<AiModelStage, String> getRoutes() {
        return routes;
    }

    public void setRoutes(Map<AiModelStage, String> routes) {
        this.routes = routes == null ? new LinkedHashMap<>() : new LinkedHashMap<>(routes);
    }

    public Map<String, AiModelProfile> getProfiles() {
        return profiles;
    }

    public void setProfiles(Map<String, AiModelProfile> profiles) {
        this.profiles = profiles == null ? new LinkedHashMap<>() : new LinkedHashMap<>(profiles);
    }
}
