package com.example.courselingo.chapter.service;

import com.example.courselingo.ai.llm.LlmProvider;
import com.example.courselingo.ai.llm.LlmRequest;
import com.example.courselingo.ai.llm.LlmResponseFormat;
import com.example.courselingo.ai.llm.LlmResult;
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
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CourseChapterServiceImpl implements CourseChapterService {

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
    @Transactional
    public List<CourseChapterResponse> generate(String taskId, String authorizationHeader) {
        AnalysisTask task = requireOwnedTask(taskId, authorizationHeader);
        if (!properties.isEnabled()) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, "Course chapter generation is disabled");
        }
        CourseChapterEvidenceBundle bundle = evidenceBuilder.build(task.getId(), task.getUserId(), task.getTargetLanguage());
        if (bundle.evidence().isEmpty()) {
            return List.of();
        }
        if (llmProvider == null) {
            throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "Course chapter provider is not configured");
        }
        AiCallRecordView started = startAiCall(task, bundle.evidence().size());
        try {
            LlmRequest request = new LlmRequest(
                "chapter_" + UUID.randomUUID(),
                task.getId(),
                CourseChapterPromptFactory.buildMessages(bundle.evidence(), bundle.globalContext(), properties.getMaxChapters()),
                properties.getLlmTimeout(),
                0.0d,
                4096,
                1,
                Map.of("stage", AiModelStage.COURSE_CHAPTER.name(), "targetLanguage", task.getTargetLanguage()),
                LlmResponseFormat.JSON_OBJECT
            );
            LlmRequest routed = routedRequestFactory == null ? request : routedRequestFactory.apply(AiModelStage.COURSE_CHAPTER, request);
            LlmResult result = llmProvider.generate(routed);
            List<CourseChapterResponseParser.ParsedCourseChapter> parsed = parser.parse(
                result.content(),
                bundle.evidence(),
                properties.getMaxChapters()
            );
            List<CourseChapter> rows = persistSuccess(task, parsed, bundle.evidence(), usage(result));
            completeAiCall(started, task, result, bundle.evidence().size(), rows.size());
            return rows.stream().map(this::toResponse).toList();
        } catch (RuntimeException exception) {
            failAiCall(started, task, exception);
            throw exception instanceof BusinessException
                ? exception
                : new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "Course chapter provider failed");
        }
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
        chapterMapper.deleteByTaskIdAndUserId(task.getId(), task.getUserId());
        for (CourseChapter row : rows) {
            if (chapterMapper.insert(row) != 1) {
                throw new BusinessException(ErrorCode.COMMON_INTERNAL_ERROR, "Course chapter insert failed");
            }
        }
        return rows;
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

    private void failAiCall(AiCallRecordView started, AnalysisTask task, RuntimeException exception) {
        if (started == null || started.id() == null) {
            return;
        }
        aiCallRecordService.failCall(new FailAiCallRecordCommand(
            started.id(),
            task.getId(),
            task.getUserId(),
            null,
            exception instanceof BusinessException businessException ? businessException.errorCode().code() : "AI_PROVIDER_FAILED",
            sanitizer.sanitizeErrorMessage(exception.getMessage()),
            true,
            null,
            null
        ));
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
