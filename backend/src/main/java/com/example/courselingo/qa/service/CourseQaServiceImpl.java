package com.example.courselingo.qa.service;

import com.example.courselingo.ai.llm.LlmProvider;
import com.example.courselingo.ai.llm.LlmRequest;
import com.example.courselingo.ai.llm.LlmResult;
import com.example.courselingo.ai.llm.LlmResponseFormat;
import com.example.courselingo.ai.llm.LlmUsage;
import com.example.courselingo.ai.record.domain.AiCallStage;
import com.example.courselingo.ai.record.domain.AiCallType;
import com.example.courselingo.ai.record.dto.AiCallRecordView;
import com.example.courselingo.ai.record.dto.CompleteAiCallRecordCommand;
import com.example.courselingo.ai.record.dto.FailAiCallRecordCommand;
import com.example.courselingo.ai.record.dto.StartAiCallRecordCommand;
import com.example.courselingo.ai.record.service.AiCallRecordSanitizer;
import com.example.courselingo.ai.record.service.AiCallRecordService;
import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.modelrouting.AiModelRoutedLlmRequestFactory;
import com.example.courselingo.modelrouting.AiModelStage;
import com.example.courselingo.qa.domain.CourseQaRecord;
import com.example.courselingo.qa.dto.CourseQaAskRequest;
import com.example.courselingo.qa.dto.CourseQaEvidenceItem;
import com.example.courselingo.qa.dto.CourseQaResponse;
import com.example.courselingo.qa.dto.CourseQaUsage;
import com.example.courselingo.qa.mapper.CourseQaRecordMapper;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Clock;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CourseQaServiceImpl implements CourseQaService {

    private final CurrentUserService currentUserService;
    private final AnalysisTaskMapper analysisTaskMapper;
    private final CourseQaEvidenceRetriever evidenceRetriever;
    private final CourseQaRecordMapper recordMapper;
    private final LlmProvider llmProvider;
    private final AiCallRecordService aiCallRecordService;
    private final CourseQaRateLimitService rateLimitService;
    private final Clock clock;
    private final CourseQaResponseParser parser;
    private final AiModelRoutedLlmRequestFactory routedRequestFactory;
    private final CourseQaProperties properties;
    private final ObjectMapper objectMapper;
    private final CourseQaEvidenceSanitizer evidenceSanitizer;
    private final AiCallRecordSanitizer sanitizer = new AiCallRecordSanitizer();

    public CourseQaServiceImpl(
        CurrentUserService currentUserService,
        AnalysisTaskMapper analysisTaskMapper,
        CourseQaEvidenceRetriever evidenceRetriever,
        CourseQaRecordMapper recordMapper,
        LlmProvider llmProvider,
        AiCallRecordService aiCallRecordService,
        CourseQaRateLimitService rateLimitService,
        Clock clock,
        CourseQaResponseParser parser,
        AiModelRoutedLlmRequestFactory routedRequestFactory
    ) {
        this(
            currentUserService,
            analysisTaskMapper,
            evidenceRetriever,
            recordMapper,
            llmProvider,
            aiCallRecordService,
            rateLimitService,
            clock,
            parser,
            routedRequestFactory,
            new CourseQaProperties(),
            new ObjectMapper(),
            new CourseQaEvidenceSanitizer()
        );
    }

    @Autowired
    public CourseQaServiceImpl(
        CurrentUserService currentUserService,
        AnalysisTaskMapper analysisTaskMapper,
        CourseQaEvidenceRetriever evidenceRetriever,
        CourseQaRecordMapper recordMapper,
        ObjectProvider<LlmProvider> llmProvider,
        AiCallRecordService aiCallRecordService,
        CourseQaRateLimitService rateLimitService,
        CourseQaResponseParser parser,
        AiModelRoutedLlmRequestFactory routedRequestFactory,
        CourseQaProperties properties,
        ObjectMapper objectMapper,
        CourseQaEvidenceSanitizer evidenceSanitizer
    ) {
        this(
            currentUserService,
            analysisTaskMapper,
            evidenceRetriever,
            recordMapper,
            llmProvider.getIfAvailable(),
            aiCallRecordService,
            rateLimitService,
            Clock.systemUTC(),
            parser,
            routedRequestFactory,
            properties,
            objectMapper,
            evidenceSanitizer
        );
    }

    private CourseQaServiceImpl(
        CurrentUserService currentUserService,
        AnalysisTaskMapper analysisTaskMapper,
        CourseQaEvidenceRetriever evidenceRetriever,
        CourseQaRecordMapper recordMapper,
        LlmProvider llmProvider,
        AiCallRecordService aiCallRecordService,
        CourseQaRateLimitService rateLimitService,
        Clock clock,
        CourseQaResponseParser parser,
        AiModelRoutedLlmRequestFactory routedRequestFactory,
        CourseQaProperties properties,
        ObjectMapper objectMapper,
        CourseQaEvidenceSanitizer evidenceSanitizer
    ) {
        this.currentUserService = currentUserService;
        this.analysisTaskMapper = analysisTaskMapper;
        this.evidenceRetriever = evidenceRetriever;
        this.recordMapper = recordMapper;
        this.llmProvider = llmProvider;
        this.aiCallRecordService = aiCallRecordService;
        this.rateLimitService = rateLimitService;
        this.clock = clock == null ? Clock.systemUTC() : clock;
        this.parser = parser == null ? new CourseQaResponseParser() : parser;
        this.routedRequestFactory = routedRequestFactory;
        this.properties = properties == null ? new CourseQaProperties() : properties;
        this.objectMapper = objectMapper == null ? new ObjectMapper() : objectMapper;
        this.evidenceSanitizer = evidenceSanitizer == null ? new CourseQaEvidenceSanitizer() : evidenceSanitizer;
    }

    @Override
    @Transactional
    public CourseQaResponse ask(String taskId, String authorizationHeader, CourseQaAskRequest request) {
        String normalizedTaskId = validateTaskId(taskId);
        String question = validateQuestion(request);
        CurrentUserResponse currentUser = currentUserService.currentUser(authorizationHeader);
        AnalysisTask task = analysisTaskMapper.selectByIdAndUserId(normalizedTaskId, currentUser.userId());
        if (task == null) {
            throw new BusinessException(ErrorCode.TASK_NOT_FOUND);
        }
        CourseQaRateLimitResult rateLimit = rateLimitService.checkAndConsume(currentUser.userId());
        if (!rateLimit.allowed()) {
            throw new BusinessException(ErrorCode.TASK_RATE_LIMITED, "Course QA rate limit exceeded");
        }
        List<CourseQaEvidenceItem> evidence = evidenceSanitizer.sanitize(evidenceRetriever.retrieve(
            normalizedTaskId,
            currentUser.userId(),
            task.getTargetLanguage(),
            question
        ));
        if (evidence.isEmpty()) {
            CourseQaRecord record = saveRecord(
                normalizedTaskId,
                currentUser.userId(),
                question,
                CourseQaMessages.INSUFFICIENT_EVIDENCE,
                evidence,
                "SUCCEEDED",
                null,
                null,
                null,
                null
            );
            return new CourseQaResponse(
                String.valueOf(record.getId()),
                CourseQaMessages.INSUFFICIENT_EVIDENCE,
                List.of(),
                null
            );
        }
        if (llmProvider == null) {
            saveRecord(
                normalizedTaskId,
                currentUser.userId(),
                question,
                CourseQaMessages.INSUFFICIENT_EVIDENCE,
                evidence,
                "FAILED",
                null,
                "AI_PROVIDER_FAILED",
                "Course QA provider is not configured",
                null
            );
            throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "Course QA provider is not configured");
        }

        AiCallRecordView started = startAiCall(normalizedTaskId, currentUser.userId(), evidence.size());
        try {
            LlmRequest requestForProvider = new LlmRequest(
                "qa_" + UUID.randomUUID(),
                normalizedTaskId,
                CourseQaPromptFactory.buildMessages(question, evidence),
                properties.getLlmTimeout(),
                0.0d,
                2048,
                1,
                Map.of("stage", AiModelStage.COURSE_QA.name(), "targetLanguage", task.getTargetLanguage()),
                LlmResponseFormat.JSON_OBJECT
            );
            LlmRequest routed = routedRequestFactory == null
                ? requestForProvider
                : routedRequestFactory.apply(AiModelStage.COURSE_QA, requestForProvider);
            LlmResult result = llmProvider.generate(routed);
            CourseQaResponseParser.ParsedCourseQaResponse parsed = parser.parse(result.content(), evidence.size());
            List<CourseQaEvidenceItem> cited = evidenceSanitizer.sanitize(citedEvidence(evidence, parsed.citedEvidenceIndexes()));
            String answer = cited.isEmpty() ? CourseQaMessages.INSUFFICIENT_EVIDENCE : parsed.answer();
            CourseQaUsage usage = usage(result);
            CourseQaRecord record = saveRecord(
                normalizedTaskId,
                currentUser.userId(),
                question,
                answer,
                cited,
                "SUCCEEDED",
                usage,
                null,
                null,
                null
            );
            completeAiCall(started, normalizedTaskId, currentUser.userId(), result, evidence.size(), answer.length());
            return new CourseQaResponse(String.valueOf(record.getId()), answer, cited, usage);
        } catch (RuntimeException exception) {
            failAiCall(started, normalizedTaskId, currentUser.userId(), exception);
            saveRecord(
                normalizedTaskId,
                currentUser.userId(),
                question,
                CourseQaMessages.INSUFFICIENT_EVIDENCE,
                evidence,
                "FAILED",
                null,
                "AI_PROVIDER_FAILED",
                sanitizer.sanitizeErrorMessage(exception.getMessage()),
                null
            );
            throw exception instanceof BusinessException
                ? exception
                : new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "Course QA provider failed");
        }
    }

    private CourseQaRecord saveRecord(
        String taskId,
        Long userId,
        String question,
        String answer,
        List<CourseQaEvidenceItem> evidence,
        String status,
        CourseQaUsage usage,
        String errorCode,
        String errorMessageSummary,
        String providerFallback
    ) {
        List<CourseQaEvidenceItem> safeEvidence = evidenceSanitizer.sanitize(evidence);
        CourseQaRecord record = new CourseQaRecord();
        record.setTaskId(taskId);
        record.setUserId(userId);
        record.setQuestion(question);
        record.setAnswer(answer);
        record.setEvidenceJson(toJson(safeEvidence));
        record.setStatus(status);
        record.setProvider(usage == null ? providerFallback : usage.provider());
        record.setModel(usage == null ? null : usage.model());
        record.setPromptTokens(usage == null ? null : usage.promptTokens());
        record.setCompletionTokens(usage == null ? null : usage.completionTokens());
        record.setTotalTokens(usage == null ? null : usage.totalTokens());
        record.setDurationMillis(usage == null ? null : usage.durationMillis());
        record.setErrorCode(errorCode);
        record.setErrorMessageSummary(errorMessageSummary);
        LocalDateTime now = LocalDateTime.ofInstant(clock.instant(), clock.getZone());
        record.setCreatedAt(now);
        record.setUpdatedAt(now);
        if (recordMapper.insert(record) != 1) {
            throw new BusinessException(ErrorCode.COMMON_INTERNAL_ERROR, "Course QA record insert failed");
        }
        return record;
    }

    private AiCallRecordView startAiCall(String taskId, Long userId, int inputUnits) {
        if (aiCallRecordService == null) {
            return null;
        }
        return aiCallRecordService.startCall(new StartAiCallRecordCommand(
            taskId,
            userId,
            AiCallType.LLM,
            AiCallStage.COURSE_QA,
            safeProviderName(),
            llmProvider.modelNameForDiagnostics(),
            null,
            inputUnits
        ));
    }

    private void completeAiCall(
        AiCallRecordView started,
        String taskId,
        Long userId,
        LlmResult result,
        int inputUnits,
        int outputUnits
    ) {
        if (started == null || started.id() == null) {
            return;
        }
        LlmUsage usage = result.usage();
        aiCallRecordService.completeCall(new CompleteAiCallRecordCommand(
            started.id(),
            taskId,
            userId,
            result.duration().toMillis(),
            usage.promptTokens(),
            usage.completionTokens(),
            usage.totalTokens(),
            inputUnits,
            outputUnits,
            null,
            null
        ));
    }

    private void failAiCall(AiCallRecordView started, String taskId, Long userId, RuntimeException exception) {
        if (started == null || started.id() == null) {
            return;
        }
        aiCallRecordService.failCall(new FailAiCallRecordCommand(
            started.id(),
            taskId,
            userId,
            null,
            exception instanceof BusinessException businessException ? businessException.errorCode().code() : "AI_PROVIDER_FAILED",
            sanitizer.sanitizeErrorMessage(exception.getMessage()),
            true,
            null,
            null
        ));
    }

    private CourseQaUsage usage(LlmResult result) {
        LlmUsage usage = result.usage();
        return new CourseQaUsage(
            result.provider(),
            result.model(),
            usage.promptTokens(),
            usage.completionTokens(),
            usage.totalTokens(),
            result.duration().toMillis()
        );
    }

    private List<CourseQaEvidenceItem> citedEvidence(List<CourseQaEvidenceItem> evidence, List<Integer> indexes) {
        return indexes.stream()
            .filter(index -> index >= 0 && index < evidence.size())
            .map(evidence::get)
            .toList();
    }

    private String toJson(List<CourseQaEvidenceItem> evidence) {
        try {
            return objectMapper.writeValueAsString(evidence == null ? List.of() : evidence);
        } catch (Exception ignored) {
            return "[]";
        }
    }

    private String safeProviderName() {
        String provider = llmProvider == null ? "" : llmProvider.providerName();
        String sanitized = sanitizer.sanitizeErrorMessage(provider);
        return sanitized == null || sanitized.isBlank() ? "llm" : sanitized.strip();
    }

    private String validateTaskId(String taskId) {
        if (taskId == null || taskId.isBlank()) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, "Task id is required");
        }
        return taskId.strip();
    }

    private String validateQuestion(CourseQaAskRequest request) {
        String question = request == null ? "" : request.question();
        if (question == null || question.isBlank()) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, "Question is required");
        }
        String cleaned = question.strip();
        if (cleaned.length() > properties.getQuestionMaxLength()) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, "Question is too long");
        }
        return cleaned;
    }
}
