package com.example.courselingo.result;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.ai.record.domain.AiCallRecordStatus;
import com.example.courselingo.ai.record.domain.AiCallStage;
import com.example.courselingo.ai.record.domain.AiCallType;
import com.example.courselingo.ai.record.dto.AiCallRecordView;
import com.example.courselingo.ai.record.service.AiCallRecordService;
import com.example.courselingo.artifact.domain.ArtifactType;
import com.example.courselingo.artifact.dto.ArtifactFileView;
import com.example.courselingo.artifact.service.ArtifactFileQueryService;
import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.fusion.VideoSegmentEvidence;
import com.example.courselingo.fusion.VideoSegmentResponse;
import com.example.courselingo.fusion.VideoSegmentService;
import com.example.courselingo.fusion.VideoSegmentStatus;
import com.example.courselingo.learning.dto.LearningPackageView;
import com.example.courselingo.learning.service.LearningPackageQueryService;
import com.example.courselingo.result.dto.TaskResultResponse;
import com.example.courselingo.result.service.TaskResultServiceImpl;
import com.example.courselingo.subtitle.dto.SubtitleSegmentView;
import com.example.courselingo.subtitle.dto.SubtitleTranslationSegmentView;
import com.example.courselingo.subtitle.service.SubtitleSegmentQueryService;
import com.example.courselingo.subtitle.service.SubtitleTranslationQueryService;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.task.model.AnalysisTaskStatus;
import com.example.courselingo.vision.analysis.VideoKeyframeAnalysis;
import com.example.courselingo.vision.analysis.VisionAnalysisProperties;
import com.example.courselingo.vision.analysis.VisionAnalysisStatus;
import com.example.courselingo.vision.analysis.mapper.VideoKeyframeAnalysisMapper;
import com.example.courselingo.vision.keyframe.KeyframeSelectionReason;
import com.example.courselingo.vision.keyframe.VideoKeyframe;
import com.example.courselingo.vision.keyframe.VideoKeyframeServiceImpl;
import com.example.courselingo.vision.keyframe.mapper.VideoKeyframeMapper;
import com.example.courselingo.vision.ocr.OcrStatus;
import com.example.courselingo.vision.ocr.VideoKeyframeOcr;
import com.example.courselingo.vision.ocr.VisionOcrProperties;
import com.example.courselingo.vision.ocr.mapper.VideoKeyframeOcrMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class TaskResultServiceTest {

    @Mock
    private CurrentUserService currentUserService;

    @Mock
    private AnalysisTaskMapper analysisTaskMapper;

    @Mock
    private SubtitleSegmentQueryService subtitleSegmentQueryService;

    @Mock
    private SubtitleTranslationQueryService subtitleTranslationQueryService;

    @Mock
    private LearningPackageQueryService learningPackageQueryService;

    @Mock
    private ArtifactFileQueryService artifactFileQueryService;

    @Mock
    private AiCallRecordService aiCallRecordService;

    @Mock
    private VideoKeyframeMapper videoKeyframeMapper;

    @Mock
    private VideoKeyframeOcrMapper ocrMapper;

    @Mock
    private VideoKeyframeAnalysisMapper analysisMapper;

    @Mock
    private VideoSegmentService videoSegmentService;

    private TaskResultServiceImpl service;

    @BeforeEach
    void setUp() {
        service = new TaskResultServiceImpl(
            currentUserService,
            analysisTaskMapper,
            subtitleSegmentQueryService,
            subtitleTranslationQueryService,
            learningPackageQueryService,
            artifactFileQueryService,
            aiCallRecordService,
            new ObjectMapper()
        );
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
    }

    @Test
    void resultAndKeyframesServicesReturnSameExistingOcrStatusAndText() {
        TaskResultServiceImpl resultService = new TaskResultServiceImpl(
            currentUserService,
            analysisTaskMapper,
            subtitleSegmentQueryService,
            subtitleTranslationQueryService,
            null,
            learningPackageQueryService,
            artifactFileQueryService,
            aiCallRecordService,
            videoKeyframeMapper,
            ocrMapper,
            new VisionOcrProperties(),
            analysisMapper,
            disabledVisionAnalysisProperties(),
            null,
            new ObjectMapper()
        );
        VideoKeyframeServiceImpl keyframeService = new VideoKeyframeServiceImpl(
            currentUserService,
            analysisTaskMapper,
            videoKeyframeMapper,
            null,
            ocrMapper,
            new VisionOcrProperties(),
            analysisMapper,
            disabledVisionAnalysisProperties()
        );
        VideoKeyframe keyframe = keyframe();
        VideoKeyframeOcr ocr = ocrRow(9L, OcrStatus.SUCCEEDED, "COURSELINGO OCR TEST");
        VideoKeyframeAnalysis analysis = analysisRow(9L, VisionAnalysisStatus.SUCCEEDED, "PPT", "A slide about CourseLingo");
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 42L)).thenReturn(task("task_1", 42L));
        when(subtitleSegmentQueryService.listByTaskId("task_1", 42L)).thenReturn(List.of());
        when(subtitleTranslationQueryService.listTranslations("task_1", 42L, "zh-CN")).thenReturn(List.of());
        when(learningPackageQueryService.getByTaskAndLanguage("task_1", 42L, "zh-CN")).thenReturn(Optional.empty());
        when(artifactFileQueryService.listByTaskId("task_1", 42L)).thenReturn(List.of());
        when(aiCallRecordService.listByTask("task_1", 42L)).thenReturn(List.of());
        when(videoKeyframeMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(keyframe));
        when(ocrMapper.selectByKeyframeIds("task_1", 42L, List.of(9L))).thenReturn(List.of(ocr));
        when(analysisMapper.selectByKeyframeIds("task_1", 42L, List.of(9L))).thenReturn(List.of(analysis));

        TaskResultResponse result = resultService.getResult("task_1", "Bearer access-token");
        var keyframes = keyframeService.listKeyframes("Bearer access-token", "task_1");

        assertThat(result.keyframes()).hasSize(1);
        assertThat(keyframes).hasSize(1);
        assertThat(result.keyframes().getFirst().ocr().status()).isEqualTo(OcrStatus.SUCCEEDED.name());
        assertThat(keyframes.getFirst().ocr().status()).isEqualTo(result.keyframes().getFirst().ocr().status());
        assertThat(keyframes.getFirst().ocr().text()).isEqualTo(result.keyframes().getFirst().ocr().text());
        assertThat(result.keyframes().getFirst().visualAnalysis().status()).isEqualTo(VisionAnalysisStatus.SUCCEEDED.name());
        assertThat(keyframes.getFirst().visualAnalysis().status())
            .isEqualTo(result.keyframes().getFirst().visualAnalysis().status());
        assertThat(keyframes.getFirst().visualAnalysis().summary())
            .isEqualTo(result.keyframes().getFirst().visualAnalysis().summary());
        assertThat(result.keyframes().getFirst().toString())
            .doesNotContain("objectKey")
            .doesNotContain("localPath")
            .doesNotContain("secret");
    }

    @Test
    void ownerCanReadAggregatedResultWithoutSensitiveFields() {
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 42L)).thenReturn(task("task_1", 42L));
        when(subtitleSegmentQueryService.listByTaskId("task_1", 42L))
            .thenReturn(List.of(new SubtitleSegmentView(
                "task_1",
                0,
                0L,
                3000L,
                "en",
                "hello",
                "mock-asr",
                time(1),
                time(2)
            )));
        when(subtitleTranslationQueryService.listTranslations("task_1", 42L, "zh-CN"))
            .thenReturn(List.of(new SubtitleTranslationSegmentView(
                "task_1",
                0,
                0L,
                3000L,
                "en",
                "zh-CN",
                "你好",
                "mock-llm",
                time(1),
                time(2)
            )));
        when(learningPackageQueryService.getByTaskAndLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(Optional.of(new LearningPackageView(
                "task_1",
                "en",
                "zh-CN",
                "Lesson",
                "Summary",
                "[{\"index\":1,\"text\":\"Point\"}]",
                "[{\"term\":\"API\",\"definition\":\"Interface\",\"translation\":\"接口\"}]",
                "[{\"question\":\"Q?\",\"answer\":\"A\"}]",
                "mock-llm",
                "v1",
                time(1),
                time(2)
            )));
        when(artifactFileQueryService.listByTaskId("task_1", 42L))
            .thenReturn(List.of(new ArtifactFileView(
                "task_1",
                ArtifactType.JSON,
                "zh-CN",
                "task_1-zh-CN.json",
                "application/json; charset=utf-8",
                "minio",
                1234L,
                "abc123",
                time(1),
                time(2)
            )));
        when(aiCallRecordService.listByTask("task_1", 42L))
            .thenReturn(List.of(new AiCallRecordView(
                7L,
                "task_1",
                AiCallType.LLM,
                AiCallStage.TRANSLATION,
                "mock-llm",
                "mock-model",
                AiCallRecordStatus.SUCCEEDED,
                time(1),
                time(2),
                100L,
                10,
                20,
                30,
                40,
                50,
                "request-fingerprint",
                "response-fingerprint",
                null,
                null,
                null,
                time(1),
                time(2)
            )));

        TaskResultResponse response = service.getResult("task_1", "Bearer access-token");

        assertThat(response.taskId()).isEqualTo("task_1");
        assertThat(response.targetLanguage()).isEqualTo("zh-CN");
        assertThat(response.subtitles()).extracting("sourceText").containsExactly("hello");
        assertThat(response.translations()).extracting("translatedText").containsExactly("你好");
        assertThat(response.learningPackage()).isNotNull();
        assertThat(response.learningPackage().keyPoints()).extracting("text").containsExactly("Point");
        assertThat(response.learningPackage().glossary()).extracting("term").containsExactly("API");
        assertThat(response.learningPackage().qa()).extracting("question").containsExactly("Q?");
        assertThat(response.artifacts()).extracting("fileName").containsExactly("task_1-zh-CN.json");
        assertThat(response.keyframes()).isEmpty();
        assertThat(response.aiCallRecords()).extracting("id").containsExactly(7L);
        assertThat(response.toString())
            .doesNotContain("userId")
            .doesNotContain("objectKey")
            .doesNotContain("localPath")
            .doesNotContain("authorization")
            .doesNotContain("apiKey")
            .doesNotContain("secret")
            .doesNotContain("request-fingerprint")
            .doesNotContain("response-fingerprint");
    }

    @Test
    void resultIncludesVideoSegmentsFromSharedOwnerScopedService() {
        TaskResultServiceImpl resultService = new TaskResultServiceImpl(
            currentUserService,
            analysisTaskMapper,
            subtitleSegmentQueryService,
            subtitleTranslationQueryService,
            null,
            learningPackageQueryService,
            artifactFileQueryService,
            aiCallRecordService,
            null,
            null,
            null,
            null,
            null,
            videoSegmentService,
            new ObjectMapper()
        );
        VideoSegmentResponse segment = new VideoSegmentResponse(
            5L,
            0,
            0L,
            60_000L,
            "00:00:00 - 00:01:00",
            "Redis ASR",
            "Redis OCR",
            "Redis slide",
            "Segment summary Redis",
            List.of("Redis"),
            new VideoSegmentEvidence(List.of(1L), List.of(2L), List.of(3L), List.of(4L), java.util.Map.of("asr", 1)),
            VideoSegmentStatus.SUCCEEDED.name(),
            0.8
        );
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 42L)).thenReturn(task("task_1", 42L));
        when(subtitleSegmentQueryService.listByTaskId("task_1", 42L)).thenReturn(List.of());
        when(subtitleTranslationQueryService.listTranslations("task_1", 42L, "zh-CN")).thenReturn(List.of());
        when(learningPackageQueryService.getByTaskAndLanguage("task_1", 42L, "zh-CN")).thenReturn(Optional.empty());
        when(artifactFileQueryService.listByTaskId("task_1", 42L)).thenReturn(List.of());
        when(aiCallRecordService.listByTask("task_1", 42L)).thenReturn(List.of());
        when(videoSegmentService.listByTaskId("task_1", 42L, 300, 0, "")).thenReturn(List.of(segment));

        TaskResultResponse response = resultService.getResult("task_1", "Bearer access-token");

        assertThat(response.videoSegments()).containsExactly(segment);
        assertThat(response.toString())
            .doesNotContain("objectKey")
            .doesNotContain("localPath")
            .doesNotContain("secret");
    }

    @Test
    void missingResultPartsReturnEmptyCollectionsAndNullLearningPackage() {
        when(analysisTaskMapper.selectByIdAndUserId("task_empty", 42L)).thenReturn(task("task_empty", 42L));
        when(subtitleSegmentQueryService.listByTaskId("task_empty", 42L)).thenReturn(List.of());
        when(subtitleTranslationQueryService.listTranslations("task_empty", 42L, "zh-CN")).thenReturn(List.of());
        when(learningPackageQueryService.getByTaskAndLanguage("task_empty", 42L, "zh-CN")).thenReturn(Optional.empty());
        when(artifactFileQueryService.listByTaskId("task_empty", 42L)).thenReturn(List.of());
        when(aiCallRecordService.listByTask("task_empty", 42L)).thenReturn(List.of());

        TaskResultResponse response = service.getResult("task_empty", "Bearer access-token");

        assertThat(response.subtitles()).isEmpty();
        assertThat(response.translations()).isEmpty();
        assertThat(response.learningPackage()).isNull();
        assertThat(response.artifacts()).isEmpty();
        assertThat(response.keyframes()).isEmpty();
        assertThat(response.aiCallRecords()).isEmpty();
    }

    @Test
    void nonOwnerOrMissingTaskFailsBeforeReadingResultTables() {
        when(analysisTaskMapper.selectByIdAndUserId("task_missing", 42L)).thenReturn(null);

        assertThatThrownBy(() -> service.getResult("task_missing", "Bearer access-token"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_NOT_FOUND);

        verify(subtitleSegmentQueryService, never()).listByTaskId("task_missing", 42L);
        verify(subtitleTranslationQueryService, never()).listTranslations("task_missing", 42L, "zh-CN");
        verify(learningPackageQueryService, never()).getByTaskAndLanguage("task_missing", 42L, "zh-CN");
        verify(artifactFileQueryService, never()).listByTaskId("task_missing", 42L);
        verify(aiCallRecordService, never()).listByTask("task_missing", 42L);
    }

    private static AnalysisTask task(String taskId, Long userId) {
        AnalysisTask task = new AnalysisTask();
        task.setId(taskId);
        task.setUserId(userId);
        task.setUploadId("up_1");
        task.setTargetLanguage("zh-CN");
        task.setStatus(AnalysisTaskStatus.SUCCEEDED.name());
        task.setCreatedAt(time(1));
        task.setUpdatedAt(time(2));
        return task;
    }

    private static VideoKeyframe keyframe() {
        VideoKeyframe keyframe = new VideoKeyframe();
        keyframe.setId(9L);
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
        keyframe.setCreatedAt(time(1));
        keyframe.setUpdatedAt(time(2));
        return keyframe;
    }

    private static VideoKeyframeOcr ocrRow(Long keyframeId, OcrStatus status, String text) {
        VideoKeyframeOcr row = new VideoKeyframeOcr();
        row.setId(100L + keyframeId);
        row.setTaskId("task_1");
        row.setUserId(42L);
        row.setKeyframeId(keyframeId);
        row.setTimestampMillis(12_345L);
        row.setProvider("tesseract");
        row.setLanguageHint("chi_sim+eng");
        row.setOcrText(text);
        row.setTextLength(text.length());
        row.setTextTruncated(false);
        row.setConfidence(0.91);
        row.setStatus(status.name());
        row.setDurationMillis(123L);
        row.setCreatedAt(time(1));
        row.setUpdatedAt(time(2));
        return row;
    }

    private static VideoKeyframeAnalysis analysisRow(
        Long keyframeId,
        VisionAnalysisStatus status,
        String screenType,
        String summary
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
        row.setVisualSummary(summary);
        row.setDetectedElementsJson("[\"title\",\"diagram\"]");
        row.setStatus(status.name());
        row.setDurationMillis(321L);
        row.setCreatedAt(time(1));
        row.setUpdatedAt(time(2));
        return row;
    }

    private static VisionAnalysisProperties disabledVisionAnalysisProperties() {
        VisionAnalysisProperties properties = new VisionAnalysisProperties();
        properties.setEnabled(false);
        return properties;
    }

    private static LocalDateTime time(int minute) {
        return LocalDateTime.of(2026, 6, 28, 10, minute);
    }
}
