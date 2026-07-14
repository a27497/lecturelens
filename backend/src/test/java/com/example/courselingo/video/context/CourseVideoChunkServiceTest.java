package com.example.courselingo.video.context;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.video.context.domain.CourseVideoChunk;
import com.example.courselingo.video.context.dto.CourseVideoContextChunkResponse;
import com.example.courselingo.video.context.dto.CourseVideoContextEvidenceItem;
import com.example.courselingo.video.context.mapper.CourseVideoChunkMapper;
import com.example.courselingo.video.context.service.CourseVideoContextBuildResult;
import com.example.courselingo.video.context.service.CourseVideoContextBuilder;
import com.example.courselingo.video.context.service.CourseVideoContextServiceImpl;
import com.example.courselingo.video.context.service.CourseVideoContextSourceSnapshot;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class CourseVideoChunkServiceTest {

    private static final Clock FIXED_CLOCK = Clock.fixed(Instant.parse("2026-07-09T00:00:00Z"), ZoneOffset.UTC);

    @Mock
    private CurrentUserService currentUserService;

    @Mock
    private AnalysisTaskMapper analysisTaskMapper;

    @Mock
    private CourseVideoChunkMapper chunkMapper;

    @Mock
    private CourseVideoContextBuilder builder;

    private CourseVideoContextServiceImpl service;

    @BeforeEach
    void setUp() {
        service = new CourseVideoContextServiceImpl(
            currentUserService,
            analysisTaskMapper,
            chunkMapper,
            builder,
            new ObjectMapper(),
            FIXED_CLOCK
        );
    }

    @Test
    void getRejectsMissingOrNonOwnerTask() {
        when(currentUserService.currentUser("Bearer demo"))
            .thenReturn(new CurrentUserResponse(42L, "u@example.com", "ACTIVE"));
        when(analysisTaskMapper.selectByIdAndUserId("task_missing", 42L)).thenReturn(null);

        assertThatThrownBy(() -> service.get("task_missing", "Bearer demo"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_NOT_FOUND);

        verify(chunkMapper, never()).selectByTaskIdUserIdAndTargetLanguage(any(), any(), any());
    }

    @Test
    void rebuildDeletesOldRowsOnlyAfterBuildSucceedsAndInsertsNewChunks() {
        whenOwnedTask();
        when(builder.build(any(AnalysisTask.class))).thenReturn(buildResult());
        when(chunkMapper.insert(any(CourseVideoChunk.class))).thenAnswer(invocation -> {
            CourseVideoChunk chunk = invocation.getArgument(0, CourseVideoChunk.class);
            chunk.setId((long) chunk.getChunkIndex() + 1L);
            return 1;
        });

        var response = service.rebuild("task_1", "Bearer demo");

        assertThat(response.taskId()).isEqualTo("task_1");
        assertThat(response.targetLanguage()).isEqualTo("zh-CN");
        assertThat(response.chunkCount()).isEqualTo(1);
        assertThat(response.buildVersion()).isEqualTo("VIDEO_CONTEXT_R1");
        verify(chunkMapper).deleteByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN");
        ArgumentCaptor<CourseVideoChunk> captor = ArgumentCaptor.forClass(CourseVideoChunk.class);
        verify(chunkMapper).insert(captor.capture());
        assertThat(captor.getValue().getSummary()).contains("语言模型");
        assertThat(captor.getValue().getEvidenceJson()).doesNotContain("object" + "Key");
    }

    @Test
    void rebuildFailurePreservesOldChunks() {
        whenOwnedTask();
        when(builder.build(any(AnalysisTask.class))).thenThrow(new IllegalStateException("builder failed"));

        assertThatThrownBy(() -> service.rebuild("task_1", "Bearer demo"))
            .isInstanceOf(IllegalStateException.class);

        verify(chunkMapper, never()).deleteByTaskIdUserIdAndTargetLanguage(any(), any(), any());
        verify(chunkMapper, never()).insert(any(CourseVideoChunk.class));
    }

    @Test
    void getReturnsPersistedChunksWithoutRebuilding() {
        whenOwnedTask();
        when(chunkMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN")).thenReturn(List.of(chunkRow()));
        when(builder.snapshot(any(AnalysisTask.class), anyList())).thenReturn(sourceSnapshot());

        var response = service.get("task_1", "Bearer demo");

        assertThat(response.taskId()).isEqualTo("task_1");
        assertThat(response.chunks()).hasSize(1);
        assertThat(response.chunks().getFirst().summary()).contains("语言模型");
        verify(builder, never()).build(any());
    }

    private void whenOwnedTask() {
        when(currentUserService.currentUser("Bearer demo"))
            .thenReturn(new CurrentUserResponse(42L, "u@example.com", "ACTIVE"));
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 42L)).thenReturn(task());
    }

    private static AnalysisTask task() {
        AnalysisTask task = new AnalysisTask();
        task.setId("task_1");
        task.setUserId(42L);
        task.setTargetLanguage("zh-CN");
        return task;
    }

    private static CourseVideoContextBuildResult buildResult() {
        return new CourseVideoContextBuildResult(
            "task_1",
            "zh-CN",
            240000L,
            240,
            "VIDEO_CONTEXT_R1",
            sourceSnapshot(),
            "全局总结",
            List.of("语言模型"),
            List.of(),
            List.of(new CourseVideoContextChunkResponse(
                0,
                0L,
                240000L,
                "00:00:00 - 00:04:00",
                "语言模型基础",
                List.of("语言模型"),
                "source preview",
                "translated preview",
                List.of(new CourseVideoContextEvidenceItem("SUBTITLE", 0, 0L, 60000L, "00:00:00 - 00:01:00", "source", "translated"))
            ))
        );
    }

    private static CourseVideoContextSourceSnapshot sourceSnapshot() {
        return new CourseVideoContextSourceSnapshot(
            1,
            1,
            0,
            1,
            true,
            true,
            LocalDateTime.ofInstant(FIXED_CLOCK.instant(), FIXED_CLOCK.getZone()),
            List.of(),
            "全局总结",
            List.of("语言模型")
        );
    }

    private static CourseVideoChunk chunkRow() {
        CourseVideoChunk chunk = new CourseVideoChunk();
        chunk.setTaskId("task_1");
        chunk.setUserId(42L);
        chunk.setTargetLanguage("zh-CN");
        chunk.setChunkIndex(0);
        chunk.setStartMillis(0L);
        chunk.setEndMillis(240000L);
        chunk.setTimeText("00:00:00 - 00:04:00");
        chunk.setSummary("语言模型基础");
        chunk.setKeywordsJson("[\"语言模型\"]");
        chunk.setEvidenceJson("[{\"sourceType\":\"SUBTITLE\",\"segmentIndex\":0,\"startMillis\":0,\"endMillis\":60000,\"timeText\":\"00:00:00 - 00:01:00\",\"textPreview\":\"source\",\"translatedPreview\":\"translated\"}]");
        chunk.setSourceTextPreview("source preview");
        chunk.setTranslatedTextPreview("translated preview");
        chunk.setBuildVersion("VIDEO_CONTEXT_R1");
        return chunk;
    }
}
