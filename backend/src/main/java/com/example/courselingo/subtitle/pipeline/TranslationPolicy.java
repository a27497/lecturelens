package com.example.courselingo.subtitle.pipeline;

/** Immutable execution parameters, distinct from the system model binding version. */
public record TranslationPolicy(
    String engineVersion, String tokenCounter, long requestTimeoutMillis, long totalTimeoutMillis,
    int outputMin, int outputMax, double outputRatio, int outputSlack, double safetyFactor,
    int contextReserve, int contextLimit, int maxDepth, int maxAttempts, int maxCalls,
    long tokenBudget, int batchMaxSegments, int batchMaxInputChars,
    @com.fasterxml.jackson.annotation.JsonInclude(com.fasterxml.jackson.annotation.JsonInclude.Include.NON_NULL)
    com.example.courselingo.media.SilenceSegmentationPolicy silence,
    @com.fasterxml.jackson.annotation.JsonInclude(com.fasterxml.jackson.annotation.JsonInclude.Include.NON_NULL)
    TranslationAimdPolicy aimd,
    @com.fasterxml.jackson.annotation.JsonInclude(com.fasterxml.jackson.annotation.JsonInclude.Include.NON_NULL)
    TranslationRecoveryPolicy recovery,
    @com.fasterxml.jackson.annotation.JsonInclude(com.fasterxml.jackson.annotation.JsonInclude.Include.NON_NULL)
    String priceSet
) {
    public TranslationPolicy(String engineVersion,String tokenCounter,long requestTimeoutMillis,long totalTimeoutMillis,
        int outputMin,int outputMax,double outputRatio,int outputSlack,double safetyFactor,int contextReserve,
        int contextLimit,int maxDepth,int maxAttempts,int maxCalls,long tokenBudget,int batchMaxSegments,int batchMaxInputChars,
        com.example.courselingo.media.SilenceSegmentationPolicy silence,TranslationAimdPolicy aimd,TranslationRecoveryPolicy recovery) {
        this(engineVersion,tokenCounter,requestTimeoutMillis,totalTimeoutMillis,outputMin,outputMax,outputRatio,outputSlack,safetyFactor,
            contextReserve,contextLimit,maxDepth,maxAttempts,maxCalls,tokenBudget,batchMaxSegments,batchMaxInputChars,silence,aimd,recovery,null);
    }
    public TranslationPolicy(String engineVersion,String tokenCounter,long requestTimeoutMillis,long totalTimeoutMillis,
        int outputMin,int outputMax,double outputRatio,int outputSlack,double safetyFactor,int contextReserve,
        int contextLimit,int maxDepth,int maxAttempts,int maxCalls,long tokenBudget,int batchMaxSegments,int batchMaxInputChars,
        com.example.courselingo.media.SilenceSegmentationPolicy silence,TranslationAimdPolicy aimd) {
        this(engineVersion,tokenCounter,requestTimeoutMillis,totalTimeoutMillis,outputMin,outputMax,outputRatio,outputSlack,safetyFactor,
            contextReserve,contextLimit,maxDepth,maxAttempts,maxCalls,tokenBudget,batchMaxSegments,batchMaxInputChars,silence,aimd,null);
    }
    public TranslationPolicy(String engineVersion,String tokenCounter,long requestTimeoutMillis,long totalTimeoutMillis,
        int outputMin,int outputMax,double outputRatio,int outputSlack,double safetyFactor,int contextReserve,
        int contextLimit,int maxDepth,int maxAttempts,int maxCalls,long tokenBudget,int batchMaxSegments,int batchMaxInputChars,
        com.example.courselingo.media.SilenceSegmentationPolicy silence) {
        this(engineVersion,tokenCounter,requestTimeoutMillis,totalTimeoutMillis,outputMin,outputMax,outputRatio,outputSlack,safetyFactor,
            contextReserve,contextLimit,maxDepth,maxAttempts,maxCalls,tokenBudget,batchMaxSegments,batchMaxInputChars,silence,null,null);
    }
    public TranslationPolicy(String engineVersion,String tokenCounter,long requestTimeoutMillis,long totalTimeoutMillis,
        int outputMin,int outputMax,double outputRatio,int outputSlack,double safetyFactor,int contextReserve,
        int contextLimit,int maxDepth,int maxAttempts,int maxCalls,long tokenBudget,int batchMaxSegments,int batchMaxInputChars) {
        this(engineVersion,tokenCounter,requestTimeoutMillis,totalTimeoutMillis,outputMin,outputMax,outputRatio,outputSlack,safetyFactor,
            contextReserve,contextLimit,maxDepth,maxAttempts,maxCalls,tokenBudget,batchMaxSegments,batchMaxInputChars,null,null,null);
    }
    public TranslationPolicy {
        if (!java.util.Set.of("translation-v2.1","translation-v2.2","translation-v2.3","translation-v2.4","translation-v2.5").contains(engineVersion) || !"UTF8_CONSERVATIVE_V1".equals(tokenCounter)
            || requestTimeoutMillis < 1 || requestTimeoutMillis > 120000
            || totalTimeoutMillis < 1 || totalTimeoutMillis > 900000
            || outputMin < 1 || outputMin > outputMax || outputMax > 8192
            || !Double.isFinite(outputRatio) || outputRatio < 1 || outputRatio > 4
            || outputSlack < 0 || outputSlack > 1024 || !Double.isFinite(safetyFactor)
            || safetyFactor < 1 || safetyFactor > 2 || contextReserve < 0 || contextReserve > 8192
            || contextLimit < 1024 || contextLimit > 1000000 || maxDepth < 0 || maxDepth > 6
            || maxAttempts < 1 || maxAttempts > 3 || maxCalls < 1 || maxCalls > 256
            || tokenBudget < 1 || tokenBudget > 200000 || batchMaxSegments < 1
            || batchMaxSegments > 10000 || batchMaxInputChars < 1 || batchMaxInputChars > 100000)
            throw new IllegalArgumentException("Invalid translation policy");
        if ("translation-v2.2".equals(engineVersion) && silence == null) throw new IllegalArgumentException("Missing frozen silence policy");
        if ("translation-v2.3".equals(engineVersion) && aimd == null) throw new IllegalArgumentException("Missing frozen concurrency policy");
        if ("translation-v2.4".equals(engineVersion) && recovery == null) throw new IllegalArgumentException("Missing frozen recovery policy");
        if("translation-v2.5".equals(engineVersion) && (recovery==null || !"catalog-20261016".equals(priceSet)))throw new IllegalArgumentException("Missing frozen accounting policy");
    }
}
