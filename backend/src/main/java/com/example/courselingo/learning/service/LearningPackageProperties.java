package com.example.courselingo.learning.service;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "courselingo.learning-package")
public class LearningPackageProperties {

    public static final Duration DEFAULT_LLM_TIMEOUT = Duration.ofSeconds(180);

    private Duration llmTimeout = DEFAULT_LLM_TIMEOUT;

    public LearningPackageProperties() {
    }

    public LearningPackageProperties(Duration llmTimeout) {
        setLlmTimeout(llmTimeout);
    }

    public Duration llmTimeout() {
        return llmTimeout;
    }

    public void setLlmTimeout(Duration llmTimeout) {
        Duration normalized = llmTimeout == null ? DEFAULT_LLM_TIMEOUT : llmTimeout;
        if (normalized.isZero() || normalized.isNegative()) {
            throw new IllegalArgumentException("llmTimeout must be positive");
        }
        this.llmTimeout = normalized;
    }
}
