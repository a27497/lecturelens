package com.example.courselingo.artifact.service;

import com.example.courselingo.artifact.domain.ArtifactType;
import com.example.courselingo.artifact.dto.ArtifactFileView;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.learning.dto.LearningPackageView;
import com.example.courselingo.learning.service.LearningPackageQueryService;
import com.example.courselingo.subtitle.dto.SubtitleSegmentView;
import com.example.courselingo.subtitle.dto.SubtitleTranslationSegmentView;
import com.example.courselingo.subtitle.service.SubtitleSegmentQueryService;
import com.example.courselingo.subtitle.service.SubtitleTranslationQueryService;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class JsonArtifactServiceImpl implements JsonArtifactService {

    private static final int MAX_TASK_ID_LENGTH = 64;
    private static final int MAX_LANGUAGE_LENGTH = 32;
    private static final String CONTENT_TYPE = "application/json; charset=utf-8";

    private final SubtitleSegmentQueryService sourceSubtitleQueryService;
    private final SubtitleTranslationQueryService translatedSubtitleQueryService;
    private final LearningPackageQueryService learningPackageQueryService;
    private final ArtifactFileService artifactFileService;
    private final JsonLearningPackageExporter exporter;

    public JsonArtifactServiceImpl(
        SubtitleSegmentQueryService sourceSubtitleQueryService,
        SubtitleTranslationQueryService translatedSubtitleQueryService,
        LearningPackageQueryService learningPackageQueryService,
        ArtifactFileService artifactFileService,
        JsonLearningPackageExporter exporter
    ) {
        this.sourceSubtitleQueryService = sourceSubtitleQueryService;
        this.translatedSubtitleQueryService = translatedSubtitleQueryService;
        this.learningPackageQueryService = learningPackageQueryService;
        this.artifactFileService = artifactFileService;
        this.exporter = exporter;
    }

    @Override
    public ArtifactFileView generateJsonArtifact(GenerateJsonArtifactCommand command) {
        ValidatedCommand validated = validate(command);
        List<SubtitleSegmentView> sourceSubtitles = sourceSubtitleQueryService
            .listByTaskId(validated.taskId(), validated.userId());
        List<SubtitleTranslationSegmentView> translatedSubtitles = translatedSubtitleQueryService
            .listTranslations(validated.taskId(), validated.userId(), validated.targetLanguage());
        LearningPackageView learningPackage = learningPackageQueryService
            .getByTaskAndLanguage(validated.taskId(), validated.userId(), validated.targetLanguage())
            .orElseThrow(() -> validationFailure("JSON learning package is required"));
        String content = exporter.export(
            validated.taskId(),
            validated.targetLanguage(),
            sourceSubtitles,
            translatedSubtitles,
            learningPackage
        );
        return artifactFileService.saveArtifactFile(new SaveArtifactFileCommand(
            validated.taskId(),
            validated.userId(),
            ArtifactType.JSON,
            validated.targetLanguage(),
            fileName(validated),
            CONTENT_TYPE,
            content.getBytes(StandardCharsets.UTF_8)
        ));
    }

    private ValidatedCommand validate(GenerateJsonArtifactCommand command) {
        if (command == null) {
            throw validationFailure("JSON artifact command is required");
        }
        String taskId = validateIdentifier(command.taskId(), MAX_TASK_ID_LENGTH, "JSON task ID is required");
        if (command.userId() == null || command.userId() <= 0) {
            throw validationFailure("JSON user ID is required");
        }
        String targetLanguage = validateIdentifier(
            command.targetLanguage(),
            MAX_LANGUAGE_LENGTH,
            "JSON target language is required"
        );
        return new ValidatedCommand(taskId, command.userId(), targetLanguage);
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
            throw validationFailure("JSON artifact scope is invalid");
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
        return "task-" + command.taskId() + "-" + command.targetLanguage() + "-learning-package.json";
    }

    private BusinessException validationFailure(String message) {
        return new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, message);
    }

    private record ValidatedCommand(String taskId, Long userId, String targetLanguage) {
    }
}
