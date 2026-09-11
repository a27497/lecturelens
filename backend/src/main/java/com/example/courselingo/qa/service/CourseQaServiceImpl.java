package com.example.courselingo.qa.service;

import com.example.courselingo.ai.llm.LlmProvider;
import com.example.courselingo.ai.llm.LlmProviderFailureCategory;
import com.example.courselingo.ai.llm.LlmProviderFailureDetails;
import com.example.courselingo.ai.llm.LlmRequest;
import com.example.courselingo.ai.llm.LlmResult;
import com.example.courselingo.ai.llm.LlmResponseFormat;
import com.example.courselingo.ai.llm.LlmStageException;
import com.example.courselingo.ai.llm.LlmStructuredOutputExecutor;
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
import com.example.courselingo.common.logging.SafeLogSanitizer;
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
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.annotation.Propagation;
import com.example.courselingo.task.service.GenerationFence;

@Service
public class CourseQaServiceImpl implements CourseQaService {

    private GenerationFence generationFence;

    @Autowired
    public void configureGenerationFence(GenerationFence generationFence) {
        this.generationFence = generationFence;
    }


    private static final Logger log = LoggerFactory.getLogger(CourseQaServiceImpl.class);
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
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    public CourseQaResponse ask(String taskId, String authorizationHeader, CourseQaAskRequest request) {
        String normalizedTaskId = validateTaskId(taskId);
        String question = validateQuestion(request);
        CurrentUserResponse currentUser = currentUserService.currentUser(authorizationHeader);
        AnalysisTask task = analysisTaskMapper.selectByIdAndUserId(normalizedTaskId, currentUser.userId());
        if (task == null) {
            throw new BusinessException(ErrorCode.TASK_NOT_FOUND);
        }
        GenerationFence.Ticket ticket = generationFence == null ? null
            : generationFence.begin(normalizedTaskId, currentUser.userId(), null);
        CourseQaRateLimitResult rateLimit = rateLimitService.checkAndConsume(currentUser.userId());
        if (!rateLimit.allowed()) {
            throw new BusinessException(ErrorCode.TASK_RATE_LIMITED, "Course QA rate limit exceeded");
        }
        List<CourseQaEvidenceItem> evidence = evidenceSanitizer.sanitize(evidenceRetriever.retrieve(
            normalizedTaskId,
            currentUser.userId(),
            task.getTargetLanguage(),
            question
        )).stream()
            .distinct()
            .limit(properties.getMaxEvidenceItems())
            .toList();
        if (evidence.isEmpty()) {
            CourseQaRecord record = saveRecord(ticket,
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
            saveRecord(ticket,
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
        long startedNanos = System.nanoTime();
        try {
            var prepared = CourseQaPromptFactory.prepare(
                question,
                evidence,
                properties.getMaxPromptChars(),
                properties.getMaxSnippetChars()
            );
            var messages = prepared.messages();
            var visibleEvidence = prepared.evidence();
            int promptChars = CourseQaPromptFactory.promptChars(messages);
            LlmRequest requestForProvider = new LlmRequest(
                "qa_" + UUID.randomUUID(),
                normalizedTaskId,
                messages,
                properties.getLlmTimeout(),
                0.0d,
                properties.getMaxTokens(),
                properties.getMaxAttempts(),
                Map.of("stage", AiModelStage.COURSE_QA.name(), "targetLanguage", task.getTargetLanguage()),
                LlmResponseFormat.JSON_OBJECT
            );
            LlmRequest routed = routedRequestFactory == null
                ? requestForProvider
                : routedRequestFactory.apply(AiModelStage.COURSE_QA, requestForProvider);
            LlmResult result = LlmStructuredOutputExecutor.execute(llmProvider, routed);
            CourseQaResponseParser.ParsedCourseQaResponse parsed = parser.parse(result.content(), visibleEvidence.size());
            List<CourseQaEvidenceItem> cited = evidenceSanitizer.sanitize(citedEvidence(visibleEvidence, parsed.citedEvidenceIndexes()));
            String answer = cited.isEmpty() ? CourseQaMessages.INSUFFICIENT_EVIDENCE : parsed.answer();
            CourseQaUsage usage = usage(result);
            CourseQaRecord record = saveRecord(ticket,
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
            log.info(
                "event=course_qa_completed taskId={} evidenceCount={} promptChars={} providerDurationMillis={} totalDurationMillis={}",
                SafeLogSanitizer.sanitize(normalizedTaskId),
                evidence.size(),
                promptChars,
                result.duration().toMillis(),
                elapsedMillis(startedNanos)
            );
            return new CourseQaResponse(String.valueOf(record.getId()), answer, cited, usage);
        } catch (RuntimeException exception) {
            LlmStageException safeFailure = toStageFailure(exception);
            failAiCall(started, normalizedTaskId, currentUser.userId(), safeFailure, elapsedMillis(startedNanos));
            saveRecord(ticket,
                normalizedTaskId,
                currentUser.userId(),
                question,
                CourseQaMessages.INSUFFICIENT_EVIDENCE,
                evidence,
                "FAILED",
                null,
                safeFailure.apiDetails().errorCode(),
                safeFailure.safeDiagnosticSummary(),
                null
            );
            log.warn(
                "event=course_qa_failed taskId={} evidenceCount={} totalDurationMillis={} errorCode={}",
                SafeLogSanitizer.sanitize(normalizedTaskId),
                evidence.size(),
                elapsedMillis(startedNanos),
                safeFailure.apiDetails().errorCode()
            );
            if (exception instanceof BusinessException business
                && (business.errorCode() == ErrorCode.TASK_INVALID_STATUS || business.errorCode() == ErrorCode.TASK_NOT_FOUND)) {
                throw business;
            }
            throw safeFailure;
        }
    }

    private static LlmStageException toStageFailure(RuntimeException exception) {
        if (exception instanceof LlmStageException stageException) {
            return stageException;
        }
        if (exception instanceof BusinessException && exception.getCause() == null) {
            return new LlmStageException(
                AiModelStage.COURSE_QA.name(),
                new LlmProviderFailureDetails(LlmProviderFailureCategory.OUTPUT_INVALID, null, null, false),
                exception
            );
        }
        return new LlmStageException(AiModelStage.COURSE_QA.name(), exception);
    }

    private CourseQaRecord saveRecord(
        GenerationFence.Ticket ticket,
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
        java.util.function.Supplier<CourseQaRecord> persist = () -> {
            if (recordMapper.insert(record) != 1) {
                throw new BusinessException(ErrorCode.COMMON_INTERNAL_ERROR, "Course QA record insert failed");
            }
            return record;
        };
        if (generationFence == null) return persist.get(); // Direct constructors support isolated unit tests.
        return "FAILED".equals(status) ? generationFence.recordFailure(ticket, persist) : generationFence.commit(ticket, persist);
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

    private void failAiCall(
        AiCallRecordView started,
        String taskId,
        Long userId,
        LlmStageException exception,
        long durationMillis
    ) {
        if (started == null || started.id() == null) {
            return;
        }
        aiCallRecordService.failCall(new FailAiCallRecordCommand(
            started.id(),
            taskId,
            userId,
            durationMillis,
            exception.apiDetails().errorCode(),
            exception.safeDiagnosticSummary(),
            exception.details().retryable(),
            null,
            null
        ));
    }

    private static long elapsedMillis(long startedNanos) {
        return Math.max(1L, Duration.ofNanos(System.nanoTime() - startedNanos).toMillis());
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
