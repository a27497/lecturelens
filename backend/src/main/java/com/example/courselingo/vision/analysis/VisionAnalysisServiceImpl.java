package com.example.courselingo.vision.analysis;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.logging.SafeLogSanitizer;
import com.example.courselingo.modelrouting.AiModelRoute;
import com.example.courselingo.modelrouting.AiModelRouter;
import com.example.courselingo.modelrouting.AiModelStage;
import com.example.courselingo.media.VideoFrameSampler;
import com.example.courselingo.storage.StorageService;
import com.example.courselingo.vision.analysis.mapper.VideoKeyframeAnalysisMapper;
import com.example.courselingo.vision.keyframe.VideoKeyframe;
import com.example.courselingo.vision.keyframe.mapper.VideoKeyframeMapper;
import com.example.courselingo.vision.ocr.VideoKeyframeOcr;
import com.example.courselingo.vision.ocr.mapper.VideoKeyframeOcrMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.Collection;
import java.util.Comparator;
import java.util.List;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class VisionAnalysisServiceImpl implements VisionAnalysisService {

    private final VideoKeyframeMapper keyframeMapper;
    private final VideoKeyframeOcrMapper ocrMapper;
    private final VideoKeyframeAnalysisMapper analysisMapper;
    private final StorageService storageService;
    private final VisionModelProvider provider;
    private final AiModelRouter aiModelRouter;
    private final HighValueKeyframeSelector selector;
    private final VisionAnalysisProperties properties;
    private final ObjectMapper objectMapper;
    private final Clock clock;
    private final VideoFrameSampler frameSampler;
    private final VisionPromptContextBuilder promptContextBuilder;

    @Autowired
    public VisionAnalysisServiceImpl(
        VideoKeyframeMapper keyframeMapper,
        VideoKeyframeOcrMapper ocrMapper,
        VideoKeyframeAnalysisMapper analysisMapper,
        StorageService storageService,
        VisionModelProvider provider,
        AiModelRouter aiModelRouter,
        HighValueKeyframeSelector selector,
        VisionAnalysisProperties properties,
        VideoFrameSampler frameSampler,
        VisionPromptContextBuilder promptContextBuilder
    ) {
        this(
            keyframeMapper,
            ocrMapper,
            analysisMapper,
            storageService,
            provider,
            aiModelRouter,
            selector,
            properties,
            new ObjectMapper(),
            Clock.systemUTC(),
            frameSampler,
            promptContextBuilder
        );
    }

    VisionAnalysisServiceImpl(
        VideoKeyframeMapper keyframeMapper,
        VideoKeyframeOcrMapper ocrMapper,
        VideoKeyframeAnalysisMapper analysisMapper,
        StorageService storageService,
        VisionModelProvider provider,
        AiModelRouter aiModelRouter,
        HighValueKeyframeSelector selector,
        VisionAnalysisProperties properties,
        ObjectMapper objectMapper,
        Clock clock
    ) {
        this(
            keyframeMapper,
            ocrMapper,
            analysisMapper,
            storageService,
            provider,
            aiModelRouter,
            selector,
            properties,
            objectMapper,
            clock,
            null,
            null
        );
    }

    VisionAnalysisServiceImpl(
        VideoKeyframeMapper keyframeMapper,
        VideoKeyframeOcrMapper ocrMapper,
        VideoKeyframeAnalysisMapper analysisMapper,
        StorageService storageService,
        VisionModelProvider provider,
        AiModelRouter aiModelRouter,
        HighValueKeyframeSelector selector,
        VisionAnalysisProperties properties,
        ObjectMapper objectMapper,
        Clock clock,
        VideoFrameSampler frameSampler,
        VisionPromptContextBuilder promptContextBuilder
    ) {
        this.keyframeMapper = keyframeMapper;
        this.ocrMapper = ocrMapper;
        this.analysisMapper = analysisMapper;
        this.storageService = storageService;
        this.provider = provider == null ? new NoopVisionProvider() : provider;
        this.aiModelRouter = aiModelRouter;
        this.selector = selector == null ? new HighValueKeyframeSelector() : selector;
        this.properties = properties == null ? new VisionAnalysisProperties() : properties;
        this.objectMapper = objectMapper == null ? new ObjectMapper() : objectMapper;
        this.clock = clock == null ? Clock.systemUTC() : clock;
        this.frameSampler = frameSampler;
        this.promptContextBuilder = promptContextBuilder;
    }

    @Override
    @Transactional
    public VisionAnalysisScanResult scan(String taskId, Long userId) {
        return scanInternal(taskId, userId, null, null, "");
    }

    @Override
    @Transactional
    public VisionAnalysisScanResult scan(
        String taskId,
        Long userId,
        Path sourceVideo,
        Path analysisWorkspace,
        String targetLanguage
    ) {
        return scanInternal(taskId, userId, sourceVideo, analysisWorkspace, targetLanguage);
    }

    private VisionAnalysisScanResult scanInternal(
        String taskId,
        Long userId,
        Path sourceVideo,
        Path analysisWorkspace,
        String targetLanguage
    ) {
        if (!properties.isEnabled()) {
            return new VisionAnalysisScanResult(0, 0, 0, 0, 0);
        }
        String normalizedTaskId = normalizeTaskId(taskId);
        if (userId == null) {
            throw new IllegalArgumentException("userId is required");
        }
        List<VideoKeyframe> keyframes = keyframeMapper.selectByTaskIdAndUserId(normalizedTaskId, userId);
        List<VideoKeyframeOcr> ocrRows = ocrMapper == null
            ? List.of()
            : ocrMapper.selectByKeyframeIds(normalizedTaskId, userId, keyframes.stream().map(VideoKeyframe::getId).toList());
        List<VideoKeyframe> selected = selector.select(keyframes, ocrRows, properties);
        AiModelRoute route = aiModelRouter.route(AiModelStage.VISION_FRAME_ANALYSIS);
        analysisMapper.deleteByTaskIdAndUserId(normalizedTaskId, userId);
        int saved = 0;
        int succeeded = 0;
        int empty = 0;
        int failed = 0;
        for (VideoKeyframe keyframe : selected) {
            VideoKeyframeAnalysis row = analyze(
                keyframe,
                ocrRows,
                route,
                sourceVideo,
                analysisWorkspace,
                targetLanguage
            );
            if (analysisMapper.insert(row) != 1) {
                throw new BusinessException(ErrorCode.COMMON_INTERNAL_ERROR, "Visual analysis persistence failed");
            }
            saved++;
            VisionAnalysisStatus status = VisionAnalysisStatus.valueOf(row.getStatus());
            switch (status) {
                case SUCCEEDED -> succeeded++;
                case EMPTY -> empty++;
                case FAILED -> failed++;
                default -> {
                }
            }
        }
        int skipped = Math.max(0, keyframes.size() - selected.size());
        return new VisionAnalysisScanResult(saved, succeeded, empty, failed, skipped);
    }

    private VideoKeyframeAnalysis analyze(
        VideoKeyframe keyframe,
        Collection<VideoKeyframeOcr> ocrRows,
        AiModelRoute route,
        Path sourceVideo,
        Path analysisWorkspace,
        String targetLanguage
    ) {
        Path tempDirectory = null;
        try {
            tempDirectory = analysisWorkspace == null
                ? Files.createTempDirectory("courselingo-vlm-")
                : Files.createDirectories(analysisWorkspace.resolve("vlm-" + keyframe.getId()).toAbsolutePath().normalize());
            Path imageFile = temporaryAnalysisImage(keyframe, sourceVideo, tempDirectory);
            String ocrText = ocrRows.stream()
                .filter(row -> keyframe.getId().equals(row.getKeyframeId()))
                .map(VideoKeyframeOcr::getOcrText)
                .filter(text -> text != null && !text.isBlank())
                .findFirst()
                .orElse("");
            String promptContext = promptContextBuilder == null
                ? "Timestamp millis: " + keyframe.getTimestampMillis()
                : promptContextBuilder.build(
                    keyframe.getTaskId(),
                    keyframe.getUserId(),
                    keyframe.getTimestampMillis() == null ? 0L : keyframe.getTimestampMillis(),
                    targetLanguage
                );
            VisionAnalysisResult result = provider.analyze(new VisionAnalysisRequest(
                keyframe.getTaskId(),
                keyframe.getId(),
                keyframe.getTimestampMillis(),
                imageFile,
                ocrText,
                promptContext,
                route
            ));
            return toRow(keyframe, result);
        } catch (Exception exception) {
            return toRow(keyframe, VisionAnalysisResult.failed(
                provider.providerName(),
                route == null ? "" : route.modelName(),
                null,
                "VISION_FRAME_FAILED",
                SafeLogSanitizer.sanitizeAndLimit(exception.getMessage())
            ));
        } finally {
            deleteDirectoryBestEffort(tempDirectory);
        }
    }

    private Path temporaryAnalysisImage(VideoKeyframe keyframe, Path sourceVideo, Path tempDirectory) throws IOException {
        if (frameSampler != null && sourceVideo != null) {
            return frameSampler.sample(
                sourceVideo,
                keyframe.getTimestampMillis() == null ? 0L : keyframe.getTimestampMillis(),
                tempDirectory.resolve("analysis.png"),
                properties.getMaxImageWidth(),
                properties.getTimeout()
            );
        }
        Path imageFile = tempDirectory.resolve("frame.jpg");
        try (InputStream inputStream = storageService.openObject(keyframe.getObjectKey())) {
            Files.copy(inputStream, imageFile);
        }
        return imageFile;
    }

    private VideoKeyframeAnalysis toRow(VideoKeyframe keyframe, VisionAnalysisResult result) {
        LocalDateTime now = LocalDateTime.ofInstant(clock.instant(), clock.getZone());
        VideoKeyframeAnalysis row = new VideoKeyframeAnalysis();
        row.setTaskId(keyframe.getTaskId());
        row.setUserId(keyframe.getUserId());
        row.setKeyframeId(keyframe.getId());
        row.setTimestampMillis(keyframe.getTimestampMillis());
        row.setProvider(nonBlank(result.provider(), provider.providerName()));
        row.setModel(nonBlank(result.model(), ""));
        row.setScreenType(nonBlank(result.screenType(), ""));
        row.setVisualSummary(truncate(nonBlank(result.summary(), ""), 4000));
        row.setDetectedElementsJson(detectedElementsJson(result.detectedElements()));
        row.setStatus((result.status() == null ? VisionAnalysisStatus.FAILED : result.status()).name());
        row.setErrorCode(result.errorCode());
        row.setErrorMessage(SafeLogSanitizer.sanitizeAndLimit(result.errorMessage(), 512));
        row.setDurationMillis(result.durationMillis());
        row.setCreatedAt(now);
        row.setUpdatedAt(now);
        return row;
    }

    private String detectedElementsJson(List<String> elements) {
        try {
            return objectMapper.writeValueAsString(elements == null ? List.of() : elements);
        } catch (Exception ignored) {
            return "[]";
        }
    }

    private static String truncate(String value, int maxLength) {
        if (value == null || value.length() <= maxLength) {
            return value == null ? "" : value;
        }
        return value.substring(0, maxLength);
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
