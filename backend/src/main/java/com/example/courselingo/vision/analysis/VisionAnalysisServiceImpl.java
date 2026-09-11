package com.example.courselingo.vision.analysis;

import com.example.courselingo.ai.record.domain.AiCallStage;
import com.example.courselingo.ai.record.domain.AiCallType;
import com.example.courselingo.ai.record.dto.AiCallRecordView;
import com.example.courselingo.ai.record.dto.CompleteAiCallRecordCommand;
import com.example.courselingo.ai.record.dto.FailAiCallRecordCommand;
import com.example.courselingo.ai.record.dto.StartAiCallRecordCommand;
import com.example.courselingo.ai.record.service.AiCallRecordService;
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
import com.example.courselingo.vision.ocr.OcrTextQualityEvaluator;
import com.example.courselingo.vision.ocr.mapper.VideoKeyframeOcrMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class VisionAnalysisServiceImpl implements VisionAnalysisService {

    private com.example.courselingo.task.service.GenerationFence generationFence;

    @Autowired
    public void configureGenerationFence(com.example.courselingo.task.service.GenerationFence fence) {
        this.generationFence = fence;
    }


    private static final Logger LOGGER = LoggerFactory.getLogger(VisionAnalysisServiceImpl.class);

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
    private final AiCallRecordService aiCallRecordService;
    private final TransactionTemplate persistenceTransaction;

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
        VisionPromptContextBuilder promptContextBuilder,
        AiCallRecordService aiCallRecordService,
        PlatformTransactionManager transactionManager
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
            promptContextBuilder,
            aiCallRecordService,
            transactionManager
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
        this(
            keyframeMapper, ocrMapper, analysisMapper, storageService, provider, aiModelRouter, selector,
            properties, objectMapper, clock, frameSampler, promptContextBuilder, null
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
        VisionPromptContextBuilder promptContextBuilder,
        AiCallRecordService aiCallRecordService
    ) {
        this(
            keyframeMapper, ocrMapper, analysisMapper, storageService, provider, aiModelRouter, selector,
            properties, objectMapper, clock, frameSampler, promptContextBuilder, aiCallRecordService, null
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
        VisionPromptContextBuilder promptContextBuilder,
        AiCallRecordService aiCallRecordService,
        PlatformTransactionManager transactionManager
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
        this.aiCallRecordService = aiCallRecordService;
        this.persistenceTransaction = persistenceTransaction(transactionManager);
    }

    @Override
    public VisionAnalysisScanResult scan(String taskId, Long userId) {
        return scanInternal(taskId, userId, null, null, "");
    }

    @Override
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
        AiCallRecordView call = startAiCall(normalizedTaskId, userId, selected.size(), route);
        long scanStartedNanos = System.nanoTime();
        int saved = 0;
        int succeeded = 0;
        int empty = 0;
        int failed = 0;
        int providerCalls = 0;
        long providerDurationMillis = 0L;
        List<VideoKeyframeAnalysis> analysisRows = new ArrayList<>(selected.size());
        try {
            for (VideoKeyframe keyframe : selected) {
                AnalysisOutcome outcome = analyze(
                    keyframe,
                    ocrRows,
                    route,
                    sourceVideo,
                    analysisWorkspace,
                    targetLanguage
                );
                VideoKeyframeAnalysis row = outcome.row();
                if (outcome.providerCalled()) providerCalls++;
                if (outcome.providerCalled() && row.getDurationMillis() != null) {
                    providerDurationMillis += Math.max(0L, row.getDurationMillis());
                }
                analysisRows.add(row);
                saved++;
                VisionAnalysisStatus status = VisionAnalysisStatus.valueOf(row.getStatus());
                switch (status) {
                    case SUCCEEDED -> succeeded++;
                    case EMPTY -> empty++;
                    case FAILED -> failed++;
                    default -> { }
                }
            }
            replaceAnalyses(normalizedTaskId, userId, analysisRows);
            int skipped = Math.max(0, keyframes.size() - selected.size());
            long wallDurationMillis = elapsedMillis(scanStartedNanos);
            completeAiCall(call, normalizedTaskId, userId, wallDurationMillis, providerDurationMillis,
                providerCalls, selected.size(), succeeded + empty);
            LOGGER.info(
                "event=adaptive_vlm_completed availableKeyframes={} vlmPlanned={} vlmAttempted={} vlmSucceeded={} vlmEmpty={} vlmFailed={} vlmSkipped={}",
                keyframes.size(), selected.size(), saved, succeeded, empty, failed, skipped
            );
            return new VisionAnalysisScanResult(saved, succeeded, empty, failed, skipped);
        } catch (RuntimeException exception) {
            failAiCall(call, normalizedTaskId, userId, elapsedMillis(scanStartedNanos), exception);
            throw exception;
        }
    }

    private AnalysisOutcome analyze(
        VideoKeyframe keyframe,
        Collection<VideoKeyframeOcr> ocrRows,
        AiModelRoute route,
        Path sourceVideo,
        Path analysisWorkspace,
        String targetLanguage
    ) {
        Path tempDirectory = null;
        boolean providerCalled = false;
        try {
            tempDirectory = analysisWorkspace == null
                ? Files.createTempDirectory("courselingo-vlm-")
                : Files.createDirectories(analysisWorkspace.resolve("vlm-" + keyframe.getId()).toAbsolutePath().normalize());
            Path imageFile = temporaryAnalysisImage(keyframe, sourceVideo, tempDirectory);
            String ocrText = ocrRows.stream()
                .filter(row -> keyframe.getId().equals(row.getKeyframeId()))
                .filter(row -> "SUCCEEDED".equals(row.getStatus()))
                .filter(row -> OcrTextQualityEvaluator.isUseful(
                    row.getOcrText(), row.getConfidence(), row.getLanguageHint(), ""
                ))
                .map(VideoKeyframeOcr::getOcrText)
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
            providerCalled = true;
            VisionAnalysisResult result = provider.analyze(new VisionAnalysisRequest(
                keyframe.getTaskId(),
                keyframe.getId(),
                keyframe.getTimestampMillis(),
                imageFile,
                ocrText,
                promptContext,
                route
            ));
            return new AnalysisOutcome(toRow(keyframe, result), true);
        } catch (Exception exception) {
            return new AnalysisOutcome(toRow(keyframe, VisionAnalysisResult.failed(
                provider.providerName(),
                route == null ? "" : route.modelName(),
                null,
                "VISION_FRAME_FAILED",
                SafeLogSanitizer.sanitizeAndLimit(exception.getMessage())
            )), providerCalled);
        } finally {
            deleteDirectoryBestEffort(tempDirectory);
        }
    }

    private void replaceAnalyses(String taskId, Long userId, List<VideoKeyframeAnalysis> rows) {
        Runnable persistence = () -> {
        if (generationFence != null) generationFence.sourceChanging(taskId, userId);
            analysisMapper.deleteByTaskIdAndUserId(taskId, userId);
            for (VideoKeyframeAnalysis row : rows) {
                if (analysisMapper.insert(row) != 1) {
                    throw new BusinessException(ErrorCode.COMMON_INTERNAL_ERROR, "Visual analysis persistence failed");
                }
            }
        };
        if (persistenceTransaction == null) {
            persistence.run();
            return;
        }
        persistenceTransaction.executeWithoutResult(status -> persistence.run());
    }

    private static TransactionTemplate persistenceTransaction(PlatformTransactionManager transactionManager) {
        if (transactionManager == null) {
            return null;
        }
        TransactionTemplate transaction = new TransactionTemplate(transactionManager);
        transaction.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
        return transaction;
    }

    private AiCallRecordView startAiCall(String taskId, Long userId, int inputUnits, AiModelRoute route) {
        if (aiCallRecordService == null) return null;
        return aiCallRecordService.startCall(new StartAiCallRecordCommand(
            taskId, userId, AiCallType.VLM, AiCallStage.VISION_ANALYSIS,
            nonBlank(provider.providerName(), "vision"), route == null ? "" : nonBlank(route.modelName(), ""),
            null, inputUnits
        ));
    }

    private void completeAiCall(
        AiCallRecordView call,
        String taskId,
        Long userId,
        long wallDurationMillis,
        long providerDurationMillis,
        int providerCalls,
        int inputUnits,
        int outputUnits
    ) {
        if (call == null || call.id() == null) return;
        aiCallRecordService.completeCall(new CompleteAiCallRecordCommand(
            call.id(), taskId, userId, wallDurationMillis, null, null, null,
            inputUnits, outputUnits, null, null, providerDurationMillis, providerCalls, 0
        ));
    }

    private void failAiCall(AiCallRecordView call, String taskId, Long userId, long durationMillis, RuntimeException ex) {
        if (call == null || call.id() == null) return;
        aiCallRecordService.failCall(new FailAiCallRecordCommand(
            call.id(), taskId, userId, durationMillis, "VISION_ANALYSIS_FAILED",
            SafeLogSanitizer.sanitizeAndLimit(ex.getMessage()), false, null, null
        ));
    }

    private static long elapsedMillis(long startedNanos) {
        return Math.max(1L, java.time.Duration.ofNanos(System.nanoTime() - startedNanos).toMillis());
    }

    private record AnalysisOutcome(VideoKeyframeAnalysis row, boolean providerCalled) {
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
