package com.example.courselingo.learning.service;

import com.example.courselingo.learning.dto.LearningPackageView;
import java.util.Optional;

public interface LearningPackageQueryService {

    Optional<LearningPackageView> getByTaskAndLanguage(String taskId, Long userId, String targetLanguage);

    long countByTaskIdAndLanguage(String taskId, Long userId, String targetLanguage);
}
