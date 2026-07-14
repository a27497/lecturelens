package com.example.courselingo.task.runner;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.ai.record.domain.AiCallStage;
import com.example.courselingo.ai.record.domain.AiCallType;
import com.example.courselingo.subtitle.service.SubtitleTranslationAiCallResult;
import com.example.courselingo.subtitle.service.SubtitleTranslationService;
import com.example.courselingo.subtitle.service.TranslateSubtitleCommand;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import java.util.Objects;

final class TranslateSubtitleSegmentsStep implements PipelineAnalysisTaskStep {

    private final AnalysisTaskMapper analysisTaskMapper;
    private final SubtitleTranslationService subtitleTranslationService;

    TranslateSubtitleSegmentsStep(
        AnalysisTaskMapper analysisTaskMapper,
        SubtitleTranslationService subtitleTranslationService
    ) {
        this.analysisTaskMapper = Objects.requireNonNull(
            analysisTaskMapper,
            "analysis task mapper is required"
        );
        this.subtitleTranslationService = Objects.requireNonNull(
            subtitleTranslationService,
            "subtitle translation service is required"
        );
    }

    @Override
    public PipelineAnalysisTaskStepName name() {
        return PipelineAnalysisTaskStepName.TRANSLATE_SUBTITLES;
    }

    @Override
    public void execute(PipelineAnalysisTaskStepContext context) {
        if (analysisTaskMapper.selectByIdAndUserId(context.taskId(), context.userId()) == null) {
            throw new BusinessException(ErrorCode.TASK_NOT_FOUND);
        }
        String sourceLanguage = context.requireSpeechToTextResult().language();
        long startedNanos = System.nanoTime();
        try {
            SubtitleTranslationAiCallResult result = subtitleTranslationService.translateTaskSubtitlesWithAiCallRecord(
                new TranslateSubtitleCommand(
                    context.taskId(),
                    context.userId(),
                    sourceLanguage,
                    context.targetLanguage(),
                    context.requestId()
                )
            );
            context.addAiCallRecord(PipelineAiCallRecord.succeeded(
                AiCallType.LLM,
                AiCallStage.TRANSLATION,
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
                "subtitle-translation-service"
            );
            context.addAiCallRecord(PipelineAiCallRecord.failed(
                AiCallType.LLM,
                AiCallStage.TRANSLATION,
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
