package com.example.courselingo.chapter.service;

import com.example.courselingo.ai.llm.LlmProvider;
import com.example.courselingo.ai.llm.LlmProviderFailureCategory;
import com.example.courselingo.ai.llm.LlmProviderFailureDetails;
import com.example.courselingo.ai.llm.LlmRequest;
import com.example.courselingo.ai.llm.LlmResponseFormat;
import com.example.courselingo.ai.llm.LlmResult;
import com.example.courselingo.ai.llm.LlmUsage;
import com.example.courselingo.ai.llm.LlmStageException;
import com.example.courselingo.ai.llm.LlmStructuredOutputExecutor;
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
import com.example.courselingo.chapter.domain.CourseChapter;
import com.example.courselingo.chapter.dto.CourseChapterEvidenceItem;
import com.example.courselingo.chapter.dto.CourseChapterResponse;
import com.example.courselingo.chapter.dto.CourseChapterUsage;
import com.example.courselingo.chapter.mapper.CourseChapterMapper;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.modelrouting.AiModelRoutedLlmRequestFactory;
import com.example.courselingo.modelrouting.AiModelStage;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.annotation.Propagation;
import com.example.courselingo.task.service.GenerationFence;

@Service
public class CourseChapterServiceImpl implements CourseChapterService {

    private GenerationFence generationFence;

    @Autowired
    public void configureGenerationFence(GenerationFence generationFence) {
        this.generationFence = generationFence;
    }


    private static final Logger LOGGER = LoggerFactory.getLogger(CourseChapterServiceImpl.class);

    private static final TypeReference<List<String>> STRING_LIST_TYPE = new TypeReference<>() {
    };
    private static final TypeReference<List<CourseChapterEvidenceItem>> EVIDENCE_LIST_TYPE = new TypeReference<>() {
    };

    private final CurrentUserService currentUserService;
    private final AnalysisTaskMapper analysisTaskMapper;
    private final CourseChapterMapper chapterMapper;
    private final CourseChapterEvidenceBuilder evidenceBuilder;
    private final CourseChapterResponseParser parser;
    private final LlmProvider llmProvider;
    private final AiCallRecordService aiCallRecordService;
    private final AiModelRoutedLlmRequestFactory routedRequestFactory;
    private final CourseChapterProperties properties;
    private final ObjectMapper objectMapper;
    private final Clock clock;
    private final AiCallRecordSanitizer sanitizer = new AiCallRecordSanitizer();

    @Autowired
    public CourseChapterServiceImpl(
        CurrentUserService currentUserService,
        AnalysisTaskMapper analysisTaskMapper,
        CourseChapterMapper chapterMapper,
        CourseChapterEvidenceBuilder evidenceBuilder,
        CourseChapterResponseParser parser,
        ObjectProvider<LlmProvider> llmProvider,
        AiCallRecordService aiCallRecordService,
        AiModelRoutedLlmRequestFactory routedRequestFactory,
        CourseChapterProperties properties,
        ObjectMapper objectMapper
    ) {
        this(
            currentUserService,
            analysisTaskMapper,
            chapterMapper,
            evidenceBuilder,
            parser,
            llmProvider.getIfAvailable(),
            aiCallRecordService,
            routedRequestFactory,
            properties,
            objectMapper,
            Clock.systemUTC()
        );
    }

    public CourseChapterServiceImpl(
        CurrentUserService currentUserService,
        AnalysisTaskMapper analysisTaskMapper,
        CourseChapterMapper chapterMapper,
        CourseChapterEvidenceBuilder evidenceBuilder,
        CourseChapterResponseParser parser,
        LlmProvider llmProvider,
        AiCallRecordService aiCallRecordService,
        AiModelRoutedLlmRequestFactory routedRequestFactory,
        CourseChapterProperties properties,
        ObjectMapper objectMapper,
        Clock clock
    ) {
        this.currentUserService = currentUserService;
        this.analysisTaskMapper = analysisTaskMapper;
        this.chapterMapper = chapterMapper;
        this.evidenceBuilder = evidenceBuilder;
        this.parser = parser == null ? new CourseChapterResponseParser() : parser;
        this.llmProvider = llmProvider;
        this.aiCallRecordService = aiCallRecordService;
        this.routedRequestFactory = routedRequestFactory;
        this.properties = properties == null ? new CourseChapterProperties() : properties;
        this.objectMapper = objectMapper == null ? new ObjectMapper() : objectMapper;
        this.clock = clock == null ? Clock.systemUTC() : clock;
    }

