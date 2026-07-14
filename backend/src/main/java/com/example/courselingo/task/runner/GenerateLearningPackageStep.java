package com.example.courselingo.task.runner;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.ai.record.domain.AiCallStage;
import com.example.courselingo.ai.record.domain.AiCallType;
import com.example.courselingo.learning.service.GenerateLearningPackageCommand;
import com.example.courselingo.learning.service.LearningPackageAiCallResult;
import com.example.courselingo.learning.service.LearningPackageService;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import java.util.Objects;

final class GenerateLearningPackageStep implements PipelineAnalysisTaskStep {

    private final AnalysisTaskMapper analysisTaskMapper;
    private final LearningPackageService learningPackageService;

    GenerateLearningPackageStep(
        AnalysisTaskMapper analysisTaskMapper,
        LearningPackageService learningPackageService
    ) {
        this.analysisTaskMapper = Objects.requireNonNull(
            analysisTaskMapper,
            "analysis task mapper is required"
        );
        this.learningPackageService = Objects.requireNonNull(
            learningPackageService,
            "learning package service is required"
        );
    }

    @Override
    public PipelineAnalysisTaskStepName name() {
        return PipelineAnalysisTaskStepName.GENERATE_LEARNING_PACKAGE;
    }

    @Override
    public void execute(PipelineAnalysisTaskStepContext context) {
        if (analysisTaskMapper.selectByIdAndUserId(context.taskId(), context.userId()) == null) {
            throw new BusinessException(ErrorCode.TASK_NOT_FOUND);
        }
        String sourceLanguage = context.requireSpeechToTextResult().language();
        long startedNanos = System.nanoTime();
        try {
            LearningPackageAiCallResult result = learningPackageService.generateLearningPackageWithAiCallRecord(
                new GenerateLearningPackageCommand(
                    context.taskId(),
                    context.userId(),
                    sourceLanguage,
                    context.targetLanguage(),
                    context.requestId()
                )
            );
            context.addAiCallRecord(PipelineAiCallRecord.succeeded(
                AiCallType.LLM,
                AiCallStage.LEARNING_PACKAGE,
                result.provider(),
                result.model(),
                durationMillis(result.duration(), startedNanos),
                result.promptTokens(),
                result.completionTokens(),
                result.totalTokens(),
                result.inputUnits(),
                result.outputUnits(),
                result.requestFingerprint(),
                result.responseFingerprint()
            ));
        } catch (RuntimeException exception) {
            LlmFailureDiagnostic diagnostic = LlmFailureDiagnostic.from(
                exception,
                context,
                "learning-package-service"
            );
            context.addAiCallRecord(PipelineAiCallRecord.failed(
                AiCallType.LLM,
                AiCallStage.LEARNING_PACKAGE,
                diagnostic.provider(),
                diagnostic.model(),
                elapsedMillis(startedNanos),
                diagnostic.errorCode(),
                diagnostic.errorMessage(),
                diagnostic.retryable(),
                null,
                null
            ));
            throw exception;
        }
    }

    private static Long durationMillis(java.time.Duration duration, long startedNanos) {
        if (duration == null || duration.isNegative()) {
            return elapsedMillis(startedNanos);
        }
        return duration.toMillis();
    }

    private static long elapsedMillis(long startedNanos) {
        return java.time.Duration.ofNanos(System.nanoTime() - startedNanos).toMillis();
    }
}
