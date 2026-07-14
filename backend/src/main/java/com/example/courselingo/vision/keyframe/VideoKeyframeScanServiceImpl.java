package com.example.courselingo.vision.keyframe;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.media.ExtractedVideoFrame;
import com.example.courselingo.media.VideoFrameExtractionRequest;
import com.example.courselingo.media.VideoFrameExtractor;
import com.example.courselingo.storage.StorageService;
import com.example.courselingo.vision.keyframe.mapper.VideoKeyframeMapper;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class VideoKeyframeScanServiceImpl implements VideoKeyframeScanService {

    private static final String STORAGE_BACKEND = "MINIO";
    private static final String CONTENT_TYPE = "image/jpeg";

    private final VideoFrameExtractor frameExtractor;
    private final FrameDifferenceCalculator differenceCalculator;
    private final KeyframeSelectionService selectionService;
    private final VideoKeyframeMapper mapper;
    private final StorageService storageService;
    private final VideoKeyframeProperties properties;
    private final Clock clock;

    @Autowired
    public VideoKeyframeScanServiceImpl(
        VideoFrameExtractor frameExtractor,
        FrameDifferenceCalculator differenceCalculator,
        KeyframeSelectionService selectionService,
        VideoKeyframeMapper mapper,
        StorageService storageService,
        VideoKeyframeProperties properties
    ) {
        this(frameExtractor, differenceCalculator, selectionService, mapper, storageService, properties,
            Clock.systemUTC());
    }

    VideoKeyframeScanServiceImpl(
        VideoFrameExtractor frameExtractor,
        FrameDifferenceCalculator differenceCalculator,
        KeyframeSelectionService selectionService,
        VideoKeyframeMapper mapper,
        StorageService storageService,
        VideoKeyframeProperties properties,
        Clock clock
    ) {
        this.frameExtractor = frameExtractor;
        this.differenceCalculator = differenceCalculator;
        this.selectionService = selectionService;
        this.mapper = mapper;
        this.storageService = storageService;
        this.properties = properties == null ? new VideoKeyframeProperties() : properties;
        this.clock = clock == null ? Clock.systemUTC() : clock;
    }

    @Override
    @Transactional
    public VideoKeyframeScanResult scan(VideoKeyframeScanCommand command) {
        if (!properties.isEnabled()) {
            return new VideoKeyframeScanResult(0);
        }
        validate(command);
        Path outputDirectory = command.outputDirectory().toAbsolutePath().normalize();
        try {
            Files.createDirectories(outputDirectory);
        } catch (IOException ex) {
            throw new BusinessException(ErrorCode.MEDIA_OUTPUT_INVALID, "Keyframe workspace is not available", ex);
        }
        try {
            removeExisting(command.taskId(), command.userId());
            List<ExtractedVideoFrame> frames = frameExtractor.extract(new VideoFrameExtractionRequest(
                command.sourceVideo(),
                outputDirectory,
                properties.getScanIntervalSeconds(),
                properties.getThumbnailWidth(),
                properties.getOutputFormat(),
                properties.maxSourceFramesTotal(),
                Duration.ofSeconds(properties.getTimeoutSeconds())
            ));
            List<KeyframeCandidate> candidates = toCandidates(frames);
            List<SelectedKeyframe> selected = selectionService.select(candidates, properties);
            for (SelectedKeyframe keyframe : selected) {
                save(command, keyframe);
            }
            return new VideoKeyframeScanResult(selected.size());
        } finally {
            deleteDirectoryBestEffort(outputDirectory);
        }
    }

    private List<KeyframeCandidate> toCandidates(List<ExtractedVideoFrame> frames) {
        if (frames == null || frames.isEmpty()) {
            return List.of();
        }
        List<KeyframeCandidate> candidates = new ArrayList<>();
        Path previous = null;
        for (ExtractedVideoFrame frame : frames) {
            FrameChangeScore score = previous == null
                ? FrameChangeScore.none()
                : differenceCalculator.score(previous, frame.imageFile(), properties.getPixelDiffThreshold());
            candidates.add(new KeyframeCandidate(frame.frameIndex(), frame.timestampMillis(), frame.imageFile(), score));
            previous = frame.imageFile();
        }
        return candidates;
    }

    private void save(VideoKeyframeScanCommand command, SelectedKeyframe selected) {
        Path imageFile = selected.imageFile();
        try {
            long sizeBytes = Files.size(imageFile);
            String objectKey = VideoKeyframeObjectKeyGenerator.generate(
                command.userId(),
                command.taskId(),
                selected.frameIndex()
            );
            storageService.putObject(objectKey, imageFile, sizeBytes, CONTENT_TYPE);
            mapper.insert(toEntity(command, selected, objectKey, sizeBytes));
        } catch (IOException ex) {
            throw new BusinessException(ErrorCode.STORAGE_SOURCE_FILE_INVALID, "Keyframe thumbnail is invalid", ex);
        }
    }

    private VideoKeyframe toEntity(
        VideoKeyframeScanCommand command,
        SelectedKeyframe selected,
        String objectKey,
        long sizeBytes
    ) {
        LocalDateTime now = LocalDateTime.ofInstant(clock.instant(), clock.getZone());
        VideoKeyframe keyframe = new VideoKeyframe();
        keyframe.setTaskId(command.taskId());
        keyframe.setUserId(command.userId());
        keyframe.setFrameIndex(selected.frameIndex());
        keyframe.setTimestampMillis(selected.timestampMillis());
        keyframe.setTimeText(formatTime(selected.timestampMillis()));
        keyframe.setChangeScore(selected.changeScore());
        keyframe.setSelectReason(selected.reason().name());
        keyframe.setContentType(CONTENT_TYPE);
        keyframe.setStorageBackend(STORAGE_BACKEND);
        keyframe.setObjectKey(objectKey);
        keyframe.setSizeBytes(sizeBytes);
        keyframe.setCreatedAt(now);
        keyframe.setUpdatedAt(now);
        return keyframe;
    }

    private void removeExisting(String taskId, Long userId) {
        List<VideoKeyframe> oldKeyframes = mapper.selectExistingForTask(taskId, userId);
        mapper.deleteByTaskIdAndUserId(taskId, userId);
        for (VideoKeyframe keyframe : oldKeyframes) {
            if (keyframe.getObjectKey() != null) {
                try {
                    storageService.deleteObject(keyframe.getObjectKey());
                } catch (RuntimeException ignored) {
                    // Best-effort cleanup; a DB retry must still stay idempotent.
                }
            }
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

    private static String formatTime(long timestampMillis) {
        long millis = Math.max(0L, timestampMillis);
        long hours = millis / 3_600_000L;
        long minutes = (millis % 3_600_000L) / 60_000L;
        long seconds = (millis % 60_000L) / 1_000L;
        long restMillis = millis % 1_000L;
        if (hours > 0) {
            return String.format("%02d:%02d:%02d.%03d", hours, minutes, seconds, restMillis);
        }
        return String.format("%02d:%02d.%03d", minutes, seconds, restMillis);
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
