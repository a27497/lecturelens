package com.example.courselingo.media;

public record SilenceSegmentationPolicy(int noiseDb, long pauseMillis, long minMillis,
    long targetMillis, long maxMillis, int maxClips, int sampleRate, int channels,
    int asrConcurrency, long maxClipBytes,int asrMaxAttempts,java.util.List<Long> retryBackoffMillis) {
    public SilenceSegmentationPolicy(int noiseDb,long pauseMillis,long minMillis,long targetMillis,long maxMillis,
            int maxClips,int sampleRate,int channels,int asrConcurrency,long maxClipBytes) {
        this(noiseDb,pauseMillis,minMillis,targetMillis,maxMillis,maxClips,sampleRate,channels,asrConcurrency,maxClipBytes,
            3,java.util.List.of(2000L,5000L,10000L));
    }
    public SilenceSegmentationPolicy {
        if (noiseDb < -80 || noiseDb > -10 || pauseMillis < 100 || pauseMillis > 5000
            || minMillis < 1000 || targetMillis < minMillis || maxMillis < targetMillis || maxMillis > 120000
            || maxClips < 1 || maxClips > 256 || sampleRate < 8000 || sampleRate > 48000
            || channels < 1 || channels > 2 || asrConcurrency < 1 || asrConcurrency > 4 || maxClipBytes < 8192
            || maxClipBytes>128L*1024*1024 || asrMaxAttempts<1 || asrMaxAttempts>3 || retryBackoffMillis==null
            || retryBackoffMillis.size()>3 || retryBackoffMillis.stream().anyMatch(v->v==null || v<0 || v>30000))
            throw new IllegalArgumentException("Invalid silence segmentation policy");
        retryBackoffMillis=java.util.List.copyOf(retryBackoffMillis);
    }
}
