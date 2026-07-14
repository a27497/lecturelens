package com.example.courselingo.vision.keyframe;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.storage.StorageService;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.vision.analysis.VisionAnalysisProperties;
import com.example.courselingo.vision.analysis.mapper.VideoKeyframeAnalysisMapper;
import com.example.courselingo.vision.keyframe.mapper.VideoKeyframeMapper;
import com.example.courselingo.vision.ocr.VisionOcrProperties;
import com.example.courselingo.vision.ocr.mapper.VideoKeyframeOcrMapper;
import java.util.List;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class VideoKeyframeServiceImpl implements VideoKeyframeService {

    private final CurrentUserService currentUserService;
    private final AnalysisTaskMapper analysisTaskMapper;
    private final VideoKeyframeMapper videoKeyframeMapper;
    private final StorageService storageService;
    private final VideoKeyframeOcrMapper ocrMapper;
    private final VisionOcrProperties ocrProperties;
    private final VideoKeyframeAnalysisMapper analysisMapper;
    private final VisionAnalysisProperties analysisProperties;

    public VideoKeyframeServiceImpl(
        CurrentUserService currentUserService,
        AnalysisTaskMapper analysisTaskMapper,
        VideoKeyframeMapper videoKeyframeMapper,
        StorageService storageService
    ) {
        this(
            currentUserService,
            analysisTaskMapper,
            videoKeyframeMapper,
            storageService,
            null,
            null,
            null,
            null
        );
    }

    @Autowired
    public VideoKeyframeServiceImpl(
        CurrentUserService currentUserService,
        AnalysisTaskMapper analysisTaskMapper,
        VideoKeyframeMapper videoKeyframeMapper,
        StorageService storageService,
        VideoKeyframeOcrMapper ocrMapper,
        VisionOcrProperties ocrProperties,
        VideoKeyframeAnalysisMapper analysisMapper,
        VisionAnalysisProperties analysisProperties
    ) {
        this.currentUserService = currentUserService;
        this.analysisTaskMapper = analysisTaskMapper;
        this.videoKeyframeMapper = videoKeyframeMapper;
        this.storageService = storageService;
        this.ocrMapper = ocrMapper;
        this.ocrProperties = ocrProperties == null ? new VisionOcrProperties() : ocrProperties;
        this.analysisMapper = analysisMapper;
        this.analysisProperties = analysisProperties == null ? new VisionAnalysisProperties() : analysisProperties;
    }

    public VideoKeyframeServiceImpl(
        CurrentUserService currentUserService,
        AnalysisTaskMapper analysisTaskMapper,
        VideoKeyframeMapper videoKeyframeMapper,
        StorageService storageService,
        VideoKeyframeOcrMapper ocrMapper,
        VisionOcrProperties ocrProperties
    ) {
        this(
            currentUserService,
            analysisTaskMapper,
            videoKeyframeMapper,
            storageService,
            ocrMapper,
            ocrProperties,
            null,
            null
        );
    }

    @Override
    public List<VideoKeyframeView> listKeyframes(String authorizationHeader, String taskId) {
        CurrentUserResponse currentUser = currentUserService.currentUser(authorizationHeader);
        String normalizedTaskId = normalizeTaskId(taskId);
        ensureTaskOwner(normalizedTaskId, currentUser.userId());
        List<VideoKeyframe> keyframes = videoKeyframeMapper.selectByTaskIdAndUserId(normalizedTaskId, currentUser.userId());
        return VideoKeyframeViews.toViews(
            keyframes,
            ocrMapper == null ? List.of() : ocrMapper.selectByKeyframeIds(
                normalizedTaskId,
                currentUser.userId(),
                keyframes.stream().map(VideoKeyframe::getId).toList()
            ),
            ocrProperties.isEnabled(),
            analysisMapper == null ? List.of() : analysisMapper.selectByKeyframeIds(
                normalizedTaskId,
                currentUser.userId(),
                keyframes.stream().map(VideoKeyframe::getId).toList()
            ),
            analysisProperties.isEnabled()
        );
    }

    @Override
    public VideoKeyframeImage downloadKeyframeImage(String authorizationHeader, String taskId, Long frameId) {
        CurrentUserResponse currentUser = currentUserService.currentUser(authorizationHeader);
        String normalizedTaskId = normalizeTaskId(taskId);
        if (frameId == null || frameId <= 0) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, "Keyframe id is invalid");
        }
        ensureTaskOwner(normalizedTaskId, currentUser.userId());
        VideoKeyframe keyframe = videoKeyframeMapper.selectByIdAndTaskIdAndUserId(
            frameId,
            normalizedTaskId,
            currentUser.userId()
        );
        if (keyframe == null) {
            throw new BusinessException(ErrorCode.COMMON_NOT_FOUND);
        }
        return new VideoKeyframeImage(
            String.format("frame-%06d.jpg", keyframe.getFrameIndex() == null ? frameId : keyframe.getFrameIndex()),
            keyframe.getContentType() == null ? "image/jpeg" : keyframe.getContentType(),
            keyframe.getSizeBytes() == null ? 0L : keyframe.getSizeBytes(),
            storageService.openObject(keyframe.getObjectKey())
        );
    }

    private void ensureTaskOwner(String taskId, Long userId) {
        AnalysisTask task = analysisTaskMapper.selectByIdAndUserId(taskId, userId);
        if (task == null) {
            throw new BusinessException(ErrorCode.TASK_NOT_FOUND);
        }
    }

    private static String normalizeTaskId(String taskId) {
        if (taskId == null || taskId.isBlank()) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, "Task id is required");
        }
        return taskId.strip();
    }
}
