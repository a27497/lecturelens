package com.example.courselingo.vision.keyframe;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.storage.StorageService;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.vision.analysis.VideoKeyframeAnalysis;
import com.example.courselingo.vision.analysis.VisionAnalysisProperties;
import com.example.courselingo.vision.analysis.VisionAnalysisStatus;
import com.example.courselingo.vision.analysis.mapper.VideoKeyframeAnalysisMapper;
import com.example.courselingo.vision.keyframe.mapper.VideoKeyframeMapper;
import com.example.courselingo.vision.ocr.OcrStatus;
import com.example.courselingo.vision.ocr.VideoKeyframeOcr;
import com.example.courselingo.vision.ocr.VisionOcrProperties;
import com.example.courselingo.vision.ocr.mapper.VideoKeyframeOcrMapper;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class VideoKeyframeServiceTest {

    @Mock
    private CurrentUserService currentUserService;

    @Mock
    private AnalysisTaskMapper analysisTaskMapper;

    @Mock
    private VideoKeyframeMapper videoKeyframeMapper;

    @Mock
    private StorageService storageService;

    @Mock
    private VideoKeyframeOcrMapper ocrMapper;

    @Mock
    private VideoKeyframeAnalysisMapper analysisMapper;

    private VideoKeyframeService service;

    @BeforeEach
    void setUp() {
        service = new VideoKeyframeServiceImpl(
            currentUserService,
            analysisTaskMapper,
            videoKeyframeMapper,
            storageService
        );
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
    }

    @Test
    void springWiredServiceReturnsExistingOcrRowsEvenWhenOcrIsDisabled() {
        new ApplicationContextRunner()
            .withBean(CurrentUserService.class, () -> currentUserService)
            .withBean(AnalysisTaskMapper.class, () -> analysisTaskMapper)
            .withBean(VideoKeyframeMapper.class, () -> videoKeyframeMapper)
            .withBean(StorageService.class, () -> storageService)
            .withBean(VideoKeyframeOcrMapper.class, () -> ocrMapper)
            .withBean(VisionOcrProperties.class, VisionOcrProperties::new)
            .withBean(VideoKeyframeAnalysisMapper.class, () -> analysisMapper)
            .withBean(VisionAnalysisProperties.class, VisionAnalysisProperties::new)
            .withBean(VideoKeyframeServiceImpl.class)
            .run(context -> {
                when(analysisTaskMapper.selectByIdAndUserId("task_1", 42L)).thenReturn(task("task_1", 42L));
                when(videoKeyframeMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(entity(9L)));
                when(ocrMapper.selectByKeyframeIds("task_1", 42L, List.of(9L))).thenReturn(List.of(ocrRow(9L, OcrStatus.SUCCEEDED, "COURSELINGO OCR TEST")));
                when(analysisMapper.selectByKeyframeIds("task_1", 42L, List.of(9L)))
                    .thenReturn(List.of(analysisRow(9L, VisionAnalysisStatus.SUCCEEDED, "PPT", "A slide about CourseLingo")));

                List<VideoKeyframeView> keyframes = context.getBean(VideoKeyframeService.class)
                    .listKeyframes("Bearer access-token", "task_1");

                assertThat(keyframes).hasSize(1);
                assertThat(keyframes.getFirst().ocr().status()).isEqualTo(OcrStatus.SUCCEEDED.name());
                assertThat(keyframes.getFirst().ocr().text()).isEqualTo("COURSELINGO OCR TEST");
                assertThat(keyframes.getFirst().visualAnalysis().status()).isEqualTo(VisionAnalysisStatus.SUCCEEDED.name());
                assertThat(keyframes.getFirst().visualAnalysis().summary()).isEqualTo("A slide about CourseLingo");
            });
    }

    @Test
    void disabledOcrWithoutRowsReturnsDisabledFallback() {
        VideoKeyframeService serviceWithOcr = new VideoKeyframeServiceImpl(
            currentUserService,
            analysisTaskMapper,
            videoKeyframeMapper,
            storageService,
            ocrMapper,
            new VisionOcrProperties(),
            analysisMapper,
            disabledVisionAnalysisProperties()
        );
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 42L)).thenReturn(task("task_1", 42L));
        when(videoKeyframeMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(entity(9L)));
        when(ocrMapper.selectByKeyframeIds("task_1", 42L, List.of(9L))).thenReturn(List.of());
        when(analysisMapper.selectByKeyframeIds("task_1", 42L, List.of(9L))).thenReturn(List.of());

        List<VideoKeyframeView> keyframes = serviceWithOcr.listKeyframes("Bearer access-token", "task_1");

        assertThat(keyframes).hasSize(1);
        assertThat(keyframes.getFirst().ocr().status()).isEqualTo(OcrStatus.DISABLED.name());
        assertThat(keyframes.getFirst().visualAnalysis().status()).isEqualTo(VisionAnalysisStatus.DISABLED.name());
    }

    @Test
    void failedOcrRowReturnsFriendlyFailureWithoutProviderDetails() {
        VideoKeyframeService serviceWithOcr = new VideoKeyframeServiceImpl(
            currentUserService,
            analysisTaskMapper,
            videoKeyframeMapper,
            storageService,
            ocrMapper,
            new VisionOcrProperties(),
            analysisMapper,
            disabledVisionAnalysisProperties()
        );
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 42L)).thenReturn(task("task_1", 42L));
        when(videoKeyframeMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(entity(9L)));
        when(ocrMapper.selectByKeyframeIds("task_1", 42L, List.of(9L))).thenReturn(List.of(ocrRow(
            9L,
            OcrStatus.FAILED,
            "provider stderr objectKey=keyframes/42/task_1/frame.jpg token=abc"
        )));
        when(analysisMapper.selectByKeyframeIds("task_1", 42L, List.of(9L)))
            .thenReturn(List.of(analysisRow(
                9L,
                VisionAnalysisStatus.FAILED,
                "OTHER",
                "provider stderr objectKey=keyframes/42/task_1/frame.jpg token=abc"
            )));

        List<VideoKeyframeView> keyframes = serviceWithOcr.listKeyframes("Bearer access-token", "task_1");

        assertThat(keyframes.getFirst().ocr().status()).isEqualTo(OcrStatus.FAILED.name());
        assertThat(keyframes.getFirst().ocr().text()).isEmpty();
        assertThat(keyframes.getFirst().ocr().message())
            .doesNotContain("stderr")
            .doesNotContain("keyframes/42")
            .doesNotContain("token");
        assertThat(keyframes.getFirst().visualAnalysis().status()).isEqualTo(VisionAnalysisStatus.FAILED.name());
        assertThat(keyframes.getFirst().visualAnalysis().message())
            .doesNotContain("stderr")
            .doesNotContain("keyframes/42")
            .doesNotContain("token");
    }

    @Test
    void listsOnlyOwnerScopedKeyframesWithoutObjectKeys() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 42L)).thenReturn(task("task_1", 42L));
        when(videoKeyframeMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(entity(9L)));

        List<VideoKeyframeView> keyframes = service.listKeyframes("Bearer access-token", "task_1");

        assertThat(keyframes).hasSize(1);
        assertThat(keyframes.getFirst().frameId()).isEqualTo(9L);
        assertThat(keyframes.getFirst().imageUrl()).isEqualTo("/api/tasks/task_1/keyframes/9/image");
        assertThat(keyframes.toString())
            .doesNotContain("objectKey")
            .doesNotContain("minio")
            .doesNotContain("localPath")
            .doesNotContain("secret")
            .doesNotContain("token");
    }

    @Test
    void nonOwnerCannotListOrDownloadKeyframes() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 42L)).thenReturn(null);

        assertThatThrownBy(() -> service.listKeyframes("Bearer access-token", "task_1"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_NOT_FOUND);
        assertThatThrownBy(() -> service.downloadKeyframeImage("Bearer access-token", "task_1", 9L))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_NOT_FOUND);

        verify(videoKeyframeMapper, never()).selectByTaskIdAndUserId("task_1", 42L);
        verify(videoKeyframeMapper, never()).selectByIdAndTaskIdAndUserId(9L, "task_1", 42L);
    }

    @Test
    void downloadsOwnerScopedImageThroughStorageService() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 42L)).thenReturn(task("task_1", 42L));
        VideoKeyframe entity = entity(9L);
        when(videoKeyframeMapper.selectByIdAndTaskIdAndUserId(9L, "task_1", 42L)).thenReturn(entity);
        when(storageService.openObject("keyframes/42/task_1/frame-000009.jpg"))
            .thenReturn(new ByteArrayInputStream("jpg".getBytes(StandardCharsets.UTF_8)));

        VideoKeyframeImage image = service.downloadKeyframeImage("Bearer access-token", "task_1", 9L);

        assertThat(image.contentType()).isEqualTo("image/jpeg");
        assertThat(image.sizeBytes()).isEqualTo(1234L);
        assertThat(image.inputStream()).isNotNull();
    }

    private static AnalysisTask task(String taskId, Long userId) {
        AnalysisTask task = new AnalysisTask();
        task.setId(taskId);
        task.setUserId(userId);
        task.setUploadId("up_1");
        task.setTargetLanguage("zh-CN");
        return task;
    }

    private static VideoKeyframeOcr ocrRow(Long keyframeId, OcrStatus status, String textOrError) {
        VideoKeyframeOcr row = new VideoKeyframeOcr();
        row.setId(100L + keyframeId);
        row.setTaskId("task_1");
        row.setUserId(42L);
        row.setKeyframeId(keyframeId);
        row.setTimestampMillis(12_345L);
        row.setProvider("tesseract");
        row.setLanguageHint("chi_sim+eng");
        row.setOcrText(status == OcrStatus.SUCCEEDED ? textOrError : "");
        row.setTextLength(status == OcrStatus.SUCCEEDED ? textOrError.length() : 0);
        row.setTextTruncated(false);
        row.setConfidence(status == OcrStatus.SUCCEEDED ? 0.91 : null);
        row.setStatus(status.name());
        row.setErrorCode(status == OcrStatus.FAILED ? "OCR_PROVIDER_FAILED" : null);
        row.setErrorMessage(status == OcrStatus.FAILED ? textOrError : null);
        row.setDurationMillis(123L);
        row.setCreatedAt(LocalDateTime.of(2026, 7, 6, 10, 1));
        row.setUpdatedAt(LocalDateTime.of(2026, 7, 6, 10, 1));
        return row;
    }

    private static VideoKeyframeAnalysis analysisRow(
        Long keyframeId,
        VisionAnalysisStatus status,
        String screenType,
        String summaryOrError
    ) {
        VideoKeyframeAnalysis row = new VideoKeyframeAnalysis();
        row.setId(200L + keyframeId);
        row.setTaskId("task_1");
        row.setUserId(42L);
        row.setKeyframeId(keyframeId);
        row.setTimestampMillis(12_345L);
        row.setProvider("openai-compatible-vision");
        row.setModel("qwen-vl");
        row.setScreenType(screenType);
        row.setVisualSummary(status == VisionAnalysisStatus.SUCCEEDED ? summaryOrError : "");
        row.setDetectedElementsJson(status == VisionAnalysisStatus.SUCCEEDED ? "[\"title\",\"chart\"]" : "[]");
        row.setStatus(status.name());
        row.setErrorCode(status == VisionAnalysisStatus.FAILED ? "VISION_PROVIDER_FAILED" : null);
        row.setErrorMessage(status == VisionAnalysisStatus.FAILED ? summaryOrError : null);
        row.setDurationMillis(321L);
        row.setCreatedAt(LocalDateTime.of(2026, 7, 6, 10, 1));
        row.setUpdatedAt(LocalDateTime.of(2026, 7, 6, 10, 1));
        return row;
    }

    private static VisionAnalysisProperties disabledVisionAnalysisProperties() {
        VisionAnalysisProperties properties = new VisionAnalysisProperties();
        properties.setEnabled(false);
        return properties;
    }

    private static VideoKeyframe entity(Long id) {
        VideoKeyframe keyframe = new VideoKeyframe();
        keyframe.setId(id);
        keyframe.setTaskId("task_1");
        keyframe.setUserId(42L);
        keyframe.setFrameIndex(9);
        keyframe.setTimestampMillis(12_345L);
        keyframe.setTimeText("00:12.345");
        keyframe.setChangeScore(0.42);
        keyframe.setSelectReason(KeyframeSelectionReason.SCENE_CHANGE.name());
        keyframe.setContentType("image/jpeg");
        keyframe.setSizeBytes(1234L);
        keyframe.setStorageBackend("MINIO");
        keyframe.setObjectKey("keyframes/42/task_1/frame-000009.jpg");
        keyframe.setCreatedAt(LocalDateTime.of(2026, 7, 6, 10, 0));
        keyframe.setUpdatedAt(LocalDateTime.of(2026, 7, 6, 10, 0));
        return keyframe;
    }
}
