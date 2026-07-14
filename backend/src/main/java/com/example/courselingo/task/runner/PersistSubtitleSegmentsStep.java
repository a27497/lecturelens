package com.example.courselingo.task.runner;

import com.example.courselingo.ai.asr.SpeechToTextResult;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.subtitle.service.SaveTranscriptionSegmentsCommand;
import com.example.courselingo.subtitle.service.SubtitleSegmentPersistenceService;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import java.util.Objects;

final class PersistSubtitleSegmentsStep implements PipelineAnalysisTaskStep {

    private final AnalysisTaskMapper analysisTaskMapper;
    private final SubtitleSegmentPersistenceService subtitleSegmentPersistenceService;

    PersistSubtitleSegmentsStep(
        AnalysisTaskMapper analysisTaskMapper,
        SubtitleSegmentPersistenceService subtitleSegmentPersistenceService
    ) {
        this.analysisTaskMapper = Objects.requireNonNull(
            analysisTaskMapper,
            "analysis task mapper is required"
        );
        this.subtitleSegmentPersistenceService = Objects.requireNonNull(
            subtitleSegmentPersistenceService,
            "subtitle segment persistence service is required"
        );
    }

    @Override
    public PipelineAnalysisTaskStepName name() {
        return PipelineAnalysisTaskStepName.PERSIST_SUBTITLES;
    }

    @Override
    public void execute(PipelineAnalysisTaskStepContext context) {
        if (analysisTaskMapper.selectByIdAndUserId(context.taskId(), context.userId()) == null) {
            throw new BusinessException(ErrorCode.TASK_NOT_FOUND);
        }
        SpeechToTextResult result = context.requireSpeechToTextResult();
        subtitleSegmentPersistenceService.saveTranscriptionResult(new SaveTranscriptionSegmentsCommand(
            context.taskId(),
            context.userId(),
            result
        ));
    }
}
