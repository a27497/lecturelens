package com.example.courselingo.ai.asr;

import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "courselingo.ai.asr.bailian")
public class BailianAsrProperties {
    private String endpoint = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation";
    private String apiKey = "";
    private String model = "qwen-audio-3.1-asr-flash";
    private Duration connectTimeout = Duration.ofSeconds(5);
    private Duration requestTimeout = Duration.ofSeconds(180);
    private DataSize maxAudioFileSize = DataSize.ofMegabytes(7);
    private boolean languageHintEnabled = false;
    private String context = "";
    private Map<String, Integer> vocabulary = new LinkedHashMap<>();

    public String getEndpoint() { return endpoint; }
    public void setEndpoint(String endpoint) { this.endpoint = endpoint; }

    public String getApiKey() { return apiKey; }
    public void setApiKey(String apiKey) { this.apiKey = apiKey; }

    public String getModel() { return model; }
    public void setModel(String model) { this.model = model; }

    public Duration getConnectTimeout() { return connectTimeout; }
    public void setConnectTimeout(Duration connectTimeout) { this.connectTimeout = connectTimeout; }

    public Duration getRequestTimeout() { return requestTimeout; }
    public void setRequestTimeout(Duration requestTimeout) { this.requestTimeout = requestTimeout; }

    public DataSize getMaxAudioFileSize() { return maxAudioFileSize; }
    public void setMaxAudioFileSize(DataSize maxAudioFileSize) { this.maxAudioFileSize = maxAudioFileSize; }

    public boolean isLanguageHintEnabled() { return languageHintEnabled; }
    public void setLanguageHintEnabled(boolean languageHintEnabled) { this.languageHintEnabled = languageHintEnabled; }

    public String getContext() { return context; }
    public void setContext(String context) { this.context = context; }

    public Map<String, Integer> getVocabulary() { return vocabulary; }
    public void setVocabulary(Map<String, Integer> vocabulary) { this.vocabulary = vocabulary; }
}
