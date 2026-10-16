package com.example.courselingo.subtitle.pipeline;

import org.springframework.boot.context.properties.ConfigurationProperties;
import java.time.Duration;

@ConfigurationProperties(prefix = "courselingo.pipeline.translation-v2")
public class PipelineTranslationProperties {
    private boolean enabled;
    private int outputMin = 512, outputMax = 8192, maxDepth = 6, maxAttempts = 3, maxCalls = 256;
    private int contextLimit = 32768;
    private long tokenBudget = 200000;
    private double outputRatio = 2.0;

    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean value) { enabled = value; }
    public int getOutputMin() { return outputMin; }
    public void setOutputMin(int value) { outputMin = value; }
    public int getOutputMax() { return outputMax; }
    public void setOutputMax(int value) { outputMax = value; }
    public int getMaxDepth() { return maxDepth; }
    public void setMaxDepth(int value) { maxDepth = value; }
    public int getMaxAttempts() { return maxAttempts; }
    public void setMaxAttempts(int value) { maxAttempts = value; }
    public int getMaxCalls() { return maxCalls; }
    public void setMaxCalls(int value) { maxCalls = value; }
    public int getContextLimit() { return contextLimit; }
    public void setContextLimit(int value) { contextLimit = value; }
    public long getTokenBudget() { return tokenBudget; }
    public void setTokenBudget(long value) { tokenBudget = value; }
    public double getOutputRatio() { return outputRatio; }
    public void setOutputRatio(double value) { outputRatio = value; }

    public TranslationPolicy freeze(Duration requestTimeout, Duration totalTimeout, int segments, int chars) {
        return new TranslationPolicy("translation-v2.1", "UTF8_CONSERVATIVE_V1",
            Math.min(120000, requestTimeout.toMillis()), Math.min(900000, totalTimeout.toMillis()),
            outputMin, outputMax, outputRatio, 128, 1.10, 512, contextLimit,
            maxDepth, maxAttempts, maxCalls, tokenBudget, segments, chars);
    }
}
