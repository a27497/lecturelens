package com.example.courselingo.ai.asr;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "courselingo.ai.asr.silicon-flow")
public class SiliconFlowAsrProperties {

    public static final String DEFAULT_BASE_URL = "https://api.siliconflow.cn";
    public static final String DEFAULT_MODEL = "FunAudioLLM/SenseVoiceSmall";

    private boolean enabled;
    private String baseUrl = DEFAULT_BASE_URL;
    private String apiKey = "";
    private String model = DEFAULT_MODEL;
    private Duration connectTimeout = Duration.ofSeconds(5);
    private Duration requestTimeout = Duration.ofSeconds(180);
    private DataSize maxAudioFileSize = DataSize.ofMegabytes(5);

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

    public DataSize getMaxAudioFileSize() {
        return maxAudioFileSize;
    }

    public void setMaxAudioFileSize(DataSize maxAudioFileSize) {
        this.maxAudioFileSize = maxAudioFileSize;
    }
}
