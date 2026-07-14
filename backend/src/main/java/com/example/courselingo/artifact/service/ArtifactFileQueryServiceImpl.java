package com.example.courselingo.artifact.service;

import com.example.courselingo.artifact.domain.ArtifactType;
import com.example.courselingo.artifact.dto.ArtifactFileView;
import com.example.courselingo.artifact.mapper.ArtifactFileMapper;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class ArtifactFileQueryServiceImpl implements ArtifactFileQueryService {

    private final ArtifactFileMapper mapper;

    public ArtifactFileQueryServiceImpl(ArtifactFileMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public List<ArtifactFileView> listByTaskId(String taskId, Long userId) {
        ValidatedArtifactTaskScope scope = ArtifactFileValidators.validateTaskScope(taskId, userId);
        return mapper.selectByTaskIdAndUserId(scope.taskId(), scope.userId())
            .stream()
            .map(ArtifactFileViewMapper::toView)
            .toList();
    }

    @Override
    public Optional<ArtifactFileView> getByTaskTypeAndLanguage(
        String taskId,
        Long userId,
        ArtifactType artifactType,
        String language
    ) {
        ValidatedArtifactFileScope scope = ArtifactFileValidators.validateScope(taskId, userId, artifactType, language);
        return Optional.ofNullable(mapper.selectByScope(
            scope.taskId(),
            scope.userId(),
            scope.artifactType().name(),
            scope.language()
        )).map(ArtifactFileViewMapper::toView);
    }

    @Override
    public long countByScope(String taskId, Long userId, ArtifactType artifactType, String language) {
        ValidatedArtifactFileScope scope = ArtifactFileValidators.validateScope(taskId, userId, artifactType, language);
        return mapper.countByScope(scope.taskId(), scope.userId(), scope.artifactType().name(), scope.language());
    }
}
