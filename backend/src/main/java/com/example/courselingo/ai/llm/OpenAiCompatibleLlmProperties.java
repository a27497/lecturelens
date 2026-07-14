package com.example.courselingo.ai.llm;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "courselingo.ai.llm.openai-compatible")
public class OpenAiCompatibleLlmProperties {

    public static final String DEFAULT_BASE_URL = "https://api.siliconflow.cn/v1";
    public static final String DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct";

    private boolean enabled;
    private String baseUrl = DEFAULT_BASE_URL;
    private String apiKey = "";
    private String model = DEFAULT_MODEL;
    private Duration connectTimeout = Duration.ofSeconds(5);
    private Duration requestTimeout = Duration.ofSeconds(60);
    private Double temperature = 0.0;
    private Integer maxTokens = 4096;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public String getApiKey() {
        return apiKey;
    }

    public void setApiKey(String apiKey) {
        this.apiKey = apiKey;
    }

    public String getModel() {
        return model;
    }

    public void setModel(String model) {
        this.model = model;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public Duration getRequestTimeout() {
        return requestTimeout;
    }

    public void setRequestTimeout(Duration requestTimeout) {
        this.requestTimeout = requestTimeout;
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
}
