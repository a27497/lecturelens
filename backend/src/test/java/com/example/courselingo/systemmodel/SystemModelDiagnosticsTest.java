package com.example.courselingo.systemmodel;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.ai.llm.OpenAiCompatibleClientResponse;
import com.example.courselingo.ai.llm.OpenAiCompatibleLlmClient;
import com.example.courselingo.ai.record.domain.AiCallRecord;
import com.example.courselingo.ai.record.domain.AiCallStage;
import com.example.courselingo.ai.record.domain.AiCallType;
import com.example.courselingo.ai.record.dto.StartAiCallRecordCommand;
import com.example.courselingo.ai.record.mapper.AiCallRecordMapper;
import com.example.courselingo.ai.record.service.AiCallRecordSanitizer;
import com.example.courselingo.ai.record.service.AiCallRecordServiceImpl;
import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.chapter.domain.CourseChapter;
import com.example.courselingo.chapter.dto.CourseChapterEvidenceItem;
import com.example.courselingo.chapter.mapper.CourseChapterMapper;
import com.example.courselingo.chapter.service.*;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.modelrouting.AiModelRoutedLlmRequestFactory;
import com.example.courselingo.qa.domain.CourseQaRecord;
import com.example.courselingo.qa.dto.CourseQaAskRequest;
import com.example.courselingo.qa.dto.CourseQaEvidenceItem;
import com.example.courselingo.qa.mapper.CourseQaRecordMapper;
import com.example.courselingo.qa.service.*;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.InetAddress;
import java.time.Clock;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;
import org.junit.jupiter.params.provider.ValueSource;

class SystemModelDiagnosticsTest {
    private final AiCallRecordMapper calls = mock(AiCallRecordMapper.class);
    private final AiCallRecordServiceImpl records =
        new AiCallRecordServiceImpl(calls, Clock.systemUTC(), new AiCallRecordSanitizer());

