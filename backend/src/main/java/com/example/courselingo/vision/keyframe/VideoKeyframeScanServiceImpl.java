package com.example.courselingo.vision.keyframe;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.logging.SafeLogSanitizer;
import com.example.courselingo.media.SceneDetectionPoint;
import com.example.courselingo.media.SingleFrameVideoFrameBatchSampler;
import com.example.courselingo.media.VideoFrameBatchSampler;
import com.example.courselingo.media.VideoFrameSampler;
import com.example.courselingo.media.VideoMetadata;
import com.example.courselingo.media.VideoMetadataProbe;
import com.example.courselingo.media.VideoSceneScanner;
import com.example.courselingo.storage.StorageService;
import com.example.courselingo.vision.adaptive.CandidateTimestampPlanner;
import com.example.courselingo.vision.adaptive.AdaptiveFramePreparationPipeline;
import com.example.courselingo.vision.adaptive.ImageQualityAnalysis;
import com.example.courselingo.vision.adaptive.OcrTextDeduplicator;
import com.example.courselingo.vision.adaptive.PerceptualHashDeduplicator;
import com.example.courselingo.vision.adaptive.SceneCandidate;
import com.example.courselingo.vision.adaptive.ContentAdaptiveFrameBudgetAllocator;
import com.example.courselingo.vision.adaptive.VideoContentClassifier;
import com.example.courselingo.vision.adaptive.VideoContentType;
import com.example.courselingo.vision.keyframe.mapper.VideoKeyframeMapper;
import com.example.courselingo.vision.ocr.OcrProvider;
import com.example.courselingo.vision.ocr.OcrResult;
import com.example.courselingo.vision.ocr.OcrStatus;
import com.example.courselingo.vision.ocr.VideoKeyframeOcr;
import com.example.courselingo.vision.ocr.VisionOcrProperties;
import com.example.courselingo.vision.ocr.mapper.VideoKeyframeOcrMapper;
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import javax.imageio.ImageIO;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class VideoKeyframeScanServiceImpl implements VideoKeyframeScanService {

    private static final Logger LOGGER = LoggerFactory.getLogger(VideoKeyframeScanServiceImpl.class);
    private static final String STORAGE_BACKEND = "MINIO";
    private static final String CONTENT_TYPE = "image/jpeg";

    private final VideoKeyframeMapper mapper;
    private final StorageService storageService;
    private final VideoKeyframeProperties properties;
    private final VideoMetadataProbe metadataProbe;
    private final VideoSceneScanner sceneScanner;
    private final VideoFrameBatchSampler frameBatchSampler;
    private final OcrProvider ocrProvider;
    private final VideoKeyframeOcrMapper ocrMapper;
    private final VisionOcrProperties ocrProperties;
    private final Clock clock;
    private final VideoKeyframeEvidenceLifecycleService evidenceLifecycleService;
    private final EvidenceImageWriter evidenceImageWriter = new EvidenceImageWriter();

    @Autowired
    public VideoKeyframeScanServiceImpl(
        VideoKeyframeMapper mapper,
        StorageService storageService,
        VideoKeyframeProperties properties,
        VideoMetadataProbe metadataProbe,
        VideoSceneScanner sceneScanner,
        VideoFrameSampler frameSampler,
        VideoFrameBatchSampler frameBatchSampler,
        OcrProvider ocrProvider,
        VideoKeyframeOcrMapper ocrMapper,
        VisionOcrProperties ocrProperties,
        VideoKeyframeEvidenceLifecycleService evidenceLifecycleService
    ) {
        this(
            mapper,
            storageService,
            properties,
            metadataProbe,
            sceneScanner,
            frameSampler,
            frameBatchSampler,
            ocrProvider,
            ocrMapper,
            ocrProperties,
            evidenceLifecycleService,
            Clock.systemUTC()
        );
    }

    VideoKeyframeScanServiceImpl(
        VideoKeyframeMapper mapper,
        StorageService storageService,
        VideoKeyframeProperties properties,
        VideoMetadataProbe metadataProbe,
        VideoSceneScanner sceneScanner,
        VideoFrameSampler frameSampler,
        OcrProvider ocrProvider,
        VideoKeyframeOcrMapper ocrMapper,
        VisionOcrProperties ocrProperties,
        Clock clock
    ) {
        this(
            mapper,
            storageService,
            properties,
            metadataProbe,
            sceneScanner,
            frameSampler,
            new SingleFrameVideoFrameBatchSampler(frameSampler),
            ocrProvider,
            ocrMapper,
            ocrProperties,
            null,
            clock
        );
    }

    VideoKeyframeScanServiceImpl(
        VideoKeyframeMapper mapper,
        StorageService storageService,
        VideoKeyframeProperties properties,
        VideoMetadataProbe metadataProbe,
        VideoSceneScanner sceneScanner,
        VideoFrameSampler frameSampler,
        OcrProvider ocrProvider,
        VideoKeyframeOcrMapper ocrMapper,
        VisionOcrProperties ocrProperties,
        VideoKeyframeEvidenceLifecycleService evidenceLifecycleService,
        Clock clock
    ) {
        this(
            mapper,
            storageService,
            properties,
            metadataProbe,
            sceneScanner,
            frameSampler,
            new SingleFrameVideoFrameBatchSampler(frameSampler),
            ocrProvider,
            ocrMapper,
            ocrProperties,
            evidenceLifecycleService,
            clock
        );
    }

    VideoKeyframeScanServiceImpl(
        VideoKeyframeMapper mapper,
        StorageService storageService,
        VideoKeyframeProperties properties,
        VideoMetadataProbe metadataProbe,
        VideoSceneScanner sceneScanner,
        VideoFrameSampler frameSampler,
        VideoFrameBatchSampler frameBatchSampler,
        OcrProvider ocrProvider,
        VideoKeyframeOcrMapper ocrMapper,
        VisionOcrProperties ocrProperties,
        VideoKeyframeEvidenceLifecycleService evidenceLifecycleService,
        Clock clock
    ) {
        this.mapper = mapper;
        this.storageService = storageService;
        this.properties = properties == null ? new VideoKeyframeProperties() : properties;
        this.metadataProbe = metadataProbe;
        this.sceneScanner = sceneScanner;
        this.frameBatchSampler = frameBatchSampler;
        this.ocrProvider = ocrProvider;
        this.ocrMapper = ocrMapper;
        this.ocrProperties = ocrProperties == null ? new VisionOcrProperties() : ocrProperties;
        this.evidenceLifecycleService = evidenceLifecycleService;
        this.clock = clock == null ? Clock.systemUTC() : clock;
    }

    @Override
    public VideoKeyframeScanResult scan(VideoKeyframeScanCommand command) {
        if (!properties.isEnabled()) {
            return new VideoKeyframeScanResult(0);
        }
        validate(command);
        requireAdaptiveDependencies();
        long startedNanos = System.nanoTime();
        Path outputDirectory = normalizedOutputDirectory(command.outputDirectory());
        MutableStats stats = new MutableStats();
        try {
            removeExisting(command.taskId(), command.userId());
            VideoMetadata metadata = metadataProbe.probe(
                command.sourceVideo(),
                Duration.ofSeconds(Math.min(60L, properties.getTimeoutSeconds()))
            );
            if (!metadata.hasVideoStream() || metadata.durationMillis() <= 0L) {
                throw new BusinessException(ErrorCode.MEDIA_INPUT_INVALID, "Uploaded source has no usable video stream");
            }
            List<SceneDetectionPoint> scenePoints = sceneScanner.scan(
                command.sourceVideo(),
                outputDirectory,
                properties.getDetectionWidth(),
                properties.getContentChangeThreshold(),
                Duration.ofSeconds(properties.getTimeoutSeconds())
            );
            CandidateTimestampPlanner planner = planner();
            List<SceneCandidate> planned = planner.plan(
                metadata.durationMillis() / 1000.0d,
                scenePoints.stream()
                    .map(point -> point.score() >= properties.getSceneChangeThreshold()
                        ? SceneCandidate.sceneChange(point.timestampMillis() / 1000.0d, point.score())
                        : SceneCandidate.contentChange(point.timestampMillis() / 1000.0d, point.score()))
                    .toList()
            );
            stats.candidates = planned.size();
            List<SceneCandidate> bounded = boundedCandidates(planned, metadata.durationMillis());
            AdaptiveFramePreparationPipeline.Result preparation = new AdaptiveFramePreparationPipeline(
                properties,
                frameBatchSampler,
                ocrProvider,
                ocrProperties
            ).prepare(command.sourceVideo(), outputDirectory, metadata.durationMillis(), bounded);
            stats.merge(preparation.statistics());
            List<PreparedFrame> prepared = preparation.frames().stream().map(frame -> new PreparedFrame(
                frame.candidate(),
                frame.timestampMillis(),
                frame.imagePath(),
                frame.quality(),
                frame.relaxed(),
                frame.ocr()
            )).toList();
            List<PreparedFrame> deduplicated = deduplicate(prepared, stats);
            List<PreparedFrame> selected = applyContentAdaptiveBudget(deduplicated);

            int frameIndex = 0;
            for (PreparedFrame frame : selected) {
                save(command, frameIndex++, frame, outputDirectory, stats);
            }
            long durationMillis = Duration.ofNanos(System.nanoTime() - startedNanos).toMillis();
            LOGGER.info(
                "event=adaptive_vision_completed plannedCandidates={} sampleBatches={} ffmpegProcessCount={} sampleRequests={} sampleSucceeded={} sampleFailed={} stableFrames={} blurredRejected={} blackRejected={} duplicateRejected={} preOcrRejected={} ocrPlanned={} ocrAttempted={} ocrSucceeded={} ocrEmpty={} ocrFailed={} finalKeyframes={} vlmPlanned={} durationMillis={} cleanup=scheduled",
                stats.candidates,
                stats.sampleBatches,
                stats.ffmpegProcessCount,
                stats.sampleRequests,
                stats.samples,
                stats.sampleFailed,
                stats.stableFrames,
                stats.blurredRejected,
                stats.blackRejected,
                stats.duplicateRejected,
                stats.preOcrRejected,
                stats.ocrPlanned,
                stats.ocrAttempted,
                stats.ocrSucceeded,
                stats.ocrEmpty,
                stats.ocrFailed,
                selected.size(),
                selected.size(),
                durationMillis
            );
            return stats.result(selected.size(), durationMillis);
        } catch (RuntimeException failure) {
            try {
                removeExisting(command.taskId(), command.userId());
            } catch (RuntimeException cleanupFailure) {
                failure.addSuppressed(cleanupFailure);
            }
            throw failure;
        } finally {
            boolean cleaned = deleteDirectoryBestEffort(outputDirectory);
            LOGGER.info("event=adaptive_vision_workspace_cleanup success={}", cleaned);
        }
    }

    private List<PreparedFrame> deduplicate(List<PreparedFrame> prepared, MutableStats stats) {
        if (prepared.isEmpty()) {
            return List.of();
        }
        OcrTextDeduplicator textDeduplicator = new OcrTextDeduplicator(new OcrTextDeduplicator.Config(
            properties.getPerceptualHashDistance(),
            0.92d,
            120.0d,
            4
        ));
        List<PreparedFrame> kept = new ArrayList<>();
        for (PreparedFrame candidate : prepared) {
            boolean duplicate = kept.stream().anyMatch(previous -> duplicate(previous, candidate, textDeduplicator));
            if (duplicate) {
                stats.duplicateRejected++;
                deleteFileBestEffort(candidate.imagePath());
            } else {
                kept.add(candidate);
            }
        }
        return List.copyOf(kept);
    }

    private boolean duplicate(
        PreparedFrame previous,
        PreparedFrame candidate,
        OcrTextDeduplicator textDeduplicator
    ) {
        long windowMillis = properties.getWindowSeconds() * 1_000L;
        int hashDistance = PerceptualHashDeduplicator.hammingDistance(
            previous.quality().perceptualHash(),
            candidate.quality().perceptualHash()
        );
        if (!previous.quality().contentFingerprint().isBlank()
            && previous.quality().contentFingerprint().equals(candidate.quality().contentFingerprint())
            && Math.abs(previous.timestampMillis() - candidate.timestampMillis()) <= 120_000L
        ) {
            if (filesIdentical(previous.imagePath(), candidate.imagePath())) {
                return true;
            }
            boolean detectedChange = candidate.candidate().source() == SceneCandidate.Source.SCENE_CHANGE
                || candidate.candidate().source() == SceneCandidate.Source.CONTENT_CHANGE;
            if (detectedChange
                && Math.abs(previous.timestampMillis() - candidate.timestampMillis())
                    >= properties.getMinKeyframeGapSeconds() * 1_000L) {
                return false;
            }
            return true;
        }
        if (previous.timestampMillis() / windowMillis != candidate.timestampMillis() / windowMillis) {
            return false;
        }
        if (hashDistance > properties.getPerceptualHashDistance()) {
            return false;
        }
        String previousText = previous.ocr().text();
        String candidateText = candidate.ocr().text();
        if (previousText == null || previousText.isBlank() || candidateText == null || candidateText.isBlank()) {
            if (candidate.candidate().source() == SceneCandidate.Source.SCENE_CHANGE
                || candidate.candidate().source() == SceneCandidate.Source.CONTENT_CHANGE) {
                return false;
            }
            return true;
        }
        VideoContentClassifier classifier = contentClassifier();
        boolean codeLike = classifier.classify(
            previousText,
            previous.quality().edgeDensity(),
            previous.candidate().score(),
            null
        ) == VideoContentType.CODE_OR_TERMINAL || classifier.classify(
            candidateText,
            candidate.quality().edgeDensity(),
            candidate.candidate().score(),
            null
        ) == VideoContentType.CODE_OR_TERMINAL;
        if (codeLike && VideoContentClassifier.textChangeRatio(previousText, candidateText)
            >= properties.getCodeOcrChangeThreshold()) {
            return false;
        }
        return textDeduplicator.isDuplicate(
            previousText,
            previous.quality().perceptualHash(),
            previous.timestampMillis() / 1000.0d,
            candidateText,
            candidate.quality().perceptualHash(),
            candidate.timestampMillis() / 1000.0d
        );
    }

    private List<PreparedFrame> applyContentAdaptiveBudget(List<PreparedFrame> frames) {
        VideoContentClassifier classifier = contentClassifier();
        int globalWindowLimit = properties.getMaxKeyframesPerMinute();
        ContentAdaptiveFrameBudgetAllocator allocator = new ContentAdaptiveFrameBudgetAllocator(
            new ContentAdaptiveFrameBudgetAllocator.Config(
                properties.getWindowSeconds(),
                Math.min(globalWindowLimit, properties.getSlideMaxFramesPerMinute()),
                Math.min(globalWindowLimit, properties.getCodeOrTerminalMaxFramesPerMinute()),
                Math.min(globalWindowLimit, properties.getVisualDemoMaxFramesPerMinute()),
                Math.min(globalWindowLimit, properties.getTalkingOrLowInformationMaxFramesPerMinute()),
                Math.min(globalWindowLimit, properties.getUnknownMaxFramesPerMinute()),
                properties.getMaxKeyframesTotal()
            )
        );
        List<ContentAdaptiveFrameBudgetAllocator.FrameSignal<PreparedFrame>> signals = frames.stream()
            .map(frame -> {
                VideoContentType contentType = classifier.classify(
                    frame.ocr().text(),
                    frame.quality().edgeDensity(),
                    frame.candidate().score(),
                    null
                );
                return new ContentAdaptiveFrameBudgetAllocator.FrameSignal<>(
                    frame,
                    frame.timestampMillis(),
                    contentType,
                    framePriority(frame, contentType)
                );
            })
            .toList();
        List<PreparedFrame> selected = allocator.select(signals);
        java.util.Set<Path> selectedPaths = selected.stream()
            .map(PreparedFrame::imagePath)
            .collect(java.util.stream.Collectors.toSet());
        frames.stream()
            .filter(frame -> !selectedPaths.contains(frame.imagePath()))
            .forEach(frame -> deleteFileBestEffort(frame.imagePath()));
        return selected;
    }

    private double framePriority(PreparedFrame frame, VideoContentType contentType) {
        double sourcePriority = switch (frame.candidate().source()) {
            case SCENE_CHANGE -> 30.0d;
            case CONTENT_CHANGE -> 27.0d;
            case START, END -> 24.0d;
            case PERIODIC_ANCHOR -> 18.0d;
            case WINDOW_COVERAGE -> 15.0d;
        };
        double contentBonus = switch (contentType) {
            case VISUAL_DEMO -> 8.0d;
            case CODE_OR_TERMINAL -> 6.0d;
            case SLIDE -> 4.0d;
            case UNKNOWN -> 1.0d;
            case TALKING_OR_LOW_INFORMATION -> 0.0d;
        };
        return sourcePriority + contentBonus + frame.quality().totalScore()
            + Math.max(0.0d, frame.candidate().score()) * 10.0d;
    }

    private VideoContentClassifier contentClassifier() {
        return new VideoContentClassifier(new VideoContentClassifier.Config(
            properties.getContentSlideMinimumTextCharacters(),
            properties.getContentLowInformationMaximumTextCharacters(),
            properties.getContentCodeSymbolRatioThreshold(),
            properties.getContentVisualEdgeDensityThreshold(),
            properties.getContentVisualSceneScoreThreshold()
        ));
    }

    private void save(
        VideoKeyframeScanCommand command,
        int frameIndex,
        PreparedFrame prepared,
        Path outputDirectory,
        MutableStats stats
    ) {
        Path evidence = outputDirectory.resolve("evidence-%06d.jpg".formatted(frameIndex));
        String objectKey = VideoKeyframeObjectKeyGenerator.generate(command.userId(), command.taskId(), frameIndex);
        try {
            BufferedImage source = ImageIO.read(prepared.imagePath().toFile());
            if (source == null) {
                throw new IOException("Selected analysis frame is unreadable");
            }
            evidenceImageWriter.write(source, evidence, properties.getEvidenceMaxWidth());
            long sizeBytes = Files.size(evidence);
            storageService.putObject(objectKey, evidence, sizeBytes, CONTENT_TYPE);
            VideoKeyframe row = toEntity(command, frameIndex, prepared, objectKey, sizeBytes);
            if (mapper.insert(row) != 1) {
                throw new BusinessException(ErrorCode.COMMON_INTERNAL_ERROR, "Keyframe persistence failed");
            }
            if (ocrMapper != null && ocrMapper.insert(toOcrRow(row, prepared.ocr())) != 1) {
                throw new BusinessException(ErrorCode.COMMON_INTERNAL_ERROR, "Keyframe OCR persistence failed");
            }
            deleteFileBestEffort(evidence);
            deleteFileBestEffort(prepared.imagePath());
        } catch (IOException exception) {
            throw new BusinessException(ErrorCode.STORAGE_SOURCE_FILE_INVALID, "Evidence image is invalid", exception);
        } catch (RuntimeException exception) {
            try {
                storageService.deleteObject(objectKey);
            } catch (RuntimeException ignored) {
                // Retry-safe best effort after a partial database/storage failure.
            }
            throw exception;
        }
    }

    private VideoKeyframe toEntity(
        VideoKeyframeScanCommand command,
        int frameIndex,
        PreparedFrame prepared,
        String objectKey,
        long sizeBytes
    ) {
        LocalDateTime now = LocalDateTime.ofInstant(clock.instant(), clock.getZone());
        VideoKeyframe keyframe = new VideoKeyframe();
        keyframe.setTaskId(command.taskId());
        keyframe.setUserId(command.userId());
        keyframe.setFrameIndex(frameIndex);
        keyframe.setTimestampMillis(prepared.timestampMillis());
        keyframe.setTimeText(formatTime(prepared.timestampMillis()));
        keyframe.setChangeScore(prepared.candidate().score());
        keyframe.setSelectReason(selectionReason(prepared.candidate()).name());
        keyframe.setContentType(CONTENT_TYPE);
        keyframe.setStorageBackend(STORAGE_BACKEND);
        keyframe.setObjectKey(objectKey);
        keyframe.setSizeBytes(sizeBytes);
        keyframe.setQualityScore(prepared.quality().totalScore());
        keyframe.setSharpnessScore(prepared.quality().laplacianVariance());
        keyframe.setBrightnessMean(prepared.quality().meanBrightness());
        keyframe.setBrightnessVariance(prepared.quality().brightnessVariance());
        keyframe.setEdgeDensity(prepared.quality().edgeDensity());
        keyframe.setPerceptualHash(Long.toUnsignedString(prepared.quality().perceptualHash(), 16));
        keyframe.setDegraded(prepared.relaxed());
        keyframe.setSourceType(prepared.candidate().source().name());
        keyframe.setCreatedAt(now);
        keyframe.setUpdatedAt(now);
        return keyframe;
    }

    private VideoKeyframeOcr toOcrRow(VideoKeyframe keyframe, OcrResult result) {
        LocalDateTime now = LocalDateTime.ofInstant(clock.instant(), clock.getZone());
        String originalText = result.text() == null ? "" : result.text().strip();
        String text = originalText.length() <= ocrProperties.getMaxTextLength()
            ? originalText
            : originalText.substring(0, ocrProperties.getMaxTextLength());
        VideoKeyframeOcr row = new VideoKeyframeOcr();
        row.setTaskId(keyframe.getTaskId());
        row.setUserId(keyframe.getUserId());
        row.setKeyframeId(keyframe.getId());
        row.setTimestampMillis(keyframe.getTimestampMillis());
        row.setProvider(result.provider());
        row.setLanguageHint(result.languageHint());
        row.setOcrText(text);
        row.setTextLength(originalText.length());
        row.setTextTruncated(originalText.length() > text.length());
        row.setConfidence(result.confidence());
        row.setStatus((result.status() == null ? OcrStatus.FAILED : result.status()).name());
        row.setErrorCode(result.errorCode());
        row.setErrorMessage(SafeLogSanitizer.sanitizeAndLimit(result.errorMessage(), 512));
        row.setDurationMillis(result.durationMillis());
        row.setCreatedAt(now);
        row.setUpdatedAt(now);
        return row;
    }

    private List<SceneCandidate> boundedCandidates(List<SceneCandidate> candidates, long durationMillis) {
        if (candidates.isEmpty()) {
            return List.of();
        }
        int limit = Math.min(properties.maxSourceFramesTotal(), candidates.size());
        long windowMillis = properties.getWindowSeconds() * 1000L;
        Map<Long, List<SceneCandidate>> byWindow = new LinkedHashMap<>();
        candidates.stream()
            .sorted(Comparator.comparingDouble(SceneCandidate::timestampSeconds))
            .forEach(candidate -> byWindow.computeIfAbsent(
                (long) Math.floor(candidate.timestampSeconds() * 1000.0d / windowMillis),
                ignored -> new ArrayList<>()
            ).add(candidate));
        byWindow.values().forEach(values -> values.sort(candidatePriority()));

        List<SceneCandidate> selected = new ArrayList<>();
        int round = 0;
        while (selected.size() < limit) {
            int currentRound = round;
            List<List<SceneCandidate>> eligible = byWindow.values().stream()
                .filter(values -> values.size() > currentRound)
                .toList();
            if (eligible.isEmpty()) {
                break;
            }
            int slots = Math.min(limit - selected.size(), eligible.size());
            if (slots == eligible.size()) {
                for (List<SceneCandidate> values : eligible) {
                    selected.add(values.get(round));
                }
            } else if (slots == 1) {
                selected.add(eligible.get(eligible.size() / 2).get(round));
            } else {
                for (int index = 0; index < slots; index++) {
                    int position = (int) Math.round(index * (eligible.size() - 1.0d) / (slots - 1.0d));
                    selected.add(eligible.get(position).get(round));
                }
            }
            round++;
        }
        return selected.stream().sorted(Comparator.comparingDouble(SceneCandidate::timestampSeconds)).toList();
    }

    private static Comparator<SceneCandidate> candidatePriority() {
        return Comparator.comparingInt((SceneCandidate candidate) -> switch (candidate.source()) {
            case SCENE_CHANGE -> 5;
            case CONTENT_CHANGE, START, END -> 4;
            case PERIODIC_ANCHOR -> 3;
            case WINDOW_COVERAGE -> 2;
        }).reversed().thenComparing(Comparator.comparingDouble(SceneCandidate::score).reversed());
    }

    private CandidateTimestampPlanner planner() {
        return new CandidateTimestampPlanner(new CandidateTimestampPlanner.Config(
            properties.getWindowSeconds(),
            properties.getMaxCandidatesPerWindow(),
            Math.max(0.5d, properties.getMinKeyframeGapSeconds() / 2.0d),
            properties.getMediumVideoThresholdMinutes() * 60.0d,
            properties.getLongVideoThresholdMinutes() * 60.0d,
            properties.getShortVideoAnchorSeconds(),
            properties.getMediumVideoAnchorSeconds(),
            properties.getLongVideoAnchorSeconds()
        ));
    }

    private void removeExisting(String taskId, Long userId) {
        if (evidenceLifecycleService != null) {
            evidenceLifecycleService.cleanupTaskEvidence(taskId, userId);
            return;
        }
        List<VideoKeyframe> oldKeyframes = mapper.selectExistingForTask(taskId, userId);
        mapper.deleteByTaskIdAndUserId(taskId, userId);
        for (VideoKeyframe keyframe : oldKeyframes) {
            if (keyframe.getObjectKey() == null) {
                continue;
            }
            try {
                storageService.deleteObject(keyframe.getObjectKey());
            } catch (RuntimeException exception) {
                LOGGER.warn(
                    "event=keyframe_evidence_object_cleanup_failed taskId={} errorType={}",
                    SafeLogSanitizer.sanitize(taskId),
                    exception.getClass().getSimpleName()
                );
            }
        }
    }

    private void requireAdaptiveDependencies() {
        if (mapper == null || storageService == null || metadataProbe == null || sceneScanner == null
            || frameBatchSampler == null) {
            throw new BusinessException(ErrorCode.MEDIA_CONFIGURATION_INVALID, "Adaptive video components are unavailable");
        }
    }

    private static Path normalizedOutputDirectory(Path outputDirectory) {
        Path output = outputDirectory.toAbsolutePath().normalize();
        try {
            Files.createDirectories(output);
            return output;
        } catch (IOException exception) {
            throw new BusinessException(ErrorCode.MEDIA_OUTPUT_INVALID, "Keyframe workspace is unavailable", exception);
        }
    }

    private static void validate(VideoKeyframeScanCommand command) {
        if (command == null
            || command.taskId() == null
            || command.taskId().isBlank()
            || command.userId() == null
            || command.sourceVideo() == null
            || command.outputDirectory() == null) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED);
        }
    }

    private static KeyframeSelectionReason selectionReason(SceneCandidate candidate) {
        return switch (candidate.source()) {
            case START -> KeyframeSelectionReason.FIRST_FRAME;
            case SCENE_CHANGE -> KeyframeSelectionReason.SCENE_CHANGE;
            case CONTENT_CHANGE -> KeyframeSelectionReason.CONTENT_CHANGE;
            case END, PERIODIC_ANCHOR, WINDOW_COVERAGE -> KeyframeSelectionReason.PERIODIC_ANCHOR;
        };
    }

    private static String formatTime(long timestampMillis) {
        long millis = Math.max(0L, timestampMillis);
        long hours = millis / 3_600_000L;
        long minutes = (millis % 3_600_000L) / 60_000L;
        long seconds = (millis % 60_000L) / 1_000L;
        long restMillis = millis % 1_000L;
        return hours > 0
            ? String.format(Locale.ROOT, "%02d:%02d:%02d.%03d", hours, minutes, seconds, restMillis)
            : String.format(Locale.ROOT, "%02d:%02d.%03d", minutes, seconds, restMillis);
    }

    private static void ensureNotInterrupted() {
        if (Thread.currentThread().isInterrupted()) {
            throw new BusinessException(ErrorCode.MEDIA_FFMPEG_FAILED, "Adaptive video branch was interrupted");
        }
    }

    private static boolean deleteDirectoryBestEffort(Path directory) {
        if (directory == null || !Files.exists(directory)) {
            return true;
        }
        boolean[] success = {true};
        try (var paths = Files.walk(directory)) {
            paths.sorted(Comparator.reverseOrder()).forEach(path -> {
                try {
                    Files.deleteIfExists(path);
                } catch (IOException ignored) {
                    success[0] = false;
                }
            });
        } catch (IOException ignored) {
            return false;
        }
        return success[0];
    }

    private static void deleteFileBestEffort(Path path) {
        if (path == null) {
            return;
        }
        try {
            Files.deleteIfExists(path);
        } catch (IOException ignored) {
            // The guarded task-workspace cleanup provides a final retry.
        }
    }

    private static boolean filesIdentical(Path first, Path second) {
        try {
            return first != null && second != null
                && Files.size(first) == Files.size(second)
                && Files.mismatch(first, second) == -1L;
        } catch (IOException ignored) {
            return false;
        }
    }

    private record PreparedFrame(
        SceneCandidate candidate,
        long timestampMillis,
        Path imagePath,
        ImageQualityAnalysis quality,
        boolean relaxed,
        OcrResult ocr
    ) {
    }

    private static final class MutableStats {
        private int candidates;
        private int samples;
        private int sampleBatches;
        private int ffmpegProcessCount;
        private int sampleRequests;
        private int sampleFailed;
        private int stableFrames;
        private int blurredRejected;
        private int blackRejected;
        private int duplicateRejected;
        private int preOcrRejected;
        private int ocrPlanned;
        private int ocrAttempted;
        private int ocrSucceeded;
        private int ocrEmpty;
        private int ocrFailed;

        private void merge(AdaptiveFramePreparationPipeline.Statistics source) {
            sampleBatches += source.sampleBatches();
            ffmpegProcessCount += source.ffmpegProcessCount();
            sampleRequests += source.sampleRequests();
            samples += source.sampleSucceeded();
            sampleFailed += source.sampleFailed();
            stableFrames += source.stableFrames();
            blurredRejected += source.blurredRejected();
            blackRejected += source.blackRejected();
            duplicateRejected += source.imageDuplicateRejected();
            preOcrRejected += source.preOcrRejected();
            ocrPlanned += source.ocrPlanned();
            ocrAttempted += source.ocrAttempted();
            ocrSucceeded += source.ocrSucceeded();
            ocrEmpty += source.ocrEmpty();
            ocrFailed += source.ocrFailed();
        }

        private VideoKeyframeScanResult result(int saved, long durationMillis) {
            return new VideoKeyframeScanResult(
                saved,
                candidates,
                samples,
                blurredRejected,
                blackRejected,
                duplicateRejected,
                ocrSucceeded,
                ocrEmpty,
                ocrFailed,
                durationMillis,
                sampleBatches,
                ffmpegProcessCount,
                sampleRequests,
                samples,
                sampleFailed,
                stableFrames,
                preOcrRejected,
                ocrPlanned,
                ocrAttempted,
                saved,
                saved
            );
        }
    }
}
