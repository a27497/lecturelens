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
    private Silence silence = new Silence();
    private Adaptive adaptive=new Adaptive();
    private boolean checkpointEnabled=true;
    private int maxRecoveries=3;
    public boolean isCheckpointEnabled(){return checkpointEnabled;}public void setCheckpointEnabled(boolean value){checkpointEnabled=value;}
    public int getMaxRecoveries(){return maxRecoveries;}public void setMaxRecoveries(int value){maxRecoveries=value;}
    public Adaptive getAdaptive(){return adaptive;} public void setAdaptive(Adaptive v){adaptive=v;}
    public static class Adaptive {
        private boolean enabled=true;
        private int inputTokenBudget=2048,initial=1,maximum=4,successStreak=3,processMaximum=4;
        public boolean isEnabled(){return enabled;}public void setEnabled(boolean v){enabled=v;}
        public int getInputTokenBudget(){return inputTokenBudget;}public void setInputTokenBudget(int v){inputTokenBudget=v;}
        public int getInitial(){return initial;}public void setInitial(int v){initial=v;}
        public int getMaximum(){return maximum;}public void setMaximum(int v){maximum=v;}
        public int getSuccessStreak(){return successStreak;}public void setSuccessStreak(int v){successStreak=v;}
        public int getProcessMaximum(){return processMaximum;}public void setProcessMaximum(int v){processMaximum=v;}
    }
    public Silence getSilence() { return silence; }
    public void setSilence(Silence value) { silence = value; }
    public static class Silence {
        private boolean enabled=true;
        private int noiseDb=-35, maxClips=256;
        private long pauseMillis=600,minMillis=15000,targetMillis=30000,maxMillis=60000;
        public boolean isEnabled(){return enabled;} public void setEnabled(boolean v){enabled=v;}
        public int getNoiseDb(){return noiseDb;} public void setNoiseDb(int v){noiseDb=v;}
        public int getMaxClips(){return maxClips;} public void setMaxClips(int v){maxClips=v;}
        public long getPauseMillis(){return pauseMillis;} public void setPauseMillis(long v){pauseMillis=v;}
        public long getMinMillis(){return minMillis;} public void setMinMillis(long v){minMillis=v;}
        public long getTargetMillis(){return targetMillis;} public void setTargetMillis(long v){targetMillis=v;}
        public long getMaxMillis(){return maxMillis;} public void setMaxMillis(long v){maxMillis=v;}
    }

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
    public TranslationPolicy freezeWithSilence(Duration requestTimeout,Duration totalTimeout,int segments,int chars,
            int sampleRate,int channels,int concurrency,long maxClipBytes) {
        return freezeWithSilence(requestTimeout,totalTimeout,segments,chars,sampleRate,channels,concurrency,maxClipBytes,3,
            java.util.List.of(2000L,5000L,10000L));
    }

    public TranslationPolicy freezePipeline(Duration requestTimeout,Duration totalTimeout,int segments,int chars,
            int sampleRate,int channels,int concurrency,long maxClipBytes,int maxAsrAttempts,java.util.List<Long> retryBackoff) {
        var p=freezeAdaptive(requestTimeout,totalTimeout,segments,chars,sampleRate,channels,concurrency,maxClipBytes,maxAsrAttempts,retryBackoff);
        if(!checkpointEnabled)return p;
        return new TranslationPolicy("translation-v2.5",p.tokenCounter(),p.requestTimeoutMillis(),p.totalTimeoutMillis(),p.outputMin(),p.outputMax(),
            p.outputRatio(),p.outputSlack(),p.safetyFactor(),p.contextReserve(),p.contextLimit(),p.maxDepth(),p.maxAttempts(),p.maxCalls(),p.tokenBudget(),
            p.batchMaxSegments(),p.batchMaxInputChars(),p.silence(),p.aimd(),new TranslationRecoveryPolicy(maxRecoveries),"catalog-20261016");
    }
    private TranslationPolicy freezeAdaptive(Duration requestTimeout,Duration totalTimeout,int segments,int chars,
            int sampleRate,int channels,int concurrency,long maxClipBytes,int maxAsrAttempts,java.util.List<Long> retryBackoff) {
        var p=freezeWithSilence(requestTimeout,totalTimeout,segments,chars,sampleRate,channels,concurrency,maxClipBytes,maxAsrAttempts,retryBackoff);
        if(!adaptive.enabled) return p;
        var a=new TranslationAimdPolicy(adaptive.inputTokenBudget,1,adaptive.initial,adaptive.maximum,adaptive.successStreak,adaptive.processMaximum);
        return new TranslationPolicy("translation-v2.3",p.tokenCounter(),p.requestTimeoutMillis(),p.totalTimeoutMillis(),p.outputMin(),p.outputMax(),
            p.outputRatio(),p.outputSlack(),p.safetyFactor(),p.contextReserve(),p.contextLimit(),p.maxDepth(),p.maxAttempts(),p.maxCalls(),
            p.tokenBudget(),p.batchMaxSegments(),p.batchMaxInputChars(),p.silence(),a);
    }
    public TranslationPolicy freezeWithSilence(Duration requestTimeout,Duration totalTimeout,int segments,int chars,
            int sampleRate,int channels,int concurrency,long maxClipBytes,int maxAsrAttempts,java.util.List<Long> retryBackoff) {
        var p=freeze(requestTimeout,totalTimeout,segments,chars);
        if (!silence.isEnabled()) return p;
        var s=new com.example.courselingo.media.SilenceSegmentationPolicy(silence.noiseDb,silence.pauseMillis,silence.minMillis,
            silence.targetMillis,silence.maxMillis,silence.maxClips,sampleRate,channels,concurrency,maxClipBytes,maxAsrAttempts,retryBackoff);
        return new TranslationPolicy("translation-v2.2",p.tokenCounter(),p.requestTimeoutMillis(),p.totalTimeoutMillis(),
            p.outputMin(),p.outputMax(),p.outputRatio(),p.outputSlack(),p.safetyFactor(),p.contextReserve(),p.contextLimit(),
            p.maxDepth(),p.maxAttempts(),p.maxCalls(),p.tokenBudget(),p.batchMaxSegments(),p.batchMaxInputChars(),s);
    }
}
