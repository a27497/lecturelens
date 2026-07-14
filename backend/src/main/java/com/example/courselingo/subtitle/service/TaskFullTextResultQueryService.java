package com.example.courselingo.subtitle.service;

import com.example.courselingo.subtitle.dto.TaskFullTextResultView;
import java.util.Optional;

public interface TaskFullTextResultQueryService {

    Optional<TaskFullTextResultView> getByTaskAndLanguage(String taskId, Long userId, String targetLanguage);
}
