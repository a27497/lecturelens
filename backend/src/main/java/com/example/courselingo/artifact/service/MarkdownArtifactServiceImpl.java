package com.example.courselingo.artifact.service;

import com.example.courselingo.artifact.domain.ArtifactType;
import com.example.courselingo.artifact.dto.ArtifactFileView;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.learning.dto.LearningPackageView;
import com.example.courselingo.learning.service.LearningPackageQueryService;
import java.nio.charset.StandardCharsets;
import org.springframework.stereotype.Service;

@Service
public class MarkdownArtifactServiceImpl implements MarkdownArtifactService {

    private static final int MAX_TASK_ID_LENGTH = 64;
    private static final int MAX_LANGUAGE_LENGTH = 32;
    private static final String CONTENT_TYPE = "text/markdown; charset=utf-8";

    private final LearningPackageQueryService learningPackageQueryService;
    private final ArtifactFileService artifactFileService;
    private final MarkdownLearningPackageFormatter formatter;

    public MarkdownArtifactServiceImpl(
        LearningPackageQueryService learningPackageQueryService,
        ArtifactFileService artifactFileService,
        MarkdownLearningPackageFormatter formatter
    ) {
        this.learningPackageQueryService = learningPackageQueryService;
        this.artifactFileService = artifactFileService;
        this.formatter = formatter;
    }

    @Override
    public ArtifactFileView generateMarkdownArtifact(GenerateMarkdownArtifactCommand command) {
        ValidatedCommand validated = validate(command);
        LearningPackageView learningPackage = learningPackageQueryService
            .getByTaskAndLanguage(validated.taskId(), validated.userId(), validated.targetLanguage())
            .orElseThrow(() -> validationFailure("Markdown learning package is required"));
        String content = formatter.format(learningPackage);
        return artifactFileService.saveArtifactFile(new SaveArtifactFileCommand(
            validated.taskId(),
            validated.userId(),
            ArtifactType.MARKDOWN,
            validated.targetLanguage(),
            fileName(validated),
            CONTENT_TYPE,
            content.getBytes(StandardCharsets.UTF_8)
        ));
    }

    private ValidatedCommand validate(GenerateMarkdownArtifactCommand command) {
        if (command == null) {
            throw validationFailure("Markdown artifact command is required");
        }
        String taskId = validateIdentifier(command.taskId(), MAX_TASK_ID_LENGTH, "Markdown task ID is required");
        if (command.userId() == null || command.userId() <= 0) {
            throw validationFailure("Markdown user ID is required");
        }
        String targetLanguage = validateIdentifier(
            command.targetLanguage(),
            MAX_LANGUAGE_LENGTH,
            "Markdown target language is required"
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
            throw validationFailure("Markdown artifact scope is invalid");
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
        return "task-" + command.taskId() + "-" + command.targetLanguage() + "-learning-package.md";
    }

    private BusinessException validationFailure(String message) {
        return new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, message);
    }

    private record ValidatedCommand(String taskId, Long userId, String targetLanguage) {
    }
}
