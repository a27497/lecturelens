package com.example.courselingo.vision.ocr;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.logging.SafeLogSanitizer;
import com.example.courselingo.storage.StorageService;
import com.example.courselingo.vision.keyframe.VideoKeyframe;
import com.example.courselingo.vision.keyframe.mapper.VideoKeyframeMapper;
import com.example.courselingo.vision.ocr.mapper.VideoKeyframeOcrMapper;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.Comparator;
import java.util.List;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class VideoKeyframeOcrScanServiceImpl implements VideoKeyframeOcrScanService {

    private com.example.courselingo.task.service.GenerationFence generationFence;

    @Autowired
    public void configureGenerationFence(com.example.courselingo.task.service.GenerationFence fence) {
        this.generationFence = fence;
    }


    private final VideoKeyframeMapper keyframeMapper;
    private final VideoKeyframeOcrMapper ocrMapper;
    private final StorageService storageService;
    private final OcrProvider ocrProvider;
    private final VisionOcrProperties properties;
    private final Clock clock;

    @Autowired
    public VideoKeyframeOcrScanServiceImpl(
        VideoKeyframeMapper keyframeMapper,
        VideoKeyframeOcrMapper ocrMapper,
        StorageService storageService,
        OcrProvider ocrProvider,
        VisionOcrProperties properties
    ) {
        this(keyframeMapper, ocrMapper, storageService, ocrProvider, properties, Clock.systemUTC());
    }

    VideoKeyframeOcrScanServiceImpl(
        VideoKeyframeMapper keyframeMapper,
        VideoKeyframeOcrMapper ocrMapper,
        StorageService storageService,
        OcrProvider ocrProvider,
        VisionOcrProperties properties,
        Clock clock
    ) {
        this.keyframeMapper = keyframeMapper;
        this.ocrMapper = ocrMapper;
        this.storageService = storageService;
        this.ocrProvider = ocrProvider;
        this.properties = properties == null ? new VisionOcrProperties() : properties;
        this.clock = clock == null ? Clock.systemUTC() : clock;
    }

    @Override
    @Transactional(propagation = org.springframework.transaction.annotation.Propagation.NOT_SUPPORTED)
    public VideoKeyframeOcrScanResult scan(String taskId, Long userId) {
        if (!properties.isEnabled()) {
            return new VideoKeyframeOcrScanResult(0, 0, 0, 0, 0);
        }
        String normalizedTaskId = normalizeTaskId(taskId);
        if (userId == null) {
            throw new IllegalArgumentException("userId is required");
        }
        var ticket = generationFence == null ? null : generationFence.begin(normalizedTaskId, userId, "ocr");
        List<VideoKeyframe> keyframes = keyframeMapper.selectByTaskIdAndUserId(normalizedTaskId, userId);
        List<VideoKeyframeOcr> existing = ocrMapper.selectByKeyframeIds(
            normalizedTaskId,
            userId,
            keyframes.stream().map(VideoKeyframe::getId).toList()
        );
        if (!keyframes.isEmpty() && existing.size() == keyframes.size()) {
            return summarize(existing);
        }
        var rows = new java.util.ArrayList<VideoKeyframeOcr>();
        int succeeded = 0;
        int empty = 0;
        int failed = 0;
        int skipped = 0;
        int saved = 0;
        int limit = properties.getMaxKeyframesPerTask();
        for (int index = 0; index < keyframes.size(); index++) {
            VideoKeyframe keyframe = keyframes.get(index);
            VideoKeyframeOcr row = index >= limit
                ? skippedRow(keyframe)
                : recognize(keyframe);
            rows.add(row);
            saved++;
            OcrStatus status = OcrStatus.valueOf(row.getStatus());
            switch (status) {
                case SUCCEEDED -> succeeded++;
                case EMPTY -> empty++;
                case FAILED -> failed++;
                case SKIPPED -> skipped++;
                default -> {
                }
            }
        }
        java.util.function.Supplier<Void> persist = () -> {
            if (generationFence != null) generationFence.sourceChanging(normalizedTaskId, userId);
            ocrMapper.deleteByTaskIdAndUserId(normalizedTaskId, userId);
            for (VideoKeyframeOcr row : rows) {
                if (ocrMapper.insert(row) != 1) throw new BusinessException(ErrorCode.COMMON_INTERNAL_ERROR,
                    "Keyframe OCR persistence failed");
            }
            return null;
        };
        if (ticket == null) persist.get(); else generationFence.commit(ticket, persist);
        return new VideoKeyframeOcrScanResult(saved, succeeded, empty, failed, skipped);
    }

    private static VideoKeyframeOcrScanResult summarize(List<VideoKeyframeOcr> rows) {
        int succeeded = 0;
        int empty = 0;
        int failed = 0;
        int skipped = 0;
        for (VideoKeyframeOcr row : rows) {
            OcrStatus status;
            try {
                status = OcrStatus.valueOf(row.getStatus());
            } catch (RuntimeException exception) {
                status = OcrStatus.FAILED;
            }
            switch (status) {
                case SUCCEEDED -> succeeded++;
                case EMPTY -> empty++;
                case FAILED -> failed++;
                case SKIPPED -> skipped++;
                default -> {
                }
            }
        }
        return new VideoKeyframeOcrScanResult(rows.size(), succeeded, empty, failed, skipped);
    }

    private VideoKeyframeOcr recognize(VideoKeyframe keyframe) {
        Path tempDirectory = null;
        try {
            tempDirectory = Files.createTempDirectory("courselingo-ocr-");
            Path imageFile = tempDirectory.resolve("frame.jpg");
            try (InputStream inputStream = storageService.openObject(keyframe.getObjectKey())) {
                Files.copy(inputStream, imageFile);
            }
            return toRow(keyframe, ocrProvider.recognize(new OcrRequest(imageFile)));
        } catch (Exception exception) {
            return toRow(keyframe, new OcrResult(
                OcrStatus.FAILED,
                "",
                null,
                properties.getProvider(),
                properties.getLanguage(),
                null,
                "OCR_FRAME_FAILED",
                SafeLogSanitizer.sanitizeAndLimit(exception.getMessage())
            ));
        } finally {
            deleteDirectoryBestEffort(tempDirectory);
        }
    }

    private VideoKeyframeOcr skippedRow(VideoKeyframe keyframe) {
        return toRow(keyframe, new OcrResult(
            OcrStatus.SKIPPED,
            "",
            null,
            properties.getProvider(),
            properties.getLanguage(),
            null,
            null,
            null
        ));
    }

    private VideoKeyframeOcr toRow(VideoKeyframe keyframe, OcrResult result) {
        LocalDateTime now = LocalDateTime.ofInstant(clock.instant(), clock.getZone());
        String originalText = result.text() == null ? "" : result.text().strip();
        OcrStatus status = result.status() == null ? OcrStatus.FAILED : result.status();
        boolean usefulText = status == OcrStatus.SUCCEEDED
            && OcrTextQualityEvaluator.isUseful(
                originalText,
                result.confidence(),
                result.languageHint(),
                ""
            );
        String safeText = truncate(originalText, properties.getMaxTextLength());
        OcrStatus persistedStatus = status == OcrStatus.SUCCEEDED && !usefulText ? OcrStatus.EMPTY : status;
        VideoKeyframeOcr row = new VideoKeyframeOcr();
        row.setTaskId(keyframe.getTaskId());
        row.setUserId(keyframe.getUserId());
        row.setKeyframeId(keyframe.getId());
        row.setTimestampMillis(keyframe.getTimestampMillis());
        row.setProvider(nonBlank(result.provider(), properties.getProvider()));
        row.setLanguageHint(nonBlank(result.languageHint(), properties.getLanguage()));
        row.setOcrText(safeText);
        row.setTextLength(originalText.length());
        row.setTextTruncated(safeText.length() < originalText.length());
        row.setConfidence(result.confidence());
        row.setStatus(persistedStatus.name());
        row.setErrorCode(result.errorCode());
        row.setErrorMessage(SafeLogSanitizer.sanitizeAndLimit(result.errorMessage()));
        row.setDurationMillis(result.durationMillis());
        row.setCreatedAt(now);
        row.setUpdatedAt(now);
        return row;
    }

    private static String truncate(String text, int maxLength) {
        if (text == null || text.length() <= maxLength) {
            return text == null ? "" : text;
        }
        return text.substring(0, maxLength).stripTrailing();
    }

    private static String nonBlank(String value, String fallback) {
        return value == null || value.isBlank() ? fallback : value.strip();
    }

    private static String normalizeTaskId(String taskId) {
        if (taskId == null || taskId.isBlank()) {
            throw new IllegalArgumentException("taskId is required");
        }
        return taskId.strip();
    }

    private static void deleteDirectoryBestEffort(Path directory) {
        if (directory == null || !Files.exists(directory)) {
            return;
        }
        try (var paths = Files.walk(directory)) {
            paths.sorted(Comparator.reverseOrder()).forEach(path -> {
                try {
                    Files.deleteIfExists(path);
                } catch (IOException ignored) {
                    // Best-effort temporary file cleanup.
                }
            });
        } catch (IOException ignored) {
            // Best-effort temporary file cleanup.
        }
    }
}
