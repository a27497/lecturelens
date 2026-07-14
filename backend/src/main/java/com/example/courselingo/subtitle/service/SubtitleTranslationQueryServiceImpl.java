package com.example.courselingo.subtitle.service;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.subtitle.domain.SubtitleTranslationSegment;
import com.example.courselingo.subtitle.dto.SubtitleTranslationSegmentView;
import com.example.courselingo.subtitle.mapper.SubtitleTranslationSegmentMapper;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class SubtitleTranslationQueryServiceImpl implements SubtitleTranslationQueryService {

    private final SubtitleTranslationSegmentMapper mapper;

    public SubtitleTranslationQueryServiceImpl(SubtitleTranslationSegmentMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public List<SubtitleTranslationSegmentView> listTranslations(String taskId, Long userId, String targetLanguage) {
        ValidatedTranslationScope scope = SubtitleTranslationValidators.validateScope(taskId, userId, targetLanguage);
        return mapper.selectByTaskIdUserIdAndTargetLanguage(scope.taskId(), scope.userId(), scope.targetLanguage())
            .stream()
            .map(SubtitleTranslationQueryServiceImpl::toView)
            .toList();
    }

    @Override
    public long countByTaskIdAndLanguage(String taskId, Long userId, String targetLanguage) {
        ValidatedTranslationScope scope = SubtitleTranslationValidators.validateScope(taskId, userId, targetLanguage);
        return mapper.countByTaskIdAndLanguage(scope.taskId(), scope.userId(), scope.targetLanguage());
    }

    private static SubtitleTranslationSegmentView toView(SubtitleTranslationSegment segment) {
        if (segment.getTranslatedText() == null || segment.getTranslatedText().isBlank()) {
            throw new BusinessException(ErrorCode.COMMON_INTERNAL_ERROR, "Subtitle translation row is invalid");
        }
        return new SubtitleTranslationSegmentView(
            segment.getTaskId(),
            segment.getSegmentIndex(),
            segment.getStartMillis(),
            segment.getEndMillis(),
            segment.getSourceLanguage(),
            segment.getTargetLanguage(),
            segment.getTranslatedText(),
            segment.getProvider(),
            segment.getCreatedAt(),
            segment.getUpdatedAt()
        );
    }
}
