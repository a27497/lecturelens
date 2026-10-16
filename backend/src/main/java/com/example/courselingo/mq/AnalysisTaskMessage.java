package com.example.courselingo.mq;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.time.Instant;

public record AnalysisTaskMessage(
    String taskId,
    String uploadId,
    Long userId,
    String sourceLanguage,
    String targetLanguage,
    String requestId,
    String traceId,
    Instant createdAt,
    @com.fasterxml.jackson.annotation.JsonInclude(com.fasterxml.jackson.annotation.JsonInclude.Include.NON_NULL) Integer protocolVersion,
    @com.fasterxml.jackson.annotation.JsonInclude(com.fasterxml.jackson.annotation.JsonInclude.Include.NON_NULL) Long executionEpoch
) {
    public AnalysisTaskMessage(String taskId,String uploadId,Long userId,String sourceLanguage,String targetLanguage,
            String requestId,String traceId,Instant createdAt) {
        this(taskId,uploadId,userId,sourceLanguage,targetLanguage,requestId,traceId,createdAt,null,null);
    }
    public int protocol(){return protocolVersion==null?1:protocolVersion;}
    public long epoch(){return executionEpoch==null?0:executionEpoch;}
    public AnalysisTaskMessage withExecution(long epoch) {
        return new AnalysisTaskMessage(taskId,uploadId,userId,sourceLanguage,targetLanguage,requestId,traceId,createdAt,2,epoch);
    }

    public AnalysisTaskMessage {
        // Preserve compatibility with messages produced before source-language
        // selection existed. New producers always send the explicit user choice.
        if (isBlank(sourceLanguage)) {
            sourceLanguage = "auto";
        }
    }

    public AnalysisTaskMessage(
        String taskId,
        String uploadId,
        Long userId,
        String targetLanguage,
        String requestId,
        String traceId,
        Instant createdAt
    ) {
        this(taskId, uploadId, userId, "auto", targetLanguage, requestId, traceId, createdAt);
    }

    public void validate() {
        if (isBlank(taskId)
            || isBlank(uploadId)
            || userId == null
            || isBlank(sourceLanguage)
            || isBlank(targetLanguage)
            || isBlank(requestId)
            || isBlank(traceId)
            || createdAt == null || protocol()!=1 && protocol()!=2 || protocol()==2 && epoch()<1 || protocol()==1 && epoch()!=0) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED);
        }
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }
}
