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
public class VttArtifactServiceImpl implements VttArtifactService {

    private static final int MAX_TASK_ID_LENGTH = 64;
    private static final int MAX_LANGUAGE_LENGTH = 32;
    private static final String CONTENT_TYPE = "text/vtt; charset=utf-8";

    private final SubtitleTranslationQueryService subtitleQueryService;
    private final SubtitleSegmentQueryService sourceSubtitleQueryService;
    private final ArtifactFileService artifactFileService;
    private final VttFormatter formatter;

    public VttArtifactServiceImpl(
        SubtitleTranslationQueryService subtitleQueryService,
        ArtifactFileService artifactFileService,
        VttFormatter formatter
    ) {
        this(subtitleQueryService, null, artifactFileService, formatter);
    }

    @Autowired
    public VttArtifactServiceImpl(
        SubtitleTranslationQueryService subtitleQueryService,
        SubtitleSegmentQueryService sourceSubtitleQueryService,
        ArtifactFileService artifactFileService,
        VttFormatter formatter
    ) {
        this.subtitleQueryService = subtitleQueryService;
        this.sourceSubtitleQueryService = sourceSubtitleQueryService;
        this.artifactFileService = artifactFileService;
        this.formatter = formatter;
    }

    @Override
    public ArtifactFileView generateVttArtifact(GenerateVttArtifactCommand command) {
        ValidatedCommand validated = validate(command);
        List<VttCue> cues = subtitleQueryService
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
            ArtifactType.VTT,
            validated.language(),
            fileName(validated),
            CONTENT_TYPE,
            content.getBytes(StandardCharsets.UTF_8)
        ));
    }

    private VttCue toCue(SubtitleTranslationSegmentView view) {
        return new VttCue(view.segmentIndex(), view.startMillis(), view.endMillis(), view.translatedText());
    }

    private VttCue toCue(SubtitleSegmentView view) {
        return new VttCue(view.segmentIndex(), view.startMillis(), view.endMillis(), view.text());
    }

    private ValidatedCommand validate(GenerateVttArtifactCommand command) {
        if (command == null) {
            throw validationFailure("VTT artifact command is required");
        }
        String taskId = validateIdentifier(command.taskId(), MAX_TASK_ID_LENGTH, "VTT task ID is required");
        if (command.userId() == null || command.userId() <= 0) {
            throw validationFailure("VTT user ID is required");
        }
        String language = validateIdentifier(command.language(), MAX_LANGUAGE_LENGTH, "VTT language is required");
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
            throw validationFailure("VTT artifact scope is invalid");
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
        return "task-" + command.taskId() + "-" + command.language() + ".vtt";
    }

    private BusinessException validationFailure(String message) {
        return new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, message);
    }

    private record ValidatedCommand(String taskId, Long userId, String language) {
    }
}
