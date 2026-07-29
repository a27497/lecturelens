package com.example.courselingo.vision.keyframe;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.example.courselingo.media.SceneDetectionPoint;
import com.example.courselingo.media.VideoFrameSampler;
import com.example.courselingo.media.VideoMetadata;
import com.example.courselingo.storage.StorageService;
import com.example.courselingo.vision.keyframe.mapper.VideoKeyframeMapper;
import com.example.courselingo.vision.ocr.OcrProvider;
import com.example.courselingo.vision.ocr.OcrResult;
import com.example.courselingo.vision.ocr.OcrStatus;
import com.example.courselingo.vision.ocr.VideoKeyframeOcr;
import com.example.courselingo.vision.ocr.VisionOcrProperties;
import com.example.courselingo.vision.ocr.mapper.VideoKeyframeOcrMapper;
import java.awt.Color;
import java.awt.image.BufferedImage;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Clock;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import javax.imageio.ImageIO;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class AdaptiveVideoKeyframeScanServiceTest {

    @TempDir
    private Path tempDir;

    @Test
    void ocrUsesTemporaryHighResolutionPngAndOnlyEvidenceImagesArePersisted() throws Exception {
        Path source = Files.writeString(tempDir.resolve("course.mp4"), "fake");
        Path workspace = tempDir.resolve("work");
        VideoKeyframeMapper keyframeMapper = mock(VideoKeyframeMapper.class);
        VideoKeyframeOcrMapper ocrMapper = mock(VideoKeyframeOcrMapper.class);
        when(keyframeMapper.selectExistingForTask("task_1", 42L)).thenReturn(List.of());
        AtomicLong ids = new AtomicLong(1L);
        org.mockito.Mockito.doAnswer(invocation -> {
            invocation.getArgument(0, VideoKeyframe.class).setId(ids.getAndIncrement());
            return 1;
        }).when(keyframeMapper).insert(any(VideoKeyframe.class));
        when(ocrMapper.insert(any(VideoKeyframeOcr.class))).thenReturn(1);
        List<BufferedImage> persisted = new ArrayList<>();
        StorageService storage = storageCapturing(persisted);
        VisionOcrProperties ocrProperties = new VisionOcrProperties();
        ocrProperties.setEnabled(true);
        List<Integer> ocrWidths = new ArrayList<>();
        OcrProvider ocr = request -> {
            try {
                BufferedImage image = ImageIO.read(request.imageFile().toFile());
                ocrWidths.add(image.getWidth());
                return new OcrResult(
                    OcrStatus.SUCCEEDED,
                    "frame text " + ocrWidths.size(),
                    0.95d,
                    "fake",
                    "chi_sim+eng",
                    1L,
                    null,
                    null
                );
            } catch (Exception exception) {
                throw new IllegalStateException(exception);
            }
        };
        VideoKeyframeProperties properties = properties();
        VideoKeyframeScanServiceImpl service = new VideoKeyframeScanServiceImpl(
            keyframeMapper,
            storage,
            properties,
            (path, timeout) -> new VideoMetadata(125_000L, 1920, 1080, 30.0d, "h264", true, 0),
            (path, dir, width, threshold, timeout) -> List.of(new SceneDetectionPoint(61_000L, 0.8d)),
            colorfulSampler(),
            ocr,
            ocrMapper,
            ocrProperties,
            (Clock) null
        );

        VideoKeyframeScanResult result = service.scan(new VideoKeyframeScanCommand(
            "task_1", 42L, source, workspace
        ));

        assertThat(result.savedKeyframeCount()).isPositive();
        assertThat(result.candidateTimestampCount()).isPositive();
        assertThat(result.extractedSampleCount()).isGreaterThan(result.savedKeyframeCount());
        assertThat(ocrWidths).allMatch(width -> width > 320);
        assertThat(persisted).isNotEmpty().allMatch(image -> image.getWidth() <= 960);
        assertThat(Files.exists(workspace)).isFalse();
        org.mockito.Mockito.verify(ocrMapper, org.mockito.Mockito.times(result.savedKeyframeCount()))
            .insert(any(VideoKeyframeOcr.class));
    }

    @Test
    void blackFramesAreRejectedAndWorkspaceIsCleaned() throws Exception {
        Path source = Files.writeString(tempDir.resolve("black.mp4"), "fake");
        Path workspace = tempDir.resolve("black-work");
        VideoKeyframeMapper keyframeMapper = mock(VideoKeyframeMapper.class);
        when(keyframeMapper.selectExistingForTask("task_2", 42L)).thenReturn(List.of());
        VideoKeyframeScanServiceImpl service = new VideoKeyframeScanServiceImpl(
            keyframeMapper,
            storageCapturing(new ArrayList<>()),
            properties(),
            (path, timeout) -> new VideoMetadata(30_000L, 1920, 1080, 30.0d, "h264", true, 0),
            (path, dir, width, threshold, timeout) -> List.of(),
            solidSampler(Color.BLACK),
            null,
            null,
            new VisionOcrProperties(),
            (Clock) null
        );

        VideoKeyframeScanResult result = service.scan(new VideoKeyframeScanCommand(
            "task_2", 42L, source, workspace
        ));

        assertThat(result.savedKeyframeCount()).isZero();
        assertThat(result.blackRejectedCount()).isPositive();
        assertThat(Files.exists(workspace)).isFalse();
    }

    @Test
    void probeFailureStillCleansTaskWorkspace() throws Exception {
        Path source = Files.writeString(tempDir.resolve("broken.mp4"), "fake");
        Path workspace = tempDir.resolve("broken-work");
        VideoKeyframeScanServiceImpl service = new VideoKeyframeScanServiceImpl(
            mock(VideoKeyframeMapper.class),
            storageCapturing(new ArrayList<>()),
            properties(),
            (path, timeout) -> {
                throw new IllegalStateException("probe failed");
            },
            (path, dir, width, threshold, timeout) -> List.of(),
            colorfulSampler(),
            null,
            null,
            new VisionOcrProperties(),
            (Clock) null
        );

        assertThatThrownBy(() -> service.scan(new VideoKeyframeScanCommand(
            "task_3", 42L, source, workspace
        ))).isInstanceOf(IllegalStateException.class);
        assertThat(Files.exists(workspace)).isFalse();
    }

    @Test
    void identicalStaticFramesInDifferentTimelineWindowsPreserveCoverage() throws Exception {
        Path source = Files.writeString(tempDir.resolve("static-course.mp4"), "fake");
        Path workspace = tempDir.resolve("static-work");
        VideoKeyframeMapper keyframeMapper = mock(VideoKeyframeMapper.class);
        when(keyframeMapper.selectExistingForTask("task_4", 42L)).thenReturn(List.of());
        org.mockito.Mockito.doAnswer(invocation -> {
            invocation.getArgument(0, VideoKeyframe.class).setId(1L);
            return 1;
        }).when(keyframeMapper).insert(any(VideoKeyframe.class));
        VideoKeyframeScanServiceImpl service = new VideoKeyframeScanServiceImpl(
            keyframeMapper,
            storageCapturing(new ArrayList<>()),
            properties(),
            (path, timeout) -> new VideoMetadata(125_000L, 1280, 720, 12.0d, "h264", true, 0),
            (path, dir, width, threshold, timeout) -> List.of(),
            staticPatternSampler(),
            null,
            null,
            new VisionOcrProperties(),
            (Clock) null
        );

        VideoKeyframeScanResult result = service.scan(new VideoKeyframeScanCommand(
            "task_4", 42L, source, workspace
        ));

        assertThat(result.savedKeyframeCount()).isGreaterThanOrEqualTo(2);
        assertThat(Files.exists(workspace)).isFalse();
    }

    @Test
    void detectedContentChangesAreNotDroppedByHashOnlyWhenOcrIsUnavailable() throws Exception {
        Path source = Files.writeString(tempDir.resolve("content-changes.mp4"), "fake");
        Path workspace = tempDir.resolve("content-change-work");
        VideoKeyframeMapper keyframeMapper = mock(VideoKeyframeMapper.class);
        when(keyframeMapper.selectExistingForTask("task_changes", 42L)).thenReturn(List.of());
        AtomicLong ids = new AtomicLong(1L);
        org.mockito.Mockito.doAnswer(invocation -> {
            invocation.getArgument(0, VideoKeyframe.class).setId(ids.getAndIncrement());
            return 1;
        }).when(keyframeMapper).insert(any(VideoKeyframe.class));
        VideoKeyframeProperties properties = properties();
        properties.setUnknownMaxFramesPerMinute(4);
        properties.setSlideMaxFramesPerMinute(4);
        properties.setVisualDemoMaxFramesPerMinute(4);
        VideoKeyframeScanServiceImpl service = new VideoKeyframeScanServiceImpl(
            keyframeMapper,
            storageCapturing(new ArrayList<>()),
            properties,
            (path, timeout) -> new VideoMetadata(59_000L, 1280, 720, 12.0d, "h264", true, 0),
            (path, dir, width, threshold, timeout) -> List.of(
                new SceneDetectionPoint(10_000L, 0.8d),
                new SceneDetectionPoint(20_000L, 0.05d)
            ),
            staticPatternSampler(),
            null,
            null,
            new VisionOcrProperties(),
            (Clock) null
        );

        VideoKeyframeScanResult result = service.scan(new VideoKeyframeScanCommand(
            "task_changes", 42L, source, workspace
        ));

        assertThat(result.savedKeyframeCount()).isGreaterThanOrEqualTo(2);
        assertThat(workspace).doesNotExist();
    }

    @Test
    void progressiveCodeContentKeepsEachDetectedChangeWithinBudget() throws Exception {
        Path source = Files.writeString(tempDir.resolve("progressive-code.mp4"), "fake");
        Path workspace = tempDir.resolve("progressive-code-work");
        VideoKeyframeMapper keyframeMapper = mock(VideoKeyframeMapper.class);
        when(keyframeMapper.selectExistingForTask("task_code", 42L)).thenReturn(List.of());
        AtomicLong ids = new AtomicLong(1L);
        List<Long> persistedTimestamps = new ArrayList<>();
        org.mockito.Mockito.doAnswer(invocation -> {
            VideoKeyframe keyframe = invocation.getArgument(0, VideoKeyframe.class);
            keyframe.setId(ids.getAndIncrement());
            persistedTimestamps.add(keyframe.getTimestampMillis());
            return 1;
        }).when(keyframeMapper).insert(any(VideoKeyframe.class));
        VideoKeyframeOcrMapper ocrMapper = mock(VideoKeyframeOcrMapper.class);
        when(ocrMapper.insert(any(VideoKeyframeOcr.class))).thenReturn(1);
        VisionOcrProperties ocrProperties = new VisionOcrProperties();
        ocrProperties.setEnabled(true);
        AtomicInteger ocrCall = new AtomicInteger();
        OcrProvider ocr = request -> {
            int line = ocrCall.incrementAndGet();
            return new OcrResult(
                OcrStatus.SUCCEEDED,
                "public class Pipeline { static void step" + line + "() { return; } }",
                0.95d,
                "fake",
                "chi_sim+eng",
                1L,
                null,
                null
            );
        };
        VideoKeyframeProperties properties = properties();
        properties.setMaxKeyframesTotal(4);
        properties.setCodeOrTerminalMaxFramesPerMinute(4);
        VideoKeyframeScanServiceImpl service = new VideoKeyframeScanServiceImpl(
            keyframeMapper,
            storageCapturing(new ArrayList<>()),
            properties,
            (path, timeout) -> new VideoMetadata(59_000L, 1280, 720, 12.0d, "h264", true, 0),
            (path, dir, width, threshold, timeout) -> List.of(
                new SceneDetectionPoint(22_000L, 0.08d),
                new SceneDetectionPoint(34_000L, 0.09d),
                new SceneDetectionPoint(46_000L, 0.10d)
            ),
            colorfulSampler(),
            ocr,
            ocrMapper,
            ocrProperties,
            (Clock) null
        );

        VideoKeyframeScanResult result = service.scan(new VideoKeyframeScanCommand(
            "task_code", 42L, source, workspace
        ));

        assertThat(result.savedKeyframeCount()).isEqualTo(4);
        assertThat(persistedTimestamps).anyMatch(timestamp -> timestamp >= 22_000L && timestamp < 34_000L);
        assertThat(persistedTimestamps).anyMatch(timestamp -> timestamp >= 34_000L && timestamp < 46_000L);
        assertThat(persistedTimestamps).anyMatch(timestamp -> timestamp >= 46_000L && timestamp < 59_000L);
        assertThat(workspace).doesNotExist();
    }

    @Test
    void databaseInsertFailureDeletesUploadedObjectAndCleansCurrentRoundEvidence() throws Exception {
        Path source = Files.writeString(tempDir.resolve("insert-failure.mp4"), "fake");
        Path workspace = tempDir.resolve("insert-failure-work");
        VideoKeyframeMapper keyframeMapper = mock(VideoKeyframeMapper.class);
        when(keyframeMapper.insert(any(VideoKeyframe.class))).thenReturn(0);
        VideoKeyframeEvidenceLifecycleService lifecycle = mock(VideoKeyframeEvidenceLifecycleService.class);
        AtomicBoolean uploadedObjectDeleted = new AtomicBoolean(false);
        StorageService storage = new StorageService() {
            @Override
            public void putObject(String objectKey, Path sourceFile, long sizeBytes, String contentType) {
            }

            @Override
            public boolean objectExists(String objectKey) {
                return false;
            }

            @Override
            public InputStream openObject(String objectKey) {
                throw new UnsupportedOperationException();
            }

            @Override
            public void deleteObject(String objectKey) {
                uploadedObjectDeleted.set(true);
            }
        };
        VideoKeyframeScanServiceImpl service = new VideoKeyframeScanServiceImpl(
            keyframeMapper,
            storage,
            properties(),
            (path, timeout) -> new VideoMetadata(30_000L, 1280, 720, 12.0d, "h264", true, 0),
            (path, dir, width, threshold, timeout) -> List.of(),
            colorfulSampler(),
            null,
            null,
            new VisionOcrProperties(),
            lifecycle,
            Clock.systemUTC()
        );

        assertThatThrownBy(() -> service.scan(new VideoKeyframeScanCommand(
            "task_insert_failure", 42L, source, workspace
        )))
            .isInstanceOf(com.example.courselingo.common.exception.BusinessException.class)
            .hasMessage("Keyframe persistence failed");

        assertThat(uploadedObjectDeleted).isTrue();
        org.mockito.Mockito.verify(lifecycle, org.mockito.Mockito.times(2))
            .cleanupTaskEvidence("task_insert_failure", 42L);
        assertThat(workspace).doesNotExist();
    }

    private static VideoKeyframeProperties properties() {
        VideoKeyframeProperties properties = new VideoKeyframeProperties();
        properties.setMaxKeyframesPerMinute(4);
        properties.setMaxKeyframesTotal(4);
        properties.setAnalysisMaxWidth(1600);
        properties.setEvidenceMaxWidth(960);
        properties.setSharpnessThreshold(20.0d);
        return properties;
    }

    private static VideoFrameSampler colorfulSampler() {
        return (source, timestamp, output, width, timeout) -> {
            try {
                BufferedImage image = new BufferedImage(1280, 720, BufferedImage.TYPE_INT_RGB);
                var graphics = image.createGraphics();
                try {
                    graphics.setColor(Color.WHITE);
                    graphics.fillRect(0, 0, 1280, 720);
                    graphics.setColor(new Color((int) (timestamp % 200), 40, 120));
                    for (int x = 0; x < 1280; x += 24) {
                        graphics.fillRect(x, (int) ((x + timestamp / 100) % 650), 12, 60);
                    }
                    graphics.setColor(Color.BLACK);
                    graphics.drawString("Course frame " + timestamp, 80, 120);
                } finally {
                    graphics.dispose();
                }
                Files.createDirectories(output.getParent());
                ImageIO.write(image, "png", output.toFile());
                return output;
            } catch (Exception exception) {
                throw new IllegalStateException(exception);
            }
        };
    }

    private static VideoFrameSampler solidSampler(Color color) {
        return (source, timestamp, output, width, timeout) -> {
            try {
                BufferedImage image = new BufferedImage(640, 360, BufferedImage.TYPE_INT_RGB);
                var graphics = image.createGraphics();
                graphics.setColor(color);
                graphics.fillRect(0, 0, 640, 360);
                graphics.dispose();
                Files.createDirectories(output.getParent());
                ImageIO.write(image, "png", output.toFile());
                return output;
            } catch (Exception exception) {
                throw new IllegalStateException(exception);
            }
        };
    }

    private static VideoFrameSampler staticPatternSampler() {
        return (source, timestamp, output, width, timeout) -> {
            try {
                BufferedImage image = new BufferedImage(1280, 720, BufferedImage.TYPE_INT_RGB);
                var graphics = image.createGraphics();
                graphics.setColor(Color.WHITE);
                graphics.fillRect(0, 0, 1280, 720);
                graphics.setColor(Color.BLUE);
                for (int x = 20; x < 1260; x += 32) {
                    graphics.fillRect(x, 80 + (x % 240), 16, 180);
                }
                graphics.setColor(Color.BLACK);
                graphics.drawString("Static course architecture", 80, 100);
                graphics.fillRect(500 + (int) (timestamp % 11), 500, 3, 3);
                graphics.dispose();
                Files.createDirectories(output.getParent());
                ImageIO.write(image, "png", output.toFile());
                return output;
            } catch (Exception exception) {
                throw new IllegalStateException(exception);
            }
        };
    }

    private static StorageService storageCapturing(List<BufferedImage> persisted) {
        return new StorageService() {
            @Override
            public void putObject(String objectKey, Path sourceFile, long sizeBytes, String contentType) {
                try {
                    persisted.add(ImageIO.read(sourceFile.toFile()));
                } catch (Exception exception) {
                    throw new IllegalStateException(exception);
                }
            }

            @Override
            public boolean objectExists(String objectKey) {
                return false;
            }

            @Override
            public InputStream openObject(String objectKey) {
                throw new AssertionError("Adaptive OCR/VLM must not reopen a 320px storage thumbnail");
            }

            @Override
            public void deleteObject(String objectKey) {
            }
        };
    }
}
