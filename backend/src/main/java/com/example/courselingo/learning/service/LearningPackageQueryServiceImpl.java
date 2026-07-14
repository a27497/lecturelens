package com.example.courselingo.learning.service;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.learning.domain.LearningPackage;
import com.example.courselingo.learning.dto.LearningPackageView;
import com.example.courselingo.learning.mapper.LearningPackageMapper;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class LearningPackageQueryServiceImpl implements LearningPackageQueryService {

    private final LearningPackageMapper mapper;

    public LearningPackageQueryServiceImpl(LearningPackageMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public Optional<LearningPackageView> getByTaskAndLanguage(String taskId, Long userId, String targetLanguage) {
        ValidatedLearningPackageScope scope = LearningPackageValidators.validateScope(taskId, userId, targetLanguage);
        return Optional.ofNullable(mapper.selectByTaskIdUserIdAndTargetLanguage(
            scope.taskId(),
            scope.userId(),
            scope.targetLanguage()
        )).map(LearningPackageQueryServiceImpl::toView);
    }

    @Override
    public long countByTaskIdAndLanguage(String taskId, Long userId, String targetLanguage) {
        ValidatedLearningPackageScope scope = LearningPackageValidators.validateScope(taskId, userId, targetLanguage);
        return mapper.countByTaskIdAndLanguage(scope.taskId(), scope.userId(), scope.targetLanguage());
    }

    private static LearningPackageView toView(LearningPackage entity) {
        if (entity.getTitle() == null
            || entity.getTitle().isBlank()
            || entity.getSummary() == null
            || entity.getSummary().isBlank()
            || entity.getKeyPointsJson() == null
            || entity.getKeyPointsJson().isBlank()
            || entity.getGlossaryJson() == null
            || entity.getGlossaryJson().isBlank()
            || entity.getQaJson() == null
            || entity.getQaJson().isBlank()) {
            throw new BusinessException(ErrorCode.COMMON_INTERNAL_ERROR, "Learning package row is invalid");
        }
        return new LearningPackageView(
            entity.getTaskId(),
            entity.getSourceLanguage(),
            entity.getTargetLanguage(),
            entity.getTitle(),
            entity.getSummary(),
            entity.getKeyPointsJson(),
            entity.getGlossaryJson(),
            entity.getQaJson(),
            entity.getProvider(),
            entity.getSchemaVersion(),
            entity.getCreatedAt(),
            entity.getUpdatedAt()
        );
    }
}