    @Override
    @Transactional(readOnly = true)
    public List<CourseChapterResponse> list(String taskId, String authorizationHeader) {
        AnalysisTask task = requireOwnedTask(taskId, authorizationHeader);
        return chapterMapper.selectByTaskIdAndUserId(task.getId(), task.getUserId()).stream()
            .map(this::toResponse)
            .toList();
    }

    @Override
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    public List<CourseChapterResponse> generate(String taskId, String authorizationHeader) {
        AnalysisTask task = requireOwnedTask(taskId, authorizationHeader);
        if (!properties.isEnabled()) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, "Course chapter generation is disabled");
        }
        GenerationFence.Ticket ticket = generationFence == null ? null
            : generationFence.begin(task.getId(), task.getUserId(), "chapter:" + task.getTargetLanguage());
        CourseChapterEvidenceBundle bundle = evidenceBuilder.build(task.getId(), task.getUserId(), task.getTargetLanguage());
        if (bundle.evidence().isEmpty()) {
            return List.of();
        }
        if (llmProvider == null) {
            throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "Course chapter provider is not configured");
        }
        AiCallRecordView started = startAiCall(task, bundle.evidence().size());
        long startedNanos = System.nanoTime();
        try {
            List<com.example.courselingo.ai.llm.LlmMessage> messages = CourseChapterPromptFactory.buildMessages(
                bundle.evidence(), bundle.globalContext(), properties.getMaxChapters(), properties.getMaxPromptChars()
            );
            LlmRequest request = new LlmRequest(
                "chapter_" + UUID.randomUUID(),
                task.getId(),
                messages,
                properties.getLlmTimeout(),
                0.0d,
                properties.getMaxTokens(),
                properties.getMaxAttempts(),
                Map.of("stage", AiModelStage.COURSE_CHAPTER.name(), "targetLanguage", task.getTargetLanguage()),
                LlmResponseFormat.JSON_OBJECT
            );
            LlmRequest routed = routedRequestFactory == null ? request : routedRequestFactory.apply(AiModelStage.COURSE_CHAPTER, request);
            LlmResult result = executePrimaryWithTextRecovery(task, routed);
            boolean repairAttempted = false;
            boolean coverageCompleted = false;
            boolean fallbackUsed = false;
            List<CourseChapterResponseParser.ParsedCourseChapter> parsed = List.of();
            List<CourseChapterResponseParser.ParsedCourseChapter> primaryParsed = List.of();
            CourseChapterCoverageReport coverage;
            try {
                parsed = parser.parse(result.content(), bundle.evidence(), properties.getMaxChapters());
                primaryParsed = parsed;
                coverage = CourseChapterCoverageValidator.validate(parsed, bundle.evidence(), properties);
            } catch (BusinessException firstParseFailure) {
                coverage = CourseChapterCoverageReport.structuralFailure("structured output is invalid");
            }
            if (!coverage.valid()) {
                repairAttempted = true;
                LlmRequest repair = new LlmRequest(
                    "chapter_repair_" + UUID.randomUUID(),
                    task.getId(),
                    CourseChapterPromptFactory.buildRepairMessages(messages, coverage),
                    properties.getLlmTimeout(),
                    0.0d, properties.getMaxTokens(), 1,
                    Map.of("stage", AiModelStage.COURSE_CHAPTER.name(), "repair", true),
                    LlmResponseFormat.JSON_OBJECT
                );
                LlmRequest routedRepair = routedRequestFactory == null
                    ? repair
                    : routedRequestFactory.apply(AiModelStage.COURSE_CHAPTER, repair);
                LlmResult repaired = LlmStructuredOutputExecutor.execute(llmProvider, routedRepair);
                try {
                    parsed = parser.parse(repaired.content(), bundle.evidence(), properties.getMaxChapters());
                    coverage = CourseChapterCoverageValidator.validate(parsed, bundle.evidence(), properties);
                } catch (BusinessException ignored) {
                    coverage = CourseChapterCoverageReport.structuralFailure("repair output is invalid");
                }
                result = withDuration(repaired, result.duration().plus(repaired.duration()));
            }
            if (!coverage.valid()) {
                List<CourseChapterResponseParser.ParsedCourseChapter> completed = CourseChapterCoverageCompleter.complete(
                    parsed, bundle.evidence(), properties.getMaxChapters()
                );
                CourseChapterCoverageReport completedCoverage = CourseChapterCoverageValidator.validate(
                    completed, bundle.evidence(), properties
                );
                if (!completedCoverage.valid() && parsed != primaryParsed) {
                    completed = CourseChapterCoverageCompleter.complete(
                        primaryParsed, bundle.evidence(), properties.getMaxChapters()
                    );
                    completedCoverage = CourseChapterCoverageValidator.validate(
                        completed, bundle.evidence(), properties
                    );
                }
                if (completedCoverage.valid()) {
                    coverageCompleted = true;
                    parsed = completed;
                    coverage = completedCoverage;
                }
            }
            if (!coverage.valid()) {
                fallbackUsed = true;
                parsed = CourseChapterFallbackFactory.build(bundle.evidence(), task.getTargetLanguage(), properties);
                coverage = CourseChapterCoverageValidator.validate(parsed, bundle.evidence(), properties);
            }
            if (!coverage.valid()) {
                throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "Course chapter coverage validation failed");
            }
            LOGGER.info(
                "event=course_chapter_generation_validated repairAttempted={} coverageCompleted={} fallbackUsed={} chapterCount={} "
                    + "evidenceCount={} timelineCoverage={} evidenceCoverage={} maxGapMillis={}",
                repairAttempted,
                coverageCompleted,
                fallbackUsed,
                parsed.size(),
                bundle.evidence().size(),
                coverage.timelineCoverageRatio(),
                coverage.evidenceCoverageRatio(),
                coverage.maxGapMillis()
            );
            List<CourseChapter> rows = persistSuccess(ticket, task, parsed, bundle.evidence(), usage(result));
            completeAiCall(started, task, result, bundle.evidence().size(), rows.size());
            return rows.stream().map(this::toResponse).toList();
        } catch (RuntimeException exception) {
            LlmStageException safeFailure = toStageFailure(exception);
            if (exception instanceof BusinessException business
                && (business.errorCode() == ErrorCode.TASK_INVALID_STATUS || business.errorCode() == ErrorCode.TASK_NOT_FOUND)) {
                failAiCall(started, task, safeFailure, elapsedMillis(startedNanos));
                throw business;
            }
            if (safeFailure.details().category() == LlmProviderFailureCategory.OUTPUT_INVALID) {
                List<CourseChapterResponseParser.ParsedCourseChapter> fallback = CourseChapterFallbackFactory.build(
                    bundle.evidence(), task.getTargetLanguage(), properties
                );
                CourseChapterCoverageReport coverage = CourseChapterCoverageValidator.validate(
                    fallback, bundle.evidence(), properties
                );
                if (coverage.valid()) {
                    long durationMillis = elapsedMillis(startedNanos);
                    failAiCall(started, task, safeFailure, durationMillis);
                    List<CourseChapter> rows = persistSuccess(
                        ticket, task,
                        fallback,
                        bundle.evidence(),
                        new CourseChapterUsage("deterministic-fallback", "", null, null, null, durationMillis)
                    );
                    LOGGER.warn(
                        "event=course_chapter_provider_output_fallback category={} chapterCount={} evidenceCount={}",
                        safeFailure.details().category(), rows.size(), bundle.evidence().size()
                    );
                    return rows.stream().map(this::toResponse).toList();
                }
            }
            failAiCall(started, task, safeFailure, elapsedMillis(startedNanos));
            throw safeFailure;
        }
    }

    private LlmResult executePrimaryWithTextRecovery(AnalysisTask task, LlmRequest request) {
        try {
            return LlmStructuredOutputExecutor.execute(llmProvider, request);
        } catch (RuntimeException exception) {
            LlmStageException safeFailure = toStageFailure(exception);
            if (request.responseFormat() != LlmResponseFormat.JSON_OBJECT
                || safeFailure.details().category() != LlmProviderFailureCategory.OUTPUT_INVALID) {
                throw exception;
            }
            Map<String, Object> metadata = new LinkedHashMap<>(request.metadata());
            metadata.put("providerOutputRecovery", true);
            LlmRequest recovery = new LlmRequest(
                "chapter_text_recovery_" + UUID.randomUUID(),
                task.getId(),
                request.messages(),
                request.timeout(),
                request.temperature(),
                request.maxTokens(),
                1,
                metadata,
                LlmResponseFormat.TEXT
            );
            LOGGER.warn(
                "event=course_chapter_provider_output_recovery category={} nextResponseFormat={}",
                safeFailure.details().category(), LlmResponseFormat.TEXT
            );
            return LlmStructuredOutputExecutor.execute(llmProvider, recovery);
        }
    }

    private static LlmResult withDuration(LlmResult result, java.time.Duration duration) {
        return new LlmResult(
            result.provider(), result.model(), result.content(), result.finishReason(), result.usage(), duration, result.metadata()
        );
    }

    private static LlmStageException toStageFailure(RuntimeException exception) {
        if (exception instanceof LlmStageException stageException) {
            return stageException;
        }
        if (exception instanceof BusinessException && exception.getCause() == null) {
            return new LlmStageException(
                AiModelStage.COURSE_CHAPTER.name(),
                new LlmProviderFailureDetails(LlmProviderFailureCategory.OUTPUT_INVALID, null, null, false),
                exception
            );
        }
        return new LlmStageException(AiModelStage.COURSE_CHAPTER.name(), exception);
    }

    private AnalysisTask requireOwnedTask(String taskId, String authorizationHeader) {
        String normalizedTaskId = validateTaskId(taskId);
        CurrentUserResponse currentUser = currentUserService.currentUser(authorizationHeader);
        AnalysisTask task = analysisTaskMapper.selectByIdAndUserId(normalizedTaskId, currentUser.userId());
        if (task == null) {
            throw new BusinessException(ErrorCode.TASK_NOT_FOUND);
        }
        return task;
    }

    private List<CourseChapter> persistSuccess(
        GenerationFence.Ticket ticket,
        AnalysisTask task,
        List<CourseChapterResponseParser.ParsedCourseChapter> parsed,
        List<CourseChapterEvidenceItem> evidence,
        CourseChapterUsage usage
    ) {
        LocalDateTime now = LocalDateTime.ofInstant(clock.instant(), clock.getZone());
        List<CourseChapter> rows = new java.util.ArrayList<>();
        for (int index = 0; index < parsed.size(); index++) {
            CourseChapterResponseParser.ParsedCourseChapter chapter = parsed.get(index);
            CourseChapter row = new CourseChapter();
            row.setTaskId(task.getId());
            row.setUserId(task.getUserId());
            row.setChapterIndex(index);
            row.setTitle(chapter.title());
            row.setSummary(chapter.summary());
            row.setKeywordsJson(toJson(chapter.keywords()));
            row.setStartMillis(chapter.startTimeMillis());
            row.setEndMillis(chapter.endTimeMillis());
            row.setEvidenceJson(toJson(citedEvidence(evidence, chapter.evidenceIndexes())));
            row.setStatus("SUCCEEDED");
            row.setProvider(usage.provider());
            row.setModel(usage.model());
            row.setPromptTokens(usage.promptTokens());
            row.setCompletionTokens(usage.completionTokens());
            row.setTotalTokens(usage.totalTokens());
            row.setDurationMillis(usage.durationMillis());
            row.setCreatedAt(now);
            row.setUpdatedAt(now);
            rows.add(row);
        }
        java.util.function.Supplier<List<CourseChapter>> persist = () -> {
        chapterMapper.deleteByTaskIdAndUserId(task.getId(), task.getUserId());
        for (CourseChapter row : rows) {
            if (chapterMapper.insert(row) != 1) {
                throw new BusinessException(ErrorCode.COMMON_INTERNAL_ERROR, "Course chapter insert failed");
            }
        }
        return rows;
        };
        return generationFence == null ? persist.get() : generationFence.commit(ticket, persist);
    }

    private AiCallRecordView startAiCall(AnalysisTask task, int inputUnits) {
        if (aiCallRecordService == null) {
            return null;
        }
        return aiCallRecordService.startCall(new StartAiCallRecordCommand(
            task.getId(),
            task.getUserId(),
            AiCallType.LLM,
            AiCallStage.COURSE_CHAPTER,
            safeProviderName(),
            llmProvider.modelNameForDiagnostics(),
            null,
            inputUnits
        ));
    }

    private void completeAiCall(AiCallRecordView started, AnalysisTask task, LlmResult result, int inputUnits, int outputUnits) {
        if (started == null || started.id() == null) {
            return;
        }
        LlmUsage usage = result.usage();
        aiCallRecordService.completeCall(new CompleteAiCallRecordCommand(
            started.id(),
            task.getId(),
            task.getUserId(),
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
        AnalysisTask task,
        LlmStageException exception,
        long durationMillis
    ) {
        if (started == null || started.id() == null) {
            return;
        }
        aiCallRecordService.failCall(new FailAiCallRecordCommand(
            started.id(),
            task.getId(),
            task.getUserId(),
            durationMillis,
            exception.apiDetails().errorCode(),
            exception.safeDiagnosticSummary(),
            exception.details().retryable(),
            null,
            null
        ));
    }

    private static long elapsedMillis(long startedNanos) {
        return Math.max(1L, java.time.Duration.ofNanos(System.nanoTime() - startedNanos).toMillis());
    }

    private CourseChapterResponse toResponse(CourseChapter row) {
        return new CourseChapterResponse(
            row.getId(),
            row.getChapterIndex() == null ? 0 : row.getChapterIndex(),
            row.getTitle(),
            row.getSummary(),
            readKeywords(row.getKeywordsJson()),
            row.getStartMillis() == null ? 0L : row.getStartMillis(),
            row.getEndMillis() == null ? 0L : row.getEndMillis(),
            formatRange(row.getStartMillis(), row.getEndMillis()),
            readEvidence(row.getEvidenceJson()),
            new CourseChapterUsage(
                row.getProvider(),
                row.getModel(),
                row.getPromptTokens(),
                row.getCompletionTokens(),
                row.getTotalTokens(),
                row.getDurationMillis()
            )
        );
    }

    private CourseChapterUsage usage(LlmResult result) {
        LlmUsage usage = result.usage();
        return new CourseChapterUsage(
            result.provider(),
            result.model(),
            usage.promptTokens(),
            usage.completionTokens(),
            usage.totalTokens(),
            result.duration().toMillis()
        );
    }

    private List<CourseChapterEvidenceItem> citedEvidence(List<CourseChapterEvidenceItem> evidence, List<Integer> indexes) {
        return indexes.stream()
            .filter(index -> index >= 0 && index < evidence.size())
            .map(evidence::get)
            .toList();
    }

    private List<String> readKeywords(String json) {
        try {
            return json == null || json.isBlank() ? List.of() : objectMapper.readValue(json, STRING_LIST_TYPE);
        } catch (Exception ignored) {
            return List.of();
        }
    }

    private List<CourseChapterEvidenceItem> readEvidence(String json) {
        try {
            return json == null || json.isBlank() ? List.of() : objectMapper.readValue(json, EVIDENCE_LIST_TYPE);
        } catch (Exception ignored) {
            return List.of();
        }
    }

    private String toJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value == null ? List.of() : value);
        } catch (Exception ignored) {
            return "[]";
        }
    }

    private String safeProviderName() {
        String provider = llmProvider == null ? "" : llmProvider.providerName();
        String sanitized = sanitizer.sanitizeErrorMessage(provider);
        return sanitized == null || sanitized.isBlank() ? "llm" : sanitized.strip();
    }

    private static String validateTaskId(String taskId) {
        if (taskId == null || taskId.isBlank()) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, "Task id is required");
        }
        return taskId.strip();
    }

    private static String formatRange(Long start, Long end) {
        return formatTime(start == null ? 0L : start) + " - " + formatTime(end == null ? 0L : end);
    }

    private static String formatTime(long millis) {
        long totalSeconds = Math.max(0L, millis / 1000L);
        long hours = totalSeconds / 3600L;
        long minutes = (totalSeconds % 3600L) / 60L;
        long seconds = totalSeconds % 60L;
        return "%02d:%02d:%02d".formatted(hours, minutes, seconds);
    }
}
