package com.example.courselingo.subtitle.service;

import com.example.courselingo.ai.asr.SpeechToTextResult;
import com.example.courselingo.ai.asr.TranscribedSegment;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.subtitle.mapper.SubtitleSegmentMapper;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.List;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SubtitleSegmentPersistenceServiceImpl implements SubtitleSegmentPersistenceService {

    private static final int MAX_TASK_ID_LENGTH = 64;
    private static final int MAX_LANGUAGE_LENGTH = 32;
    private static final int MAX_PROVIDER_LENGTH = 64;

    private final SubtitleSegmentMapper mapper;
    private final Clock clock;

    @Autowired
    public SubtitleSegmentPersistenceServiceImpl(SubtitleSegmentMapper mapper) {
        this(mapper, Clock.systemUTC());
    }

    public SubtitleSegmentPersistenceServiceImpl(SubtitleSegmentMapper mapper, Clock clock) {
        this.mapper = mapper;
        this.clock = clock == null ? Clock.systemUTC() : clock;
    }

    @Override
    @Transactional
    public int saveTranscriptionResult(SaveTranscriptionSegmentsCommand command) {
        ValidatedCommand validated = validateSaveCommand(command);
        mapper.deleteByTaskIdAndUserId(validated.taskId(), validated.userId());

        LocalDateTime now = LocalDateTime.ofInstant(clock.instant(), clock.getZone());
        int insertedCount = 0;
        for (TranscribedSegment segment : validated.segments()) {
            int inserted = mapper.insert(toEntity(validated, segment, now));
            if (inserted != 1) {
                throw new BusinessException(ErrorCode.COMMON_INTERNAL_ERROR, "Subtitle segment persistence failed");
            }
            insertedCount++;
        }
        return insertedCount;
    }

    @Override
    public int deleteByTaskId(String taskId, Long userId) {
        validateTaskAndUser(taskId, userId);
        return mapper.deleteByTaskIdAndUserId(taskId.strip(), userId);
    }

    private static ValidatedCommand validateSaveCommand(SaveTranscriptionSegmentsCommand command) {
        if (command == null) {
            throw validationFailure("Subtitle segment command is required");
        }
        validateTaskAndUser(command.taskId(), command.userId());
        SpeechToTextResult result = command.result();
        if (result == null) {
            throw validationFailure("ASR result is required");
        }
        String language = requiredText(result.language(), "ASR result language is required");
        if (language.length() > MAX_LANGUAGE_LENGTH) {
            throw validationFailure("ASR result language is invalid");
        }
        String provider = normalizeProvider(result.provider());
        List<TranscribedSegment> segments = result.segments();
        if (segments == null || segments.isEmpty()) {
            throw validationFailure("ASR result segments are required");
        }
        for (TranscribedSegment segment : segments) {
            validateSegment(segment);
        }
        return new ValidatedCommand(command.taskId().strip(), command.userId(), language, provider, segments);
    }

    private static void validateTaskAndUser(String taskId, Long userId) {
        String normalizedTaskId = requiredText(taskId, "Task ID is required");
        if (normalizedTaskId.length() > MAX_TASK_ID_LENGTH) {
            throw validationFailure("Task ID is invalid");
        }
        if (userId == null || userId <= 0) {
            throw validationFailure("User ID is required");
        }
    }

    private static void validateSegment(TranscribedSegment segment) {
        if (segment == null) {
            throw validationFailure("ASR segment is required");
        }
        if (segment.index() < 0) {
            throw validationFailure("ASR segment index is invalid");
        }
        if (segment.startMillis() < 0) {
            throw validationFailure("ASR segment start is invalid");
        }
        if (segment.endMillis() < segment.startMillis()) {
            throw validationFailure("ASR segment end is invalid");
        }
        requiredText(segment.text(), "ASR segment text is required");
    }

    private static String normalizeProvider(String provider) {
        if (provider == null || provider.isBlank()) {
            return null;
        }
        String normalized = provider.strip();
        if (normalized.length() > MAX_PROVIDER_LENGTH || SubtitleSensitiveDataValidator.containsSensitiveData(normalized)) {
            throw validationFailure("ASR provider is invalid");
        }
        return normalized;
    }

    private static String requiredText(String value, String message) {
        if (value == null || value.isBlank()) {
            throw validationFailure(message);
        }
        return value.strip();
    }

    private static BusinessException validationFailure(String message) {
        return new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, message);
    }

    private static SubtitleSegment toEntity(ValidatedCommand command, TranscribedSegment segment, LocalDateTime now) {
        SubtitleSegment entity = new SubtitleSegment();
        entity.setTaskId(command.taskId());
        entity.setUserId(command.userId());
        entity.setSegmentIndex(segment.index());
        entity.setStartMillis(segment.startMillis());
        entity.setEndMillis(segment.endMillis());
        entity.setLanguage(command.language());
        entity.setText(segment.text().strip());
        entity.setProvider(command.provider());
        entity.setCreatedAt(now);
        entity.setUpdatedAt(now);
        return entity;
    }

    private record ValidatedCommand(
        String taskId,
        Long userId,
        String language,
        String provider,
        List<TranscribedSegment> segments
    ) {
    }
}
