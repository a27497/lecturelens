package com.example.courselingo.fusion;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.fusion.mapper.VideoSegmentMapper;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.subtitle.mapper.SubtitleSegmentMapper;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.vision.analysis.VideoKeyframeAnalysis;
import com.example.courselingo.vision.analysis.VisionAnalysisStatus;
import com.example.courselingo.vision.analysis.mapper.VideoKeyframeAnalysisMapper;
import com.example.courselingo.vision.keyframe.KeyframeSelectionReason;
import com.example.courselingo.vision.keyframe.VideoKeyframe;
import com.example.courselingo.vision.keyframe.mapper.VideoKeyframeMapper;
import com.example.courselingo.vision.ocr.OcrStatus;
import com.example.courselingo.vision.ocr.VideoKeyframeOcr;
import com.example.courselingo.vision.ocr.mapper.VideoKeyframeOcrMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InOrder;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class VideoSegmentFusionServiceTest {

    @Mock
    private VideoSegmentMapper videoSegmentMapper;

    @Mock
    private SubtitleSegmentMapper subtitleSegmentMapper;

    @Mock
    private VideoKeyframeMapper keyframeMapper;

    @Mock
    private VideoKeyframeOcrMapper ocrMapper;

    @Mock
    private VideoKeyframeAnalysisMapper analysisMapper;

    @Mock
    private CurrentUserService currentUserService;

    @Mock
    private AnalysisTaskMapper analysisTaskMapper;

    private VideoSegmentProperties properties;

    @BeforeEach
    void setUp() {
        properties = new VideoSegmentProperties();
        properties.setEnabled(true);
        properties.setWindowSeconds(60);
        properties.setMaxSegments(300);
        properties.setMaxAsrCharsPerWindow(80);
        properties.setMaxOcrCharsPerWindow(80);
        properties.setMaxVisualCharsPerWindow(80);
        properties.setMaxKeywords(8);
    }

    @Test
    void disabledFusionDoesNotReadOrWriteEvidenceTables() {
        properties.setEnabled(false);
        VideoSegmentFusionServiceImpl service = service();

        VideoSegmentFusionResult result = service.fuse("task_1", 42L);

        assertThat(result.saved()).isZero();
        verify(videoSegmentMapper, never()).deleteByTaskIdAndUserId("task_1", 42L);
        verify(subtitleSegmentMapper, never()).selectByTaskIdAndUserId("task_1", 42L);
        verify(keyframeMapper, never()).selectByTaskIdAndUserId("task_1", 42L);
    }

    @Test
    void fusesAsrOcrAndVisualEvidenceIntoSafeVideoSegment() {
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L))
            .thenReturn(List.of(subtitle(11L, 0, 1_000L, 20_000L, "Redis pipeline ASR text")));
        when(keyframeMapper.selectByTaskIdAndUserId("task_1", 42L))
            .thenReturn(List.of(keyframe(21L, 15_000L), keyframe(22L, 75_000L)));
        when(ocrMapper.selectByKeyframeIds("task_1", 42L, List.of(21L, 22L)))
            .thenReturn(List.of(
                ocr(31L, 21L, 15_000L, OcrStatus.SUCCEEDED, "Redis progress window"),
                ocr(32L, 22L, 75_000L, OcrStatus.FAILED, "should not appear")
            ));
        when(analysisMapper.selectByKeyframeIds("task_1", 42L, List.of(21L, 22L)))
            .thenReturn(List.of(
                analysis(41L, 21L, 15_000L, VisionAnalysisStatus.SUCCEEDED, "PPT", "A slide shows Redis progress"),
                analysis(42L, 22L, 75_000L, VisionAnalysisStatus.DISABLED, "OTHER", "should not appear")
            ));
        ArgumentCaptor<VideoSegment> captor = ArgumentCaptor.forClass(VideoSegment.class);

        VideoSegmentFusionResult result = service().fuse("task_1", 42L);

        assertThat(result.saved()).isEqualTo(1);
        InOrder order = inOrder(videoSegmentMapper);
        order.verify(videoSegmentMapper).deleteByTaskIdAndUserId("task_1", 42L);
        order.verify(videoSegmentMapper).insert(captor.capture());
        VideoSegment saved = captor.getValue();
        assertThat(saved.getTaskId()).isEqualTo("task_1");
        assertThat(saved.getUserId()).isEqualTo(42L);
        assertThat(saved.getSegmentIndex()).isZero();
        assertThat(saved.getStartMillis()).isZero();
        assertThat(saved.getEndMillis()).isEqualTo(60_000L);
        assertThat(saved.getTimeText()).isEqualTo("00:00:00 - 00:01:00");
        assertThat(saved.getAsrText()).contains("Redis pipeline ASR text");
        assertThat(saved.getOcrText()).contains("Redis progress window");
        assertThat(saved.getVisualSummary()).contains("Redis progress");
        assertThat(saved.getFusedSummary())
            .contains("Redis pipeline ASR text")
            .contains("Redis progress")
            .doesNotContain("null")
            .doesNotContain("undefined");
        assertThat(saved.getKeywordsJson()).contains("Redis");
        assertThat(saved.getEvidenceJson())
            .contains("\"subtitleSegmentIds\":[11]")
            .contains("\"keyframeIds\":[21]")
            .contains("\"ocrIds\":[31]")
            .contains("\"visualAnalysisIds\":[41]")
            .doesNotContain("objectKey")
            .doesNotContain("localPath")
            .doesNotContain("token")
            .doesNotContain("secret");
        assertThat(saved.getStatus()).isEqualTo(VideoSegmentStatus.SUCCEEDED.name());
        assertThat(saved.getConfidence()).isGreaterThan(0.0);
        assertThat(saved.getCreatedAt()).isEqualTo(time());
        assertThat(saved.getUpdatedAt()).isEqualTo(time());
    }

    @Test
    void maxSegmentsCapsGeneratedWindows() {
        properties.setWindowSeconds(30);
        properties.setMaxSegments(1);
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L))
            .thenReturn(List.of(
                subtitle(1L, 0, 1_000L, 20_000L, "first window"),
                subtitle(2L, 1, 35_000L, 50_000L, "second window")
            ));
        when(keyframeMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());

        VideoSegmentFusionResult result = service().fuse("task_1", 42L);

        assertThat(result.saved()).isEqualTo(1);
        assertThat(result.skipped()).isEqualTo(1);
    }

    @Test
    void clampsFinalWindowToAuthoritativeDurationAndIncludesTailEvidence() {
        long durationMillis = 4_090_265L;
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L))
            .thenReturn(List.of(subtitle(11L, 68, 4_080_000L, durationMillis, "final transcript segment")));
        when(keyframeMapper.selectByTaskIdAndUserId("task_1", 42L))
            .thenReturn(List.of(keyframe(21L, durationMillis - 1L)));
        when(ocrMapper.selectByKeyframeIds("task_1", 42L, List.of(21L)))
            .thenReturn(List.of(ocr(31L, 21L, durationMillis - 1L, OcrStatus.SUCCEEDED, "final OCR evidence")));
        when(analysisMapper.selectByKeyframeIds("task_1", 42L, List.of(21L)))
            .thenReturn(List.of(analysis(
                41L,
                21L,
                durationMillis - 1L,
                VisionAnalysisStatus.SUCCEEDED,
                "PPT",
                "final visual evidence"
            )));
        ArgumentCaptor<VideoSegment> captor = ArgumentCaptor.forClass(VideoSegment.class);

        VideoSegmentFusionResult result = service().fuse("task_1", 42L);

        assertThat(result.windows()).isEqualTo(69);
        assertThat(result.saved()).isEqualTo(1);
        verify(videoSegmentMapper).insert(captor.capture());
        VideoSegment saved = captor.getValue();
        assertThat(saved.getStartMillis()).isEqualTo(4_080_000L);
        assertThat(saved.getEndMillis()).isEqualTo(durationMillis);
        assertThat(saved.getEndMillis()).isLessThan(4_140_000L);
        assertThat(saved.getAsrText()).contains("final transcript segment");
        assertThat(saved.getOcrText()).contains("final OCR evidence");
        assertThat(saved.getVisualSummary()).contains("final visual evidence");
        assertThat(saved.getEvidenceJson())
            .contains("\"keyframeIds\":[21]")
            .contains("\"ocrIds\":[31]")
            .contains("\"visualAnalysisIds\":[41]");
    }

    @Test
    void exactWindowMultipleDoesNotCreateAnExtraEmptyWindow() {
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L))
            .thenReturn(List.of(subtitle(11L, 9, 540_000L, 600_000L, "tenth window")));
        when(keyframeMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        ArgumentCaptor<VideoSegment> captor = ArgumentCaptor.forClass(VideoSegment.class);

        VideoSegmentFusionResult result = service().fuse("task_1", 42L);

        assertThat(result.windows()).isEqualTo(10);
        assertThat(result.saved()).isEqualTo(1);
        verify(videoSegmentMapper).insert(captor.capture());
        assertThat(captor.getValue().getStartMillis()).isEqualTo(540_000L);
        assertThat(captor.getValue().getEndMillis()).isEqualTo(600_000L);
    }

    @Test
    void zeroTimestampEvidenceStillCreatesFirstWindow() {
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L))
            .thenReturn(List.of(subtitle(11L, 0, 0L, 0L, "short ASR text")));
        when(keyframeMapper.selectByTaskIdAndUserId("task_1", 42L))
            .thenReturn(List.of(keyframe(21L, 0L)));
        when(ocrMapper.selectByKeyframeIds("task_1", 42L, List.of(21L)))
            .thenReturn(List.of(ocr(31L, 21L, 0L, OcrStatus.SUCCEEDED, "CourseLingo title")));
        when(analysisMapper.selectByKeyframeIds("task_1", 42L, List.of(21L))).thenReturn(List.of());
        ArgumentCaptor<VideoSegment> captor = ArgumentCaptor.forClass(VideoSegment.class);

        VideoSegmentFusionResult result = service().fuse("task_1", 42L);

        assertThat(result.windows()).isEqualTo(1);
        assertThat(result.saved()).isEqualTo(1);
        verify(videoSegmentMapper).insert(captor.capture());
        VideoSegment saved = captor.getValue();
        assertThat(saved.getStartMillis()).isZero();
        assertThat(saved.getEndMillis()).isEqualTo(60_000L);
        assertThat(saved.getAsrText()).contains("short ASR text");
        assertThat(saved.getOcrText()).contains("CourseLingo title");
    }

    @Test
    void lowQualityHistoricalOcrRowsAreExcludedFromSegmentTextAndSummary() {
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L))
            .thenReturn(List.of(subtitle(11L, 0, 1_000L, 20_000L, "What is OpenCL?")));
        when(keyframeMapper.selectByTaskIdAndUserId("task_1", 42L))
            .thenReturn(List.of(keyframe(21L, 15_000L), keyframe(22L, 20_000L)));
        when(ocrMapper.selectByKeyframeIds("task_1", 42L, List.of(21L, 22L)))
            .thenReturn(List.of(
                ocr(31L, 21L, 15_000L, OcrStatus.SUCCEEDED, "aw & 9D"),
                ocr(32L, 22L, 20_000L, OcrStatus.SUCCEEDED, "Traditional Chatbot")
            ));
        when(analysisMapper.selectByKeyframeIds("task_1", 42L, List.of(21L, 22L))).thenReturn(List.of());
        ArgumentCaptor<VideoSegment> captor = ArgumentCaptor.forClass(VideoSegment.class);

        VideoSegmentFusionResult result = service().fuse("task_1", 42L);

        assertThat(result.saved()).isEqualTo(1);
        verify(videoSegmentMapper).insert(captor.capture());
        VideoSegment saved = captor.getValue();
        assertThat(saved.getOcrText()).contains("Traditional Chatbot");
        assertThat(saved.getOcrText()).doesNotContain("aw & 9D");
        assertThat(saved.getFusedSummary())
            .contains("Traditional Chatbot")
            .doesNotContain("aw & 9D");
    }

    @Test
    void listViewsReturnsSafeDtoAndSupportsKeywordFilter() {
        VideoSegment row = new VideoSegment();
        row.setId(100L);
        row.setTaskId("task_1");
        row.setUserId(42L);
        row.setSegmentIndex(0);
        row.setStartMillis(0L);
        row.setEndMillis(60_000L);
        row.setTimeText("00:00:00 - 00:01:00");
        row.setAsrText("Redis ASR");
        row.setOcrText("PPT Redis");
        row.setVisualSummary("A Redis slide");
        row.setFusedSummary("Segment summary Redis");
        row.setKeywordsJson("[\"Redis\",\"PPT\"]");
        row.setEvidenceJson("{\"subtitleSegmentIds\":[1],\"keyframeIds\":[2],\"counts\":{\"asr\":1,\"ocr\":1,\"visual\":1}}");
        row.setStatus(VideoSegmentStatus.SUCCEEDED.name());
        row.setConfidence(0.8);
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(row));

        List<VideoSegmentResponse> views = service().listByTaskId("task_1", 42L, 10, 0, "redis");

        assertThat(views).hasSize(1);
        assertThat(views.getFirst().segmentId()).isEqualTo(100L);
        assertThat(views.getFirst().keywords()).containsExactly("Redis", "PPT");
        assertThat(views.getFirst().evidence().counts().get("visual")).isEqualTo(1);
        assertThat(views.getFirst().toString())
            .doesNotContain("userId")
            .doesNotContain("objectKey")
            .doesNotContain("localPath")
            .doesNotContain("token")
            .doesNotContain("secret");
    }

    @Test
    void rebuildForOwnerRequiresSucceededTaskAndFusesExactlyOnce() {
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "u@example.com", "ACTIVE"));
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 42L)).thenReturn(task("SUCCEEDED"));
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L))
            .thenReturn(List.of(subtitle(11L, 0, 0L, 60_000L, "rebuild transcript")));
        when(keyframeMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());

        VideoSegmentFusionResult result = ownerScopedService().rebuildForCurrentUser(
            "Bearer access-token",
            "task_1"
        );

        assertThat(result).isEqualTo(new VideoSegmentFusionResult(1, 1, 0, 0));
        verify(videoSegmentMapper).deleteByTaskIdAndUserId("task_1", 42L);
        verify(videoSegmentMapper).insert(org.mockito.ArgumentMatchers.any(VideoSegment.class));
    }

    @Test
    void rebuildForOwnerRunsEvenWhenAutomaticPipelineFusionIsDisabled() {
        properties.setEnabled(false);
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "u@example.com", "ACTIVE"));
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 42L)).thenReturn(task("SUCCEEDED"));
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L))
            .thenReturn(List.of(subtitle(11L, 0, 0L, 60_000L, "repair transcript")));
        when(keyframeMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());

        VideoSegmentFusionResult result = ownerScopedService().rebuildForCurrentUser(
            "Bearer access-token",
            "task_1"
        );

        assertThat(result).isEqualTo(new VideoSegmentFusionResult(1, 1, 0, 0));
        verify(videoSegmentMapper).deleteByTaskIdAndUserId("task_1", 42L);
        verify(videoSegmentMapper).insert(org.mockito.ArgumentMatchers.any(VideoSegment.class));
    }

    @Test
    void rebuildHidesMissingOrNonOwnerTask() {
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "u@example.com", "ACTIVE"));
        when(analysisTaskMapper.selectByIdAndUserId("task_missing", 42L)).thenReturn(null);

        assertThatThrownBy(() -> ownerScopedService().rebuildForCurrentUser("Bearer access-token", "task_missing"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_NOT_FOUND);

        verify(videoSegmentMapper, never()).deleteByTaskIdAndUserId(
            org.mockito.ArgumentMatchers.any(),
            org.mockito.ArgumentMatchers.any()
        );
    }

    @Test
    void rebuildRejectsTaskThatIsNotSucceeded() {
        when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "u@example.com", "ACTIVE"));
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 42L)).thenReturn(task("RUNNING"));

        assertThatThrownBy(() -> ownerScopedService().rebuildForCurrentUser("Bearer access-token", "task_1"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_INVALID_STATUS);

        verify(videoSegmentMapper, never()).deleteByTaskIdAndUserId(
            org.mockito.ArgumentMatchers.any(),
            org.mockito.ArgumentMatchers.any()
        );
    }

    private VideoSegmentFusionServiceImpl service() {
        return new VideoSegmentFusionServiceImpl(
            videoSegmentMapper,
            subtitleSegmentMapper,
            keyframeMapper,
            ocrMapper,
            analysisMapper,
            properties,
            new ObjectMapper(),
            Clock.fixed(Instant.parse("2026-07-06T10:00:00Z"), ZoneOffset.UTC)
        );
    }

    private VideoSegmentFusionServiceImpl ownerScopedService() {
        return new VideoSegmentFusionServiceImpl(
            videoSegmentMapper,
            subtitleSegmentMapper,
            keyframeMapper,
            ocrMapper,
            analysisMapper,
            properties,
            new ObjectMapper(),
            currentUserService,
            analysisTaskMapper
        );
    }

    private static AnalysisTask task(String status) {
        AnalysisTask task = new AnalysisTask();
        task.setId("task_1");
        task.setUserId(42L);
        task.setStatus(status);
        return task;
    }

    private static SubtitleSegment subtitle(Long id, int index, long start, long end, String text) {
        SubtitleSegment segment = new SubtitleSegment();
        segment.setId(id);
        segment.setTaskId("task_1");
        segment.setUserId(42L);
        segment.setSegmentIndex(index);
        segment.setStartMillis(start);
        segment.setEndMillis(end);
        segment.setLanguage("zh-CN");
        segment.setText(text);
        return segment;
    }

    private static VideoKeyframe keyframe(Long id, long timestampMillis) {
        VideoKeyframe keyframe = new VideoKeyframe();
        keyframe.setId(id);
        keyframe.setTaskId("task_1");
        keyframe.setUserId(42L);
        keyframe.setFrameIndex(id.intValue());
        keyframe.setTimestampMillis(timestampMillis);
        keyframe.setTimeText("00:15.000");
        keyframe.setSelectReason(KeyframeSelectionReason.SCENE_CHANGE.name());
        keyframe.setObjectKey("internal/object/key.jpg");
        return keyframe;
    }

    private static VideoKeyframeOcr ocr(Long id, Long keyframeId, long timestampMillis, OcrStatus status, String text) {
        VideoKeyframeOcr row = new VideoKeyframeOcr();
        row.setId(id);
        row.setTaskId("task_1");
        row.setUserId(42L);
        row.setKeyframeId(keyframeId);
        row.setTimestampMillis(timestampMillis);
        row.setStatus(status.name());
        row.setOcrText(text);
        return row;
    }

    private static VideoKeyframeAnalysis analysis(
        Long id,
        Long keyframeId,
        long timestampMillis,
        VisionAnalysisStatus status,
        String screenType,
        String summary
    ) {
        VideoKeyframeAnalysis row = new VideoKeyframeAnalysis();
        row.setId(id);
        row.setTaskId("task_1");
        row.setUserId(42L);
        row.setKeyframeId(keyframeId);
        row.setTimestampMillis(timestampMillis);
        row.setStatus(status.name());
        row.setScreenType(screenType);
        row.setVisualSummary(summary);
        row.setDetectedElementsJson("[\"slide\"]");
        return row;
    }

    private static LocalDateTime time() {
        return LocalDateTime.of(2026, 7, 6, 10, 0);
    }
}
