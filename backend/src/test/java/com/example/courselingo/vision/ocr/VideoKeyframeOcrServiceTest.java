package com.example.courselingo.vision.ocr;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.when;

import com.example.courselingo.storage.StorageService;
import com.example.courselingo.vision.keyframe.KeyframeSelectionReason;
import com.example.courselingo.vision.keyframe.VideoKeyframe;
import com.example.courselingo.vision.keyframe.mapper.VideoKeyframeMapper;
import com.example.courselingo.vision.ocr.mapper.VideoKeyframeOcrMapper;
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class VideoKeyframeOcrServiceTest {

    private static final Clock CLOCK = Clock.fixed(Instant.parse("2026-07-06T10:00:00Z"), ZoneOffset.UTC);

    @Mock
    private VideoKeyframeMapper keyframeMapper;

    @Mock
    private VideoKeyframeOcrMapper ocrMapper;

    private List<VideoKeyframeOcr> rows;
    private int deleteCalls;
    private VisionOcrProperties properties;
    private VideoKeyframeOcrScanService service;

    @BeforeEach
    void setUp() {
        rows = new ArrayList<>();
        deleteCalls = 0;
        doAnswer(invocation -> {
            rows.add(invocation.getArgument(0, VideoKeyframeOcr.class));
            return 1;
        }).when(ocrMapper).insert(any(VideoKeyframeOcr.class));
        doAnswer(invocation -> {
            deleteCalls++;
            rows.clear();
            return 1;
        }).when(ocrMapper).deleteByTaskIdAndUserId("task_1", 42L);
        properties = new VisionOcrProperties();
        properties.setEnabled(true);
        properties.setMaxTextLength(8);
        properties.setMaxKeyframesPerTask(2);
    }

    @Test
    void scanIsIdempotentAndStoresTruncatedOcrTextWithoutObjectKeys() {
        when(keyframeMapper.selectByTaskIdAndUserId("task_1", 42L))
            .thenReturn(List.of(keyframe(9L, 0L), keyframe(10L, 1000L)));
        service = newService(request -> new OcrResult(
            OcrStatus.SUCCEEDED,
            "Course introduction key points",
            0.92,
            "tesseract",
            "chi_sim+eng",
            120L,
            null,
            null
        ));

        VideoKeyframeOcrScanResult result = service.scan("task_1", 42L);
        VideoKeyframeOcrScanResult retry = service.scan("task_1", 42L);

        assertThat(result.saved()).isEqualTo(2);
        assertThat(retry.saved()).isEqualTo(2);
        assertThat(deleteCalls).isEqualTo(2);
        assertThat(rows).hasSize(2);
        assertThat(rows).allSatisfy(row -> {
            assertThat(row.getStatus()).isEqualTo(OcrStatus.SUCCEEDED.name());
            assertThat(row.getOcrText()).isEqualTo("Course i");
            assertThat(row.getTextLength()).isEqualTo("Course introduction key points".length());
            assertThat(row.getTextTruncated()).isTrue();
            assertThat(row.toString())
                .doesNotContain("objectKey")
                .doesNotContain("keyframes/42")
                .doesNotContain("localPath");
        });
    }

    @Test
    void providerFailureIsPersistedPerFrameAndDoesNotStopRemainingFrames() {
        when(keyframeMapper.selectByTaskIdAndUserId("task_1", 42L))
            .thenReturn(List.of(keyframe(9L, 0L), keyframe(10L, 1000L)));
        service = newService(new OcrProvider() {
            private int calls;

            @Override
            public OcrResult recognize(OcrRequest request) {
                calls++;
                if (calls == 1) {
                    throw new IllegalStateException(
                        "failed C:\\Users\\demo\\private objectKey=keyframes/42/task_1/frame.jpg token=abc"
                    );
                }
                return OcrResult.empty("tesseract", "chi_sim+eng", 30L);
            }
        });

        VideoKeyframeOcrScanResult result = service.scan("task_1", 42L);

        assertThat(result.failed()).isEqualTo(1);
        assertThat(result.empty()).isEqualTo(1);
        assertThat(rows).extracting(VideoKeyframeOcr::getStatus)
            .containsExactly(OcrStatus.FAILED.name(), OcrStatus.EMPTY.name());
        assertThat(rows.getFirst().getErrorMessage())
            .doesNotContain("C:\\Users")
            .doesNotContain("demo")
            .doesNotContain("objectKey")
            .doesNotContain("token")
            .doesNotContain("abc");
    }

    @Test
    void lowQualityOcrTextIsPersistedAsEmptyWithoutDisplayingGarbage() {
        when(keyframeMapper.selectByTaskIdAndUserId("task_1", 42L))
            .thenReturn(List.of(keyframe(9L, 0L), keyframe(10L, 1000L)));
        service = newService(new OcrProvider() {
            private int calls;

            @Override
            public OcrResult recognize(OcrRequest request) {
                calls++;
                if (calls == 1) {
                    return new OcrResult(
                        OcrStatus.SUCCEEDED,
                        "QO sD k 3 dl",
                        null,
                        "tesseract",
                        "chi_sim+eng",
                        40L,
                        null,
                        null
                    );
                }
                return new OcrResult(
                    OcrStatus.SUCCEEDED,
                    "What is OpenCL?",
                    null,
                    "tesseract",
                    "chi_sim+eng",
                    45L,
                    null,
                    null
                );
            }
        });

        VideoKeyframeOcrScanResult result = service.scan("task_1", 42L);

        assertThat(result.empty()).isEqualTo(1);
        assertThat(result.succeeded()).isEqualTo(1);
        assertThat(rows).extracting(VideoKeyframeOcr::getStatus)
            .containsExactly(OcrStatus.EMPTY.name(), OcrStatus.SUCCEEDED.name());
        assertThat(rows.getFirst().getOcrText()).isEmpty();
        assertThat(rows.getLast().getOcrText()).isEqualTo("What is");
    }

    @Test
    void keyframesOverLimitAreMarkedSkipped() {
        when(keyframeMapper.selectByTaskIdAndUserId("task_1", 42L))
            .thenReturn(List.of(keyframe(9L, 0L), keyframe(10L, 1000L), keyframe(11L, 2000L)));
        service = newService(request -> OcrResult.empty("tesseract", "chi_sim+eng", 20L));

        VideoKeyframeOcrScanResult result = service.scan("task_1", 42L);

        assertThat(result.skipped()).isEqualTo(1);
        assertThat(rows).extracting(VideoKeyframeOcr::getStatus)
            .containsExactly(OcrStatus.EMPTY.name(), OcrStatus.EMPTY.name(), OcrStatus.SKIPPED.name());
    }

    private VideoKeyframeOcrScanService newService(OcrProvider provider) {
        return new VideoKeyframeOcrScanServiceImpl(
            keyframeMapper,
            ocrMapper,
            new MemoryStorageService(),
            provider,
            properties,
            CLOCK
        );
    }

    private static VideoKeyframe keyframe(Long id, Long timestampMillis) {
        VideoKeyframe keyframe = new VideoKeyframe();
        keyframe.setId(id);
        keyframe.setTaskId("task_1");
        keyframe.setUserId(42L);
        keyframe.setFrameIndex(id.intValue());
        keyframe.setTimestampMillis(timestampMillis);
        keyframe.setTimeText("00:00.000");
        keyframe.setChangeScore(0.42);
        keyframe.setSelectReason(KeyframeSelectionReason.SCENE_CHANGE.name());
        keyframe.setContentType("image/jpeg");
        keyframe.setSizeBytes(1234L);
        keyframe.setStorageBackend("MINIO");
        keyframe.setObjectKey("keyframes/42/task_1/frame-" + id + ".jpg");
        keyframe.setCreatedAt(LocalDateTime.ofInstant(CLOCK.instant(), CLOCK.getZone()));
        keyframe.setUpdatedAt(LocalDateTime.ofInstant(CLOCK.instant(), CLOCK.getZone()));
        return keyframe;
    }

    private static final class MemoryStorageService implements StorageService {

        @Override
        public void putObject(String objectKey, Path sourceFile, long sizeBytes, String contentType) {
        }

        @Override
        public boolean objectExists(String objectKey) {
            return true;
        }

        @Override
        public InputStream openObject(String objectKey) {
            return new ByteArrayInputStream("image".getBytes(StandardCharsets.UTF_8));
        }

        @Override
        public void deleteObject(String objectKey) {
        }
    }
}
