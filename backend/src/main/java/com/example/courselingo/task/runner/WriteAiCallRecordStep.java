package com.example.courselingo.task.runner;

import com.example.courselingo.ai.record.dto.AiCallRecordView;
import com.example.courselingo.ai.record.dto.CompleteAiCallRecordCommand;
import com.example.courselingo.ai.record.dto.FailAiCallRecordCommand;
import com.example.courselingo.ai.record.dto.StartAiCallRecordCommand;
import com.example.courselingo.ai.record.service.AiCallRecordService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import java.util.List;
import java.util.Objects;

final class WriteAiCallRecordStep implements PipelineAnalysisTaskStep {

    private final AnalysisTaskMapper analysisTaskMapper;
    private final AiCallRecordService aiCallRecordService;

    WriteAiCallRecordStep(
        AnalysisTaskMapper analysisTaskMapper,
        AiCallRecordService aiCallRecordService
    ) {
        this.analysisTaskMapper = Objects.requireNonNull(
            analysisTaskMapper,
            "analysis task mapper is required"
        );
        this.aiCallRecordService = Objects.requireNonNull(
            aiCallRecordService,
            "AI call record service is required"
        );
    }

    @Override
    public PipelineAnalysisTaskStepName name() {
        return PipelineAnalysisTaskStepName.WRITE_AI_CALL_RECORD;
    }

    @Override
    public void execute(PipelineAnalysisTaskStepContext context) {
        List<PipelineAiCallRecord> records = context.drainAiCallRecords();
        if (records.isEmpty()) {
            return;
        }
        if (analysisTaskMapper.selectByIdAndUserId(context.taskId(), context.userId()) == null) {
            context.restoreAiCallRecords(records);
            throw new BusinessException(ErrorCode.TASK_NOT_FOUND);
        }
        for (PipelineAiCallRecord record : records) {
            AiCallRecordView started = aiCallRecordService.startCall(new StartAiCallRecordCommand(
                context.taskId(),
                context.userId(),
                record.callType(),
                record.stage(),
                record.provider(),
                record.model(),
                record.requestFingerprint(),
                record.inputUnits()
            ));
            if (record.success()) {
                aiCallRecordService.completeCall(new CompleteAiCallRecordCommand(
                    started.id(),
                    context.taskId(),
                    context.userId(),
                    record.durationMillis(),
                    record.promptTokens(),
                    record.completionTokens(),
                    record.totalTokens(),
                    record.inputUnits(),
                    record.outputUnits(),
                    record.requestFingerprint(),
                    record.responseFingerprint()
                ));
            } else {
                aiCallRecordService.failCall(new FailAiCallRecordCommand(
                    started.id(),
                    context.taskId(),
                    context.userId(),
                    record.durationMillis(),
                    record.errorCode(),
                    record.errorMessage(),
                    record.retryable(),
                    record.requestFingerprint(),
                    record.responseFingerprint()
                ));
            }
        }
    }
}
