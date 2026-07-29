package com.example.courselingo.vision.keyframe;

import com.example.courselingo.common.logging.SafeLogSanitizer;
import com.example.courselingo.storage.StorageService;
import com.example.courselingo.vision.analysis.mapper.VideoKeyframeAnalysisMapper;
import com.example.courselingo.vision.keyframe.mapper.VideoKeyframeMapper;
import com.example.courselingo.vision.ocr.mapper.VideoKeyframeOcrMapper;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class VideoKeyframeEvidenceLifecycleServiceImpl implements VideoKeyframeEvidenceLifecycleService {

    private static final Logger LOGGER = LoggerFactory.getLogger(VideoKeyframeEvidenceLifecycleServiceImpl.class);

    private final VideoKeyframeMapper keyframeMapper;
    private final VideoKeyframeOcrMapper ocrMapper;
    private final VideoKeyframeAnalysisMapper analysisMapper;
    private final StorageService storageService;

    public VideoKeyframeEvidenceLifecycleServiceImpl(
        VideoKeyframeMapper keyframeMapper,
        VideoKeyframeOcrMapper ocrMapper,
        VideoKeyframeAnalysisMapper analysisMapper,
        StorageService storageService
    ) {
        this.keyframeMapper = keyframeMapper;
        this.ocrMapper = ocrMapper;
        this.analysisMapper = analysisMapper;
        this.storageService = storageService;
    }

    @Override
    public int cleanupTaskEvidence(String taskId, Long userId) {
        if (taskId == null || taskId.isBlank() || userId == null) {
            throw new IllegalArgumentException("task evidence scope is required");
        }
        String normalizedTaskId = taskId.strip();
        List<VideoKeyframe> rows = safeRows(keyframeMapper.selectExistingForTask(normalizedTaskId, userId));
        if (analysisMapper != null) {
            analysisMapper.deleteByTaskIdAndUserId(normalizedTaskId, userId);
        }
        if (ocrMapper != null) {
            ocrMapper.deleteByTaskIdAndUserId(normalizedTaskId, userId);
        }
        boolean objectCleanupFailed = false;
        for (VideoKeyframe row : rows) {
            objectCleanupFailed |= !deleteObject(normalizedTaskId, row == null ? null : row.getObjectKey());
        }
        if (objectCleanupFailed) {
            throw new IllegalStateException("Keyframe evidence object cleanup incomplete");
        }
        return keyframeMapper.deleteByTaskIdAndUserId(normalizedTaskId, userId);
    }

    private boolean deleteObject(String taskId, String objectKey) {
        if (objectKey == null || objectKey.isBlank()) {
            return true;
        }
        try {
            storageService.deleteObject(objectKey);
            return true;
        } catch (RuntimeException exception) {
            LOGGER.warn(
                "event=keyframe_evidence_object_cleanup_failed taskId={} errorType={}",
                SafeLogSanitizer.sanitize(taskId),
                exception.getClass().getSimpleName()
            );
            return false;
        }
    }

    private static List<VideoKeyframe> safeRows(List<VideoKeyframe> rows) {
        return rows == null ? List.of() : rows;
    }
}
