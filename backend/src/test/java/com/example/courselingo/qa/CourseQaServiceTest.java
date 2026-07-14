package com.example.courselingo.qa;

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
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.qa.domain.CourseQaRecord;
import com.example.courselingo.qa.dto.CourseQaAskRequest;
import com.example.courselingo.qa.dto.CourseQaEvidenceItem;
import com.example.courselingo.qa.dto.CourseQaResponse;
import com.example.courselingo.qa.mapper.CourseQaRecordMapper;
import com.example.courselingo.qa.service.CourseQaEvidenceRetriever;
import com.example.courselingo.qa.service.CourseQaRateLimitResult;
import com.example.courselingo.qa.service.CourseQaRateLimitService;
import com.example.courselingo.qa.service.CourseQaResponseParser;
import com.example.courselingo.qa.service.CourseQaServiceImpl;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
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
class CourseQaServiceTest {

    private static final Clock FIXED_CLOCK = Clock.fixed(Instant.parse("2026-07-07T00:00:00Z"), ZoneOffset.UTC);

    @Mock
    private CurrentUserService currentUserService;

    @Mock
    private AnalysisTaskMapper analysisTaskMapper;

    @Mock
    private CourseQaEvidenceRetriever evidenceRetriever;

    @Mock
    private CourseQaRecordMapper recordMapper;

    @Mock
    private AiCallRecordService aiCallRecordService;

    @Mock
    private CourseQaRateLimitService rateLimitService;

    private FakeLlmProvider llmProvider;
    private CourseQaServiceImpl service;

    @BeforeEach
    void setUp() {
        llmProvider = new FakeLlmProvider();
        service = new CourseQaServiceImpl(
            currentUserService,
            analysisTaskMapper,
            evidenceRetriever,
            recordMapper,
            llmProvider,
            aiCallRecordService,
            rateLimitService,
            FIXED_CLOCK,
            new CourseQaResponseParser(),
            null
        );
    }

    @Test
    void askRejectsMissingOrNonOwnerTaskBeforeEvidenceAndLlm() {
        when(currentUserService.currentUser("Bearer demo"))
            .thenReturn(new CurrentUserResponse(42L, "u@example.com", "ACTIVE"));
        when(analysisTaskMapper.selectByIdAndUserId("task_missing", 42L)).thenReturn(null);

        assertThatThrownBy(() -> service.ask("task_missing", "Bearer demo", new CourseQaAskRequest("hello")))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_NOT_FOUND);

