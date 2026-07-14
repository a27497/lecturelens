package com.example.courselingo.artifact.service;

import com.example.courselingo.artifact.domain.ArtifactType;
import com.example.courselingo.artifact.dto.ArtifactFileView;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.subtitle.dto.SubtitleSegmentView;
import com.example.courselingo.subtitle.dto.SubtitleTranslationSegmentView;
import com.example.courselingo.subtitle.service.SubtitleSegmentQueryService;
import com.example.courselingo.subtitle.service.SubtitleTranslationQueryService;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class SrtArtifactServiceImpl implements SrtArtifactService {

    private static final int MAX_TASK_ID_LENGTH = 64;
    private static final int MAX_LANGUAGE_LENGTH = 32;
    private static final String CONTENT_TYPE = "application/x-subrip";

    private final SubtitleTranslationQueryService subtitleQueryService;
    private final SubtitleSegmentQueryService sourceSubtitleQueryService;
    private final ArtifactFileService artifactFileService;
    private final SrtFormatter formatter;

    public SrtArtifactServiceImpl(
        SubtitleTranslationQueryService subtitleQueryService,
        ArtifactFileService artifactFileService,
        SrtFormatter formatter
    ) {
        this(subtitleQueryService, null, artifactFileService, formatter);
    }

    @Autowired
    public SrtArtifactServiceImpl(
        SubtitleTranslationQueryService subtitleQueryService,
        SubtitleSegmentQueryService sourceSubtitleQueryService,
        ArtifactFileService artifactFileService,
        SrtFormatter formatter
    ) {
        this.subtitleQueryService = subtitleQueryService;
        this.sourceSubtitleQueryService = sourceSubtitleQueryService;
        this.artifactFileService = artifactFileService;
        this.formatter = formatter;
    }

    @Override
    public ArtifactFileView generateSrtArtifact(GenerateSrtArtifactCommand command) {
        ValidatedCommand validated = validate(command);
        List<SrtCue> cues = subtitleQueryService
            .listTranslations(validated.taskId(), validated.userId(), validated.language())
            .stream()
            .map(this::toCue)
            .toList();
        if (cues.isEmpty() && sourceSubtitleQueryService != null) {
            cues = sourceSubtitleQueryService.listByTaskId(validated.taskId(), validated.userId())
                .stream()
                .map(this::toCue)
                .toList();
        }
        String content = formatter.format(cues);
        return artifactFileService.saveArtifactFile(new SaveArtifactFileCommand(
            validated.taskId(),
            validated.userId(),
            ArtifactType.SRT,
            validated.language(),
            fileName(validated),
            CONTENT_TYPE,
            content.getBytes(StandardCharsets.UTF_8)
        ));
    }

    private SrtCue toCue(SubtitleTranslationSegmentView view) {
        return new SrtCue(view.segmentIndex(), view.startMillis(), view.endMillis(), view.translatedText());
    }

    private SrtCue toCue(SubtitleSegmentView view) {
        return new SrtCue(view.segmentIndex(), view.startMillis(), view.endMillis(), view.text());
    }

    private ValidatedCommand validate(GenerateSrtArtifactCommand command) {
        if (command == null) {
            throw validationFailure("SRT artifact command is required");
        }
        String taskId = validateIdentifier(command.taskId(), MAX_TASK_ID_LENGTH, "SRT task ID is required");
        if (command.userId() == null || command.userId() <= 0) {
            throw validationFailure("SRT user ID is required");
        }
        String language = validateIdentifier(command.language(), MAX_LANGUAGE_LENGTH, "SRT language is required");
        return new ValidatedCommand(taskId, command.userId(), language);
    }

    private String validateIdentifier(String value, int maxLength, String requiredMessage) {
        if (value == null || value.isBlank()) {
            throw validationFailure(requiredMessage);
        }
        String normalized = value.trim();
        if (normalized.length() > maxLength
            || normalized.contains("/")
            || normalized.contains("\\")
            || normalized.contains("..")
            || normalized.contains(":")
            || containsControlCharacter(normalized)
            || ArtifactSensitiveDataValidator.containsSensitiveData(normalized)) {
            throw validationFailure("SRT artifact scope is invalid");
        }
        return normalized;
    }

    private boolean containsControlCharacter(String value) {
        for (int i = 0; i < value.length(); i++) {
            if (Character.isISOControl(value.charAt(i))) {
                return true;
            }
        }
        return false;
    }

    private String fileName(ValidatedCommand command) {
        return "task-" + command.taskId() + "-" + command.language() + ".srt";
    }

    private BusinessException validationFailure(String message) {
        return new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, message);
    }

    private record ValidatedCommand(String taskId, Long userId, String language) {
    }
}