    @ParameterizedTest
    @EnumSource(value = AiCallStage.class, names = {"COURSE_QA", "COURSE_CHAPTER"})
    void routedServicesStartRealCallRecordBeforeUsingFrozenModel(AiCallStage stage) throws Exception {
        var user = mock(CurrentUserService.class);
        var tasks = mock(AnalysisTaskMapper.class);
        var executions = mock(SystemModelExecutionService.class);
        var transport = mock(OpenAiCompatibleLlmClient.class);
        var addresses = new SystemModelUrlPolicy(host ->
            new InetAddress[] {InetAddress.getByAddress(new byte[] {8, 8, 8, 8})});
        var provider = new SystemModelLlmProvider(executions, transport, addresses, transport);
        var execution = new SystemModelExecutionRef("snapshot-test", 1, "task_1", 42);
        var route = new SystemModelResolvedRoute(stage.name(), "DATABASE", SystemModelProtocol.OPENAI_CHAT,
            "test-credential", 1L, 1L, "https://model.example/v1", "test-routed-model",
            Set.of("JSON_OUTPUT"), null, null, null, null, true, "test");
        when(user.currentUser("Bearer test"))
            .thenReturn(new CurrentUserResponse(42L, "test@example.com", "ACTIVE"));
        var task = new AnalysisTask();
        task.setId("task_1");
        task.setUserId(42L);
        task.setTargetLanguage("zh-CN");
        task.setStatus("SUCCEEDED");
        when(tasks.selectByIdAndUserId("task_1", 42L)).thenReturn(task);
        when(executions.operation("task_1", 42L, stage.name())).thenReturn(execution);
        when(executions.route(execution, stage.name())).thenReturn(route);
        when(executions.credential(execution, stage.name())).thenReturn("synthetic-test-key");

        // Keep the real start/complete validators; only persistence and transport are synthetic.
        var started = new AiCallRecord[1];
        when(calls.insert(any(AiCallRecord.class))).thenAnswer(invocation -> {
            started[0] = invocation.getArgument(0);
            started[0].setId(100L);
            assertThat(started[0].getModel()).isNull();
            assertThat(started[0].getStage()).isEqualTo(stage.name());
            assertThat(started[0].getStatus()).isEqualTo("STARTED");
            return 1;
        });
        when(calls.selectByIdTaskIdAndUserId(100L, "task_1", 42L))
            .thenAnswer(invocation -> started[0]);
        when(calls.updateByIdTaskIdAndUserId(any(AiCallRecord.class), eq(100L), eq("task_1"), eq(42L)))
            .thenReturn(1);
        String content = stage == AiCallStage.COURSE_QA
            ? "{\"answer\":\"课程介绍变量\",\"citedEvidenceIndexes\":[0]}"
            : """
                {"chapters":[{"title":"变量","summary":"变量介绍","startTimeMillis":0,
                "endTimeMillis":240000,"keywords":["变量"],"evidenceIndexes":[0]}]}
                """;
        String body = new ObjectMapper().writeValueAsString(Map.of("choices", List.of(
            Map.of("finish_reason", "stop", "message", Map.of("content", content)))));
        when(transport.complete(any())).thenAnswer(invocation -> {
            assertThat(started[0]).isNotNull();
            return new OpenAiCompatibleClientResponse(200, body, Map.of(), Duration.ZERO);
        });

        var requestFactory = new AiModelRoutedLlmRequestFactory(null, executions);
        if (stage == AiCallStage.COURSE_QA) {
            var evidence = mock(CourseQaEvidenceRetriever.class);
            var answers = mock(CourseQaRecordMapper.class);
            var limits = mock(CourseQaRateLimitService.class);
            when(limits.checkAndConsume(42L)).thenReturn(CourseQaRateLimitResult.allowed(10, 9));
            when(evidence.retrieve("task_1", 42L, "zh-CN", "解释变量"))
                .thenReturn(List.of(new CourseQaEvidenceItem("SUBTITLE", "1", 0L, 240000L,
                    "00:00 - 04:00", "课程介绍变量", "课程介绍变量", 1.0)));
            when(answers.insert(any(CourseQaRecord.class))).thenAnswer(invocation -> {
                invocation.getArgument(0, CourseQaRecord.class).setId(1L);
                return 1;
            });
            var service = new CourseQaServiceImpl(user, tasks, evidence, answers, provider, records,
                limits, Clock.systemUTC(), new CourseQaResponseParser(), requestFactory);
            service.configureSystemModels(executions);
            var response = service.ask("task_1", "Bearer test", new CourseQaAskRequest("解释变量"));
            assertThat(response.answer()).isEqualTo("课程介绍变量");
            assertThat(response.usage().model()).isEqualTo("test-routed-model");
        } else {
            var evidence = mock(CourseChapterEvidenceBuilder.class);
            var chapters = mock(CourseChapterMapper.class);
            when(evidence.build("task_1", 42L, "zh-CN"))
                .thenReturn(new CourseChapterEvidenceBundle(List.of(new CourseChapterEvidenceItem(
                    0, 0L, 240000L, "00:00 - 04:00", "课程介绍变量")), ""));
            when(chapters.insert(any(CourseChapter.class))).thenAnswer(invocation -> {
                invocation.getArgument(0, CourseChapter.class).setId(1L);
                return 1;
            });
            var service = new CourseChapterServiceImpl(user, tasks, chapters, evidence,
                new CourseChapterResponseParser(), provider, records, requestFactory, new CourseChapterProperties(),
                new ObjectMapper(), Clock.systemUTC());
            service.configureSystemModels(executions);
            var response = service.generate("task_1", "Bearer test");
            assertThat(response).singleElement().satisfies(chapter -> {
                assertThat(chapter.title()).isEqualTo("变量");
                assertThat(chapter.usage().model()).isEqualTo("test-routed-model");
            });
        }
        verify(calls).insert(any(AiCallRecord.class));
        verify(transport).complete(any());
        assertThat(started[0].getStatus()).isEqualTo("SUCCEEDED");
        assertThat(provider.modelNameForDiagnostics()).isNull();
    }

    @ParameterizedTest
    @EnumSource(value = AiCallStage.class, names = {"COURSE_QA", "COURSE_CHAPTER"})
    void startCallAcceptsUnknownModelWithoutInventingName(AiCallStage stage) {
        when(calls.insert(any(AiCallRecord.class))).thenAnswer(invocation -> {
            invocation.getArgument(0, AiCallRecord.class).setId(100L);
            return 1;
        });
        var view = records.startCall(new StartAiCallRecordCommand("task_1", 42L, AiCallType.LLM,
            stage, "system-model-router", null, null, 1));
        assertThat(view.model()).isNull();
        verify(calls).insert(any(AiCallRecord.class));
    }

    @ParameterizedTest
    @ValueSource(strings = {"", " ", "\t\n"})
    void startCallStillRejectsBlankModelBeforePersistence(String model) {
        assertThatThrownBy(() -> records.startCall(new StartAiCallRecordCommand("task_1", 42L,
            AiCallType.LLM, AiCallStage.COURSE_QA, "system-model-router", model, null, 1)))
            .isInstanceOfSatisfying(BusinessException.class,
                failure -> assertThat(failure.errorCode()).isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED));
        verify(calls, never()).insert(any(AiCallRecord.class));
    }
}
