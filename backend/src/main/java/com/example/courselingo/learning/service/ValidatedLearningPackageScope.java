package com.example.courselingo.learning.service;

record ValidatedLearningPackageScope(
    String taskId,
    Long userId,
    String targetLanguage
) {
}
