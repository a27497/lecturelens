package com.example.courselingo.subtitle.service;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.subtitle.dto.SubtitleSegmentView;
import com.example.courselingo.subtitle.mapper.SubtitleSegmentMapper;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class SubtitleSegmentQueryServiceImpl implements SubtitleSegmentQueryService {

    private static final int MAX_TASK_ID_LENGTH = 64;

    private final SubtitleSegmentMapper mapper;

    public SubtitleSegmentQueryServiceImpl(SubtitleSegmentMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public List<SubtitleSegmentView> listByTaskId(String taskId, Long userId) {
        validateTaskAndUser(taskId, userId);
        return mapper.selectByTaskIdAndUserId(taskId.strip(), userId)
            .stream()
            .map(SubtitleSegmentQueryServiceImpl::toView)
            .toList();
    }

    @Override
    public long countByTaskId(String taskId, Long userId) {
        validateTaskAndUser(taskId, userId);
        return mapper.countByTaskIdAndUserId(taskId.strip(), userId);
    }

    private static SubtitleSegmentView toView(SubtitleSegment segment) {
        return new SubtitleSegmentView(
            segment.getTaskId(),
            segment.getSegmentIndex(),
            segment.getStartMillis(),
            segment.getEndMillis(),
            segment.getLanguage(),
            segment.getText(),
            segment.getProvider(),
            segment.getCreatedAt(),
            segment.getUpdatedAt()
        );
    }

    private static void validateTaskAndUser(String taskId, Long userId) {
        if (taskId == null || taskId.isBlank() || taskId.strip().length() > MAX_TASK_ID_LENGTH) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, "Task ID is required");
        }
        if (userId == null || userId <= 0) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, "User ID is required");
        }
    }
}
