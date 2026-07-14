package com.example.courselingo.chapter;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.ai.llm.LlmProvider;
import com.example.courselingo.ai.llm.LlmRequest;
import com.example.courselingo.ai.llm.LlmResult;
import com.example.courselingo.ai.llm.LlmUsage;
import com.example.courselingo.ai.record.domain.AiCallRecordStatus;
import com.example.courselingo.ai.record.domain.AiCallStage;
import com.example.courselingo.ai.record.domain.AiCallType;
import com.example.courselingo.ai.record.dto.AiCallRecordView;
import com.example.courselingo.ai.record.dto.CompleteAiCallRecordCommand;
import com.example.courselingo.ai.record.dto.FailAiCallRecordCommand;
import com.example.courselingo.ai.record.dto.StartAiCallRecordCommand;
import com.example.courselingo.ai.record.service.AiCallRecordService;
import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.chapter.domain.CourseChapter;
import com.example.courselingo.chapter.dto.CourseChapterEvidenceItem;
import com.example.courselingo.chapter.dto.CourseChapterResponse;
import com.example.courselingo.chapter.mapper.CourseChapterMapper;
import com.example.courselingo.chapter.service.CourseChapterEvidenceBuilder;
import com.example.courselingo.chapter.service.CourseChapterEvidenceBundle;
import com.example.courselingo.chapter.service.CourseChapterProperties;
import com.example.courselingo.chapter.service.CourseChapterResponseParser;
import com.example.courselingo.chapter.service.CourseChapterServiceImpl;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class CourseChapterServiceTest {

    private static final Clock FIXED_CLOCK = Clock.fixed(Instant.parse("2026-07-08T00:00:00Z"), ZoneOffset.UTC);

    @Mock
    private CurrentUserService currentUserService;

    @Mock
    private AnalysisTaskMapper analysisTaskMapper;

    @Mock
    private CourseChapterMapper chapterMapper;

    @Mock
    private CourseChapterEvidenceBuilder evidenceBuilder;

    @Mock
    private AiCallRecordService aiCallRecordService;

    private FakeLlmProvider llmProvider;
    private CourseChapterServiceImpl service;

    @BeforeEach
    void setUp() {
        llmProvider = new FakeLlmProvider();
        service = new CourseChapterServiceImpl(
            currentUserService,
            analysisTaskMapper,
            chapterMapper,
            evidenceBuilder,
            new CourseChapterResponseParser(),
            llmProvider,
            aiCallRecordService,
            null,
            new CourseChapterProperties(),
            new ObjectMapper(),
            FIXED_CLOCK
        );
    }

    @Test
    void listRejectsMissingOrNonOwnerTask() {
        when(currentUserService.currentUser("Bearer demo"))
            .thenReturn(new CurrentUserResponse(42L, "u@example.com", "ACTIVE"));
        when(analysisTaskMapper.selectByIdAndUserId("task_missing", 42L)).thenReturn(null);

        assertThatThrownBy(() -> service.list("task_missing", "Bearer demo"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_NOT_FOUND);

        verify(chapterMapper, never()).selectByTaskIdAndUserId(any(), any());
    }

    @Test
    void generateReturnsEmptyWithoutLlmWhenEvidenceIsEmpty() {
        whenOwnedTask();
        when(evidenceBuilder.build("task_1", 42L, "zh-CN")).thenReturn(new CourseChapterEvidenceBundle(List.of(), ""));

        List<CourseChapterResponse> response = service.generate("task_1", "Bearer demo");

        assertThat(response).isEmpty();
        assertThat(llmProvider.requests).isEmpty();
        verify(aiCallRecordService, never()).startCall(any());
        verify(chapterMapper, never()).deleteByTaskIdAndUserId(any(), any());
    }

    @Test
    void generatePersistsChaptersOverwritingOldRowsAndRecordsAiCall() {
        whenOwnedTask();
        List<CourseChapterEvidenceItem> evidence = List.of(
            new CourseChapterEvidenceItem(0, 0L, 240000L, "00:00:00 - 00:04:00", "本段语音原文：Intro to language models"),
            new CourseChapterEvidenceItem(1, 240000L, 480000L, "00:04:00 - 00:08:00", "本段语音原文：Training parameters")
        );
        when(evidenceBuilder.build("task_1", 42L, "zh-CN")).thenReturn(new CourseChapterEvidenceBundle(evidence, "课程总结"));
        when(aiCallRecordService.startCall(any(StartAiCallRecordCommand.class))).thenReturn(startedCall());
        when(chapterMapper.insert(any(CourseChapter.class))).thenAnswer(invocation -> {
            CourseChapter row = invocation.getArgument(0, CourseChapter.class);
            row.setId((long) row.getChapterIndex() + 1L);
            return 1;
        });
        llmProvider.content = """
            {"chapters":[
              {"title":"什么是大语言模型","summary":"介绍基本概念","startTimeMillis":0,"endTimeMillis":240000,"keywords":["语言模型"],"evidenceIndexes":[0]},
              {"title":"参数与训练","summary":"解释参数训练","startTimeMillis":240000,"endTimeMillis":480000,"keywords":["参数","训练"],"evidenceIndexes":[1,99]}
            ]}
            """;

        List<CourseChapterResponse> response = service.generate("task_1", "Bearer demo");

        assertThat(response).hasSize(2);
        assertThat(response.get(0).title()).isEqualTo("什么是大语言模型");
        assertThat(response.get(0).evidence()).extracting(CourseChapterEvidenceItem::index).containsExactly(0);
        assertThat(response.get(1).keywords()).containsExactly("参数", "训练");
        assertThat(llmProvider.requests).hasSize(1);
        assertThat(llmProvider.requests.getFirst().metadata()).containsEntry("stage", "COURSE_CHAPTER");
        assertThat(llmProvider.requests.getFirst().messages().getLast().content())
            .contains("本段语音原文")
            .doesNotContain("object" + "Key")
            .doesNotContain("raw" + "Prompt")
            .doesNotContain("token");
        verify(chapterMapper).deleteByTaskIdAndUserId("task_1", 42L);
        verify(aiCallRecordService).completeCall(any(CompleteAiCallRecordCommand.class));
        ArgumentCaptor<CourseChapter> rowCaptor = ArgumentCaptor.forClass(CourseChapter.class);
        verify(chapterMapper, org.mockito.Mockito.times(2)).insert(rowCaptor.capture());
        assertThat(rowCaptor.getAllValues().getFirst().getEvidenceJson()).doesNotContain("object" + "Key");
    }

    @Test
    void generatePersistsChapterTailClampedToEvidenceDuration() {
        long durationMillis = 4_090_265L;
        whenOwnedTask();
        when(evidenceBuilder.build("task_1", 42L, "zh-CN")).thenReturn(new CourseChapterEvidenceBundle(List.of(
            new CourseChapterEvidenceItem(
                0,
                4_080_000L,
                durationMillis,
                "01:08:00 - 01:08:10",
                "本段语音原文：课程结尾"
            )
        ), ""));
        when(aiCallRecordService.startCall(any(StartAiCallRecordCommand.class))).thenReturn(startedCall());
        when(chapterMapper.insert(any(CourseChapter.class))).thenAnswer(invocation -> {
            invocation.getArgument(0, CourseChapter.class).setId(1L);
            return 1;
        });
        llmProvider.content = """
            {"chapters":[
              {"title":"最后一章","summary":"课程结尾","startTimeMillis":4080000,"endTimeMillis":4140000,"keywords":["结尾"],"evidenceIndexes":[0]}
            ]}
            """;

        List<CourseChapterResponse> response = service.generate("task_1", "Bearer demo");

        assertThat(response).singleElement().satisfies(chapter -> {
            assertThat(chapter.startTimeMillis()).isEqualTo(4_080_000L);
            assertThat(chapter.endTimeMillis()).isEqualTo(durationMillis);
        });
        ArgumentCaptor<CourseChapter> captor = ArgumentCaptor.forClass(CourseChapter.class);
        verify(chapterMapper).insert(captor.capture());
        assertThat(captor.getValue().getEndMillis()).isEqualTo(durationMillis);
    }

    @Test
    void generateRecordsAiFailureAndKeepsExistingRowsWhenJsonCannotBeParsed() {
        whenOwnedTask();
        when(evidenceBuilder.build("task_1", 42L, "zh-CN")).thenReturn(new CourseChapterEvidenceBundle(List.of(
            new CourseChapterEvidenceItem(0, 0L, 240000L, "00:00:00 - 00:04:00", "本段语音原文：Intro")
        ), ""));
        when(aiCallRecordService.startCall(any(StartAiCallRecordCommand.class))).thenReturn(startedCall());
        llmProvider.content = "not-json";

        assertThatThrownBy(() -> service.generate("task_1", "Bearer demo"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AI_PROVIDER_FAILED);

        verify(chapterMapper, never()).deleteByTaskIdAndUserId(any(), any());
        verify(aiCallRecordService).failCall(any(FailAiCallRecordCommand.class));
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
        task.setStatus("SUCCEEDED");
        return task;
    }

    private static AiCallRecordView startedCall() {
        LocalDateTime now = LocalDateTime.ofInstant(FIXED_CLOCK.instant(), FIXED_CLOCK.getZone());
        return new AiCallRecordView(
            1L,
            "task_1",
            AiCallType.LLM,
            AiCallStage.COURSE_CHAPTER,
            "fake",
            "fake-model",
            AiCallRecordStatus.STARTED,
            now,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            now,
            now
        );
    }

    private static final class FakeLlmProvider implements LlmProvider {
        private final List<LlmRequest> requests = new ArrayList<>();
        private String content = "{\"chapters\":[]}";

        @Override
        public LlmResult generate(LlmRequest request) {
            requests.add(request);
            return new LlmResult(
                "fake",
                "fake-model",
                content,
                "stop",
                new LlmUsage(10, 20, 30),
                Duration.ofMillis(123),
                Map.of()
            );
        }

        @Override
        public String providerName() {
            return "fake";
        }

        @Override
        public String modelNameForDiagnostics() {
            return "fake-model";
        }
    }
}
