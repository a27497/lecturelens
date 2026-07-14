package com.example.courselingo.subtitle.service;

import com.example.courselingo.subtitle.domain.TaskFullTextResult;
import com.example.courselingo.subtitle.dto.TaskFullTextResultView;
import com.example.courselingo.subtitle.mapper.TaskFullTextResultMapper;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class TaskFullTextResultQueryServiceImpl implements TaskFullTextResultQueryService {

    private final TaskFullTextResultMapper mapper;

    public TaskFullTextResultQueryServiceImpl(TaskFullTextResultMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public Optional<TaskFullTextResultView> getByTaskAndLanguage(String taskId, Long userId, String targetLanguage) {
        return Optional.ofNullable(mapper.selectByTaskIdUserIdAndTargetLanguage(taskId, userId, targetLanguage))
            .map(TaskFullTextResultQueryServiceImpl::toView);
    }

    private static TaskFullTextResultView toView(TaskFullTextResult entity) {
        return new TaskFullTextResultView(
            entity.getTaskId(),
            entity.getSourceLanguage(),
            entity.getTargetLanguage(),
            entity.getSourceFullText(),
            entity.getTranslatedFullText(),
            entity.getProvider(),
            entity.getCreatedAt(),
            entity.getUpdatedAt()
        );
    }
}
