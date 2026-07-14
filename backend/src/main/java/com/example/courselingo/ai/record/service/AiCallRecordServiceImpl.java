package com.example.courselingo.ai.record.service;

import com.example.courselingo.ai.record.domain.AiCallRecord;
import com.example.courselingo.ai.record.domain.AiCallRecordStatus;
import com.example.courselingo.ai.record.domain.AiCallStage;
import com.example.courselingo.ai.record.domain.AiCallType;
import com.example.courselingo.ai.record.dto.AiCallRecordView;
import com.example.courselingo.ai.record.dto.CompleteAiCallRecordCommand;
import com.example.courselingo.ai.record.dto.FailAiCallRecordCommand;
import com.example.courselingo.ai.record.dto.StartAiCallRecordCommand;
import com.example.courselingo.ai.record.mapper.AiCallRecordMapper;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.List;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AiCallRecordServiceImpl implements AiCallRecordService {

    private final AiCallRecordMapper mapper;
    private final Clock clock;
    private final AiCallRecordSanitizer sanitizer;

    @Autowired
    public AiCallRecordServiceImpl(AiCallRecordMapper mapper, AiCallRecordSanitizer sanitizer) {
        this(mapper, Clock.systemUTC(), sanitizer);
    }

    public AiCallRecordServiceImpl(AiCallRecordMapper mapper, Clock clock, AiCallRecordSanitizer sanitizer) {
        this.mapper = mapper;
        this.clock = clock == null ? Clock.systemUTC() : clock;
        this.sanitizer = sanitizer == null ? new AiCallRecordSanitizer() : sanitizer;
    }

    @Override
    @Transactional
    public AiCallRecordView startCall(StartAiCallRecordCommand command) {
        ValidatedStartAiCallRecordCommand validated = AiCallRecordValidators.validateStart(command, sanitizer);
        LocalDateTime now = now();
        AiCallRecord record = new AiCallRecord();
        record.setTaskId(validated.taskId());
        record.setUserId(validated.userId());
        record.setCallType(validated.callType().name());
        record.setStage(validated.stage().name());
        record.setProvider(validated.provider());
        record.setModel(validated.model());
        record.setStatus(AiCallRecordStatus.STARTED.name());
        record.setStartedAt(now);
        record.setInputUnits(validated.inputUnits());
        record.setRequestFingerprint(validated.requestFingerprint());
        record.setCreatedAt(now);
        record.setUpdatedAt(now);
        if (mapper.insert(record) != 1) {
            throw new BusinessException(ErrorCode.COMMON_INTERNAL_ERROR, "AI call record insert failed");
        }
        return toView(record);
    }

    @Override
    @Transactional
    public AiCallRecordView completeCall(CompleteAiCallRecordCommand command) {
        ValidatedCompleteAiCallRecordCommand validated = AiCallRecordValidators.validateComplete(command, sanitizer);
        AiCallRecord existing = findOwnedRecord(validated.recordId(), validated.taskId(), validated.userId());
        AiCallRecord update = new AiCallRecord();
        update.setStatus(AiCallRecordStatus.SUCCEEDED.name());
        update.setFinishedAt(now());
        update.setDurationMillis(validated.durationMillis());
        update.setPromptTokens(validated.promptTokens());
        update.setCompletionTokens(validated.completionTokens());
        update.setTotalTokens(validated.totalTokens());
        update.setInputUnits(validated.inputUnits());
        update.setOutputUnits(validated.outputUnits());
        update.setRequestFingerprint(validated.requestFingerprint());
        update.setResponseFingerprint(validated.responseFingerprint());
        update.setErrorCode(null);
        update.setErrorMessage(null);
        update.setRetryable(null);
        update.setUpdatedAt(now());
        updateOwnedRecord(update, validated.recordId(), validated.taskId(), validated.userId());
        copyMutableFields(existing, update);
        return toView(existing);
    }

    @Override
    @Transactional
    public AiCallRecordView failCall(FailAiCallRecordCommand command) {
        ValidatedFailAiCallRecordCommand validated = AiCallRecordValidators.validateFail(command, sanitizer);
        AiCallRecord existing = findOwnedRecord(validated.recordId(), validated.taskId(), validated.userId());
        AiCallRecord update = new AiCallRecord();
        update.setStatus(AiCallRecordStatus.FAILED.name());
        update.setFinishedAt(now());
        update.setDurationMillis(validated.durationMillis());
        update.setRequestFingerprint(validated.requestFingerprint());
        update.setResponseFingerprint(validated.responseFingerprint());
        update.setErrorCode(validated.errorCode());
        update.setErrorMessage(validated.errorMessage());
        update.setRetryable(validated.retryable());
        update.setUpdatedAt(now());
        updateOwnedRecord(update, validated.recordId(), validated.taskId(), validated.userId());
        copyMutableFields(existing, update);
        return toView(existing);
    }

    @Override
    public List<AiCallRecordView> listByTask(String taskId, Long userId) {
        ValidatedAiCallRecordScope scope = AiCallRecordValidators.validateScope(taskId, userId, sanitizer);
        return mapper.selectByTaskIdAndUserId(scope.taskId(), scope.userId())
            .stream()
            .map(AiCallRecordServiceImpl::toView)
            .toList();
    }

    private AiCallRecord findOwnedRecord(Long recordId, String taskId, Long userId) {
        AiCallRecord record = mapper.selectByIdTaskIdAndUserId(recordId, taskId, userId);
        if (record == null) {
            throw new BusinessException(ErrorCode.COMMON_NOT_FOUND, "AI call record not found");
        }
        return record;
    }

    private void updateOwnedRecord(AiCallRecord update, Long recordId, String taskId, Long userId) {
        if (mapper.updateByIdTaskIdAndUserId(update, recordId, taskId, userId) != 1) {
            throw new BusinessException(ErrorCode.COMMON_NOT_FOUND, "AI call record not found");
        }
    }

    private static void copyMutableFields(AiCallRecord target, AiCallRecord source) {
        target.setStatus(source.getStatus());
        target.setFinishedAt(source.getFinishedAt());
        target.setDurationMillis(source.getDurationMillis());
        target.setPromptTokens(source.getPromptTokens());
        target.setCompletionTokens(source.getCompletionTokens());
        target.setTotalTokens(source.getTotalTokens());
        target.setInputUnits(source.getInputUnits());
        target.setOutputUnits(source.getOutputUnits());
        target.setRequestFingerprint(source.getRequestFingerprint());
        target.setResponseFingerprint(source.getResponseFingerprint());
        target.setErrorCode(source.getErrorCode());
        target.setErrorMessage(source.getErrorMessage());
        target.setRetryable(source.getRetryable());
        target.setUpdatedAt(source.getUpdatedAt());
    }

    private static AiCallRecordView toView(AiCallRecord record) {
        return new AiCallRecordView(
            record.getId(),
            record.getTaskId(),
            AiCallType.valueOf(record.getCallType()),
            AiCallStage.valueOf(record.getStage()),
            record.getProvider(),
            record.getModel(),
            AiCallRecordStatus.valueOf(record.getStatus()),
            record.getStartedAt(),
            record.getFinishedAt(),
            record.getDurationMillis(),
            record.getPromptTokens(),
            record.getCompletionTokens(),
            record.getTotalTokens(),
            record.getInputUnits(),
            record.getOutputUnits(),
            record.getRequestFingerprint(),
            record.getResponseFingerprint(),
            record.getErrorCode(),
            record.getErrorMessage(),
            record.getRetryable(),
            record.getCreatedAt(),
            record.getUpdatedAt()
        );
    }

    private LocalDateTime now() {
        return LocalDateTime.ofInstant(clock.instant(), clock.getZone());
    }
}
