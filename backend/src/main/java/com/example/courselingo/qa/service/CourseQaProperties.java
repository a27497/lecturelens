package com.example.courselingo.qa.service;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "courselingo.qa")
public class CourseQaProperties {

    private int rateLimitPerMinute = 10;
    private int questionMaxLength = 500;
    private int maxEvidenceItems = 8;
    private int maxSnippetChars = 360;
    private int maxPromptChars = 8000;
    private int maxTokens = 768;
    private int maxAttempts = 1;
    private Duration llmTimeout = Duration.ofSeconds(45);

    public int getRateLimitPerMinute() {
        return rateLimitPerMinute;
    }

    public void setRateLimitPerMinute(int rateLimitPerMinute) {
        if (rateLimitPerMinute <= 0) {
            throw new IllegalArgumentException("QA rate limit must be greater than 0");
        }
        this.rateLimitPerMinute = rateLimitPerMinute;
    }

    public int getQuestionMaxLength() {
        return questionMaxLength;
    }

    public void setQuestionMaxLength(int questionMaxLength) {
        if (questionMaxLength <= 0) {
            throw new IllegalArgumentException("QA question max length must be greater than 0");
        }
        this.questionMaxLength = questionMaxLength;
    }

    public int getMaxEvidenceItems() {
        return maxEvidenceItems;
    }

    public void setMaxEvidenceItems(int maxEvidenceItems) {
        this.maxEvidenceItems = Math.max(1, Math.min(maxEvidenceItems, 8));
    }

    public int getMaxSnippetChars() {
        return maxSnippetChars;
    }

    public void setMaxSnippetChars(int maxSnippetChars) {
        this.maxSnippetChars = Math.max(100, Math.min(maxSnippetChars, 1000));
    }

    public Duration getLlmTimeout() {
        return llmTimeout;
    }

    public void setLlmTimeout(Duration llmTimeout) {
        this.llmTimeout = llmTimeout == null || llmTimeout.isZero() || llmTimeout.isNegative()
            ? Duration.ofSeconds(45)
            : llmTimeout.compareTo(Duration.ofSeconds(45)) > 0 ? Duration.ofSeconds(45) : llmTimeout;
    }

    public int getMaxPromptChars() {
        return maxPromptChars;
    }

    public void setMaxPromptChars(int maxPromptChars) {
        this.maxPromptChars = Math.max(1000, Math.min(maxPromptChars, 12000));
    }

    public int getMaxTokens() {
        return maxTokens;
    }

    public void setMaxTokens(int maxTokens) {
        this.maxTokens = Math.max(128, Math.min(maxTokens, 1024));
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = 1;
    }
}
