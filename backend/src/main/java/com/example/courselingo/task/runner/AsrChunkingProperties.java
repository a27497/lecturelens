package com.example.courselingo.task.runner;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "courselingo.ai.asr.chunking")
public class AsrChunkingProperties {

    private boolean enabled = true;
    private Duration chunkDuration = Duration.ofSeconds(60);
    private DataSize maxAudioFileSize = DataSize.ofMegabytes(5);
    private DataSize maxChunkFileSize = DataSize.ofMegabytes(4);
    private int maxChunks = 180;
    private int concurrency = 2;
    private int maxConcurrency = 4;
    private ChunkRetryProperties chunkRetry = new ChunkRetryProperties();

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public Duration getChunkDuration() {
        return chunkDuration;
    }

    public void setChunkDuration(Duration chunkDuration) {
        this.chunkDuration = chunkDuration;
    }

    public DataSize getMaxAudioFileSize() {
        return maxAudioFileSize;
    }

    public void setMaxAudioFileSize(DataSize maxAudioFileSize) {
        this.maxAudioFileSize = maxAudioFileSize;
    }

    public DataSize getMaxChunkFileSize() {
        return maxChunkFileSize;
    }

    public void setMaxChunkFileSize(DataSize maxChunkFileSize) {
        this.maxChunkFileSize = maxChunkFileSize;
    }

    public int getMaxChunks() {
        return maxChunks;
    }

    public void setMaxChunks(int maxChunks) {
        this.maxChunks = maxChunks;
    }

    public int getConcurrency() {
        return concurrency;
    }

    public void setConcurrency(int concurrency) {
        this.concurrency = concurrency;
    }

    public int getMaxConcurrency() {
        return maxConcurrency;
    }

    public void setMaxConcurrency(int maxConcurrency) {
        this.maxConcurrency = maxConcurrency;
    }

    public ChunkRetryProperties getChunkRetry() {
        return chunkRetry;
    }

    public void setChunkRetry(ChunkRetryProperties chunkRetry) {
        this.chunkRetry = chunkRetry == null ? new ChunkRetryProperties() : chunkRetry;
    }

    long effectiveMaxAudioFileSizeBytes() {
        return toPositiveBytes(maxAudioFileSize);
    }

    long effectiveMaxChunkFileSizeBytes() {
        long maxAudioBytes = effectiveMaxAudioFileSizeBytes();
        long configuredChunkBytes = toPositiveBytes(maxChunkFileSize);
        if (maxAudioBytes <= 0L) {
            return configuredChunkBytes;
        }
        long safeChunkBytes = Math.max(1L, Math.floorDiv(maxAudioBytes * 9L, 10L));
        if (configuredChunkBytes <= 0L) {
            return safeChunkBytes;
        }
        return Math.min(configuredChunkBytes, safeChunkBytes);
    }

    int effectiveConcurrency() {
        int configuredMax = Math.max(1, Math.min(4, maxConcurrency));
        int configuredConcurrency = Math.max(1, concurrency);
        return Math.min(configuredConcurrency, configuredMax);
    }

    private static long toPositiveBytes(DataSize dataSize) {
        if (dataSize == null || dataSize.toBytes() <= 0L) {
            return 0L;
        }
        return dataSize.toBytes();
    }

    public static class ChunkRetryProperties {

        private int maxAttempts = 3;
        private List<Duration> backoff = new ArrayList<>(List.of(
            Duration.ofSeconds(2),
            Duration.ofSeconds(5),
            Duration.ofSeconds(10)
        ));

        public int getMaxAttempts() {
            return maxAttempts;
        }

        public void setMaxAttempts(int maxAttempts) {
            this.maxAttempts = maxAttempts;
        }

        public List<Duration> getBackoff() {
            return backoff;
        }

        public void setBackoff(List<Duration> backoff) {
            this.backoff = backoff == null ? new ArrayList<>() : new ArrayList<>(backoff);
        }
    }
}
