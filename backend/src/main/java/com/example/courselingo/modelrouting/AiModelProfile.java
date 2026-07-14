package com.example.courselingo.modelrouting;

import java.time.Duration;
import java.util.LinkedHashSet;
import java.util.Set;

public class AiModelProfile {

    private String displayName;
    private String providerType;
    private String baseUrl;
    private String modelName;
    private String apiKeyEnvName;
    private Set<ModelCapability> capabilities = new LinkedHashSet<>();
    private Double temperature;
    private Integer maxTokens;
    private Duration timeout;
    private Integer maxAttempts;
    private boolean enabled = true;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getProviderType() {
        return providerType;
    }

    public void setProviderType(String providerType) {
        this.providerType = providerType;
    }

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public String getModelName() {
        return modelName;
    }

    public void setModelName(String modelName) {
        this.modelName = modelName;
    }

    public String getApiKeyEnvName() {
        return apiKeyEnvName;
    }

    public void setApiKeyEnvName(String apiKeyEnvName) {
        this.apiKeyEnvName = apiKeyEnvName;
    }

    public Set<ModelCapability> getCapabilities() {
        return capabilities;
    }

    public void setCapabilities(Set<ModelCapability> capabilities) {
        this.capabilities = capabilities == null ? new LinkedHashSet<>() : new LinkedHashSet<>(capabilities);
    }

    public Double getTemperature() {
        return temperature;
    }

    public void setTemperature(Double temperature) {
        this.temperature = temperature;
    }

    public Integer getMaxTokens() {
        return maxTokens;
    }

    public void setMaxTokens(Integer maxTokens) {
        this.maxTokens = maxTokens;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public Integer getMaxAttempts() {
        return maxAttempts;
    }

    public void setMaxAttempts(Integer maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