        verify(evidenceRetriever, never()).retrieve(any(), any(), any(), any());
        assertThat(llmProvider.requests).isEmpty();
    }

    @Test
    void askReturnsInsufficientEvidenceWithoutCallingLlm() {
        when(currentUserService.currentUser("Bearer demo"))
            .thenReturn(new CurrentUserResponse(42L, "u@example.com", "ACTIVE"));
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 42L)).thenReturn(task());
        when(rateLimitService.checkAndConsume(42L)).thenReturn(CourseQaRateLimitResult.allowed(10, 9));
        when(evidenceRetriever.retrieve("task_1", 42L, "zh-CN", "unknown")).thenReturn(List.of());
        when(recordMapper.insert(any(CourseQaRecord.class))).thenAnswer(invocation -> {
            invocation.getArgument(0, CourseQaRecord.class).setId(100L);
            return 1;
        });

        CourseQaResponse response = service.ask("task_1", "Bearer demo", new CourseQaAskRequest("unknown"));

        assertThat(response.recordId()).isEqualTo("100");
        assertThat(response.answer()).isEqualTo("当前课程内容中没有找到明确依据");
        assertThat(response.answer()).isEqualTo(response.answer().strip());
        assertThat(response.answer()).doesNotContain("\r", "\n", "。", ".");
        assertThat(response.answer().codePoints().toArray())
            .containsExactly("当前课程内容中没有找到明确依据".codePoints().toArray());
        assertThat(response.evidence()).isEmpty();
        assertThat(response.usage()).isNull();
        assertThat(llmProvider.requests).isEmpty();
        verify(aiCallRecordService, never()).startCall(any(StartAiCallRecordCommand.class));
        ArgumentCaptor<CourseQaRecord> recordCaptor = ArgumentCaptor.forClass(CourseQaRecord.class);
        verify(recordMapper).insert(recordCaptor.capture());
        assertThat(recordCaptor.getValue().getEvidenceJson()).isEqualTo("[]");
    }

    @Test
    void askReturnsControlledRefusalWithoutEvidenceWhenModelCitesNothing() {
        when(currentUserService.currentUser("Bearer demo"))
            .thenReturn(new CurrentUserResponse(42L, "u@example.com", "ACTIVE"));
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 42L)).thenReturn(task());
        when(rateLimitService.checkAndConsume(42L)).thenReturn(CourseQaRateLimitResult.allowed(10, 9));
        when(evidenceRetriever.retrieve("task_1", 42L, "zh-CN", "where OpenCL"))
            .thenReturn(List.of(evidence()));
        when(recordMapper.insert(any(CourseQaRecord.class))).thenAnswer(invocation -> {
            invocation.getArgument(0, CourseQaRecord.class).setId(103L);
            return 1;
        });
        when(aiCallRecordService.startCall(any(StartAiCallRecordCommand.class))).thenReturn(startedCall());
        llmProvider.content = "{\"answer\":\"unsupported\",\"citedEvidenceIndexes\":[]}";

        CourseQaResponse response = service.ask("task_1", "Bearer demo", new CourseQaAskRequest("where OpenCL"));

        assertThat(response.answer()).isEqualTo("当前课程内容中没有找到明确依据");
        assertThat(response.evidence()).isEmpty();
        assertThat(llmProvider.requests).hasSize(1);
        verify(aiCallRecordService).completeCall(any(CompleteAiCallRecordCommand.class));
        ArgumentCaptor<CourseQaRecord> recordCaptor = ArgumentCaptor.forClass(CourseQaRecord.class);
        verify(recordMapper).insert(recordCaptor.capture());
        assertThat(recordCaptor.getValue().getEvidenceJson()).isEqualTo("[]");
    }

    @Test
    void askReturnsControlledRefusalWithoutEvidenceWhenAllCitationsAreInvalid() {
        when(currentUserService.currentUser("Bearer demo"))
            .thenReturn(new CurrentUserResponse(42L, "u@example.com", "ACTIVE"));
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 42L)).thenReturn(task());
        when(rateLimitService.checkAndConsume(42L)).thenReturn(CourseQaRateLimitResult.allowed(10, 9));
        when(evidenceRetriever.retrieve("task_1", 42L, "zh-CN", "where OpenCL"))
            .thenReturn(List.of(evidence()));
        when(recordMapper.insert(any(CourseQaRecord.class))).thenAnswer(invocation -> {
            invocation.getArgument(0, CourseQaRecord.class).setId(104L);
            return 1;
        });
        when(aiCallRecordService.startCall(any(StartAiCallRecordCommand.class))).thenReturn(startedCall());
        llmProvider.content = "{\"answer\":\"unsupported\",\"citedEvidenceIndexes\":[99]}";

        CourseQaResponse response = service.ask("task_1", "Bearer demo", new CourseQaAskRequest("where OpenCL"));

        assertThat(response.answer()).isEqualTo("当前课程内容中没有找到明确依据");
        assertThat(response.evidence()).isEmpty();
        assertThat(llmProvider.requests).hasSize(1);
        verify(aiCallRecordService).completeCall(any(CompleteAiCallRecordCommand.class));
        ArgumentCaptor<CourseQaRecord> recordCaptor = ArgumentCaptor.forClass(CourseQaRecord.class);
        verify(recordMapper).insert(recordCaptor.capture());
        assertThat(recordCaptor.getValue().getEvidenceJson()).isEqualTo("[]");
    }

    @Test
    void askCallsLlmRecordsQaAndAiCall() {
        when(currentUserService.currentUser("Bearer demo"))
            .thenReturn(new CurrentUserResponse(42L, "u@example.com", "ACTIVE"));
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 42L)).thenReturn(task());
        when(rateLimitService.checkAndConsume(42L)).thenReturn(CourseQaRateLimitResult.allowed(10, 9));
        CourseQaEvidenceItem evidence = evidence();
        when(evidenceRetriever.retrieve("task_1", 42L, "zh-CN", "where OpenCL")).thenReturn(List.of(evidence));
        when(recordMapper.insert(any(CourseQaRecord.class))).thenAnswer(invocation -> {
            invocation.getArgument(0, CourseQaRecord.class).setId(101L);
            return 1;
        });
        when(aiCallRecordService.startCall(any(StartAiCallRecordCommand.class))).thenReturn(startedCall());
        llmProvider.content = "{\"answer\":\"OpenCL is discussed near 00:03:00.\",\"citedEvidenceIndexes\":[0]}";

        CourseQaResponse response = service.ask("task_1", "Bearer demo", new CourseQaAskRequest("where OpenCL"));

        assertThat(response.recordId()).isEqualTo("101");
        assertThat(response.answer()).contains("OpenCL");
        assertThat(response.evidence()).containsExactly(evidence);
        assertThat(response.usage().totalTokens()).isEqualTo(30);
        assertThat(llmProvider.requests).hasSize(1);
        assertThat(llmProvider.requests.getFirst().metadata()).containsEntry("stage", "COURSE_QA");
        verify(aiCallRecordService).completeCall(any(CompleteAiCallRecordCommand.class));
    }

    @Test
    void askSanitizesEvidenceBeforePromptResponseAndRecord() {
        when(currentUserService.currentUser("Bearer demo"))
            .thenReturn(new CurrentUserResponse(42L, "u@example.com", "ACTIVE"));
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 42L)).thenReturn(task());
        when(rateLimitService.checkAndConsume(42L)).thenReturn(CourseQaRateLimitResult.allowed(10, 9));
        CourseQaEvidenceItem dirtyVideoSegment = new CourseQaEvidenceItem(
            "VIDEO_SEGMENT",
            "10",
            180000L,
            240000L,
            "00:03:00 - 00:04:00",
            "本段主要讲解：Whatever the user types in becomes input tokens；画面文字包括：{emcee ade hl ey ra Alans ei so wt rr asia ?",
            "",
            0.9d
        );
        CourseQaEvidenceItem dirtyOcr = new CourseQaEvidenceItem(
            "OCR",
            "11",
            180000L,
            240000L,
            "00:03:00 - 00:04:00",
            "Parameter / Weight: ie ot me It was the best Sr of times",
            "",
            0.9d
        );
        CourseQaEvidenceItem reliableOcrOnly = new CourseQaEvidenceItem(
            "OCR",
            "12",
            180000L,
            240000L,
            "00:03:00 - 00:04:00",
            "Large Language Models for the curious beginner",
            "",
            0.95d
        );
        when(evidenceRetriever.retrieve("task_1", 42L, "zh-CN", "knowledge points"))
            .thenReturn(List.of(dirtyVideoSegment, dirtyOcr, reliableOcrOnly));
        when(recordMapper.insert(any(CourseQaRecord.class))).thenAnswer(invocation -> {
            invocation.getArgument(0, CourseQaRecord.class).setId(102L);
            return 1;
        });
        when(aiCallRecordService.startCall(any(StartAiCallRecordCommand.class))).thenReturn(startedCall());
        llmProvider.content = "{\"answer\":\"The lesson explains input tokens.\",\"citedEvidenceIndexes\":[0]}";

        CourseQaResponse response = service.ask("task_1", "Bearer demo", new CourseQaAskRequest("knowledge points"));

        assertThat(response.evidence()).hasSize(1);
        assertThat(response.evidence().getFirst().snippet())
            .contains("本段语音原文：Whatever the user types in becomes input tokens")
            .doesNotContain("本段主要讲解")
            .doesNotContain("画面文字包括")
            .doesNotContain("Large Language Models for the curious beginner")
            .doesNotContain("{emcee")
            .doesNotContain("ie ot");
        String prompt = llmProvider.requests.getFirst().messages().getLast().content();
        assertThat(prompt)
            .contains("本段语音原文：Whatever the user types in becomes input tokens")
            .doesNotContain("本段主要讲解")
            .doesNotContain("画面文字包括")
            .doesNotContain("Large Language Models for the curious beginner")
            .doesNotContain("{emcee")
            .doesNotContain("ie ot");
        ArgumentCaptor<CourseQaRecord> recordCaptor = ArgumentCaptor.forClass(CourseQaRecord.class);
        verify(recordMapper).insert(recordCaptor.capture());
        assertThat(recordCaptor.getValue().getEvidenceJson())
            .contains("本段语音原文")
            .doesNotContain("本段主要讲解")
            .doesNotContain("画面文字包括")
            .doesNotContain("Large Language Models for the curious beginner")
            .doesNotContain("{emcee")
            .doesNotContain("ie ot");
    }

    @Test
    void askStopsOnRateLimitBeforeEvidenceAndLlm() {
        when(currentUserService.currentUser("Bearer demo"))
            .thenReturn(new CurrentUserResponse(42L, "u@example.com", "ACTIVE"));
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 42L)).thenReturn(task());
        when(rateLimitService.checkAndConsume(42L)).thenReturn(CourseQaRateLimitResult.blocked(10, 60));

        assertThatThrownBy(() -> service.ask("task_1", "Bearer demo", new CourseQaAskRequest("hello")))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_RATE_LIMITED);

        verify(evidenceRetriever, never()).retrieve(any(), any(), any(), any());
        assertThat(llmProvider.requests).isEmpty();
    }

    @Test
    void askRecordsFailureWhenLlmJsonCannotBeParsed() {
        when(currentUserService.currentUser("Bearer demo"))
            .thenReturn(new CurrentUserResponse(42L, "u@example.com", "ACTIVE"));
        when(analysisTaskMapper.selectByIdAndUserId("task_1", 42L)).thenReturn(task());
        when(rateLimitService.checkAndConsume(42L)).thenReturn(CourseQaRateLimitResult.allowed(10, 9));
        when(evidenceRetriever.retrieve("task_1", 42L, "zh-CN", "where OpenCL")).thenReturn(List.of(evidence()));
        when(recordMapper.insert(any(CourseQaRecord.class))).thenReturn(1);
        when(aiCallRecordService.startCall(any(StartAiCallRecordCommand.class))).thenReturn(startedCall());
        llmProvider.content = "not-json";

        assertThatThrownBy(() -> service.ask("task_1", "Bearer demo", new CourseQaAskRequest("where OpenCL")))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AI_PROVIDER_FAILED);

        verify(aiCallRecordService).failCall(any(FailAiCallRecordCommand.class));
    }

    private static AnalysisTask task() {
        AnalysisTask task = new AnalysisTask();
        task.setId("task_1");
        task.setUserId(42L);
        task.setTargetLanguage("zh-CN");
        task.setStatus("SUCCEEDED");
        return task;
    }

    private static CourseQaEvidenceItem evidence() {
        return new CourseQaEvidenceItem(
            "VIDEO_SEGMENT",
            "10",
            180000L,
            240000L,
            "00:03:00 - 00:04:00",
            "OpenCL gateway explanation",
            "OpenCL gateway summary",
            0.9d
        );
    }

    private static AiCallRecordView startedCall() {
        LocalDateTime now = LocalDateTime.ofInstant(FIXED_CLOCK.instant(), FIXED_CLOCK.getZone());
        return new AiCallRecordView(
            1L,
            "task_1",
            AiCallType.LLM,
            AiCallStage.COURSE_QA,
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
        private String content = "{\"answer\":\"ok\",\"citedEvidenceIndexes\":[0]}";

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
