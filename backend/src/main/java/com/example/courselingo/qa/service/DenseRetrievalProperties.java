package com.example.courselingo.qa.service;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "courselingo.retrieval")
public class DenseRetrievalProperties {
    private boolean enabled;
    private String baseUrl = "http://127.0.0.1:8090";
    private String serviceSecret = "";
    private Duration timeout = Duration.ofSeconds(120);

    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean enabled) { this.enabled = enabled; }
    public String getBaseUrl() { return baseUrl; }
    public void setBaseUrl(String baseUrl) { this.baseUrl = baseUrl; }
    public String getServiceSecret() { return serviceSecret; }
    public void setServiceSecret(String serviceSecret) { this.serviceSecret = serviceSecret; }
    public Duration getTimeout() { return timeout; }
    public void setTimeout(Duration timeout) {
        if (timeout == null || timeout.isNegative() || timeout.isZero() || timeout.compareTo(Duration.ofMinutes(5)) > 0) {
            throw new IllegalArgumentException("Retrieval timeout must be in (0, 5 minutes]");
        }
        this.timeout = timeout;
    }
}
