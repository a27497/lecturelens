package com.example.courselingo.subtitle.service;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.subtitle.domain.SubtitleTranslationSegment;
import com.example.courselingo.subtitle.domain.TaskFullTextResult;
import com.example.courselingo.subtitle.mapper.SubtitleTranslationSegmentMapper;
import com.example.courselingo.subtitle.mapper.TaskFullTextResultMapper;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class SubtitleTranslationPersistenceService {

    private final SubtitleTranslationSegmentMapper translationMapper;
    private final TaskFullTextResultMapper fullTextResultMapper;

    SubtitleTranslationPersistenceService(
        SubtitleTranslationSegmentMapper translationMapper,
        TaskFullTextResultMapper fullTextResultMapper
    ) {
        this.translationMapper = translationMapper;
        this.fullTextResultMapper = fullTextResultMapper;
    }

    @Transactional
    int replaceSegmentTranslations(
        String taskId,
        Long userId,
        String targetLanguage,
        List<SubtitleTranslationSegment> translations
    ) {
        translationMapper.deleteByTaskIdUserIdAndTargetLanguage(taskId, userId, targetLanguage);
        insertTranslations(translations);
        return translations.size();
    }

    @Transactional
    void replaceDualOutput(
        String taskId,
        Long userId,
        String targetLanguage,
        List<SubtitleTranslationSegment> translations,
        TaskFullTextResult fullTextResult
    ) {
        if (fullTextResultMapper == null) {
            throw new BusinessException(ErrorCode.COMMON_INTERNAL_ERROR, "Full text persistence is not configured");
        }
        translationMapper.deleteByTaskIdUserIdAndTargetLanguage(taskId, userId, targetLanguage);
        fullTextResultMapper.deleteByTaskIdUserIdAndTargetLanguage(taskId, userId, targetLanguage);
        insertTranslations(translations);
        if (fullTextResultMapper.insert(fullTextResult) != 1) {
            throw new BusinessException(ErrorCode.COMMON_INTERNAL_ERROR, "Full text translation persistence failed");
        }
    }

    @Transactional
    int deleteTranslations(String taskId, Long userId, String targetLanguage) {
        return translationMapper.deleteByTaskIdUserIdAndTargetLanguage(taskId, userId, targetLanguage);
    }

    private void insertTranslations(List<SubtitleTranslationSegment> translations) {
        for (SubtitleTranslationSegment translation : translations) {
            if (translationMapper.insert(translation) != 1) {
                throw new BusinessException(ErrorCode.COMMON_INTERNAL_ERROR, "Subtitle translation persistence failed");
            }
        }
    }
}
