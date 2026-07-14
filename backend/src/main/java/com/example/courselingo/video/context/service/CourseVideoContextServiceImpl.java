package com.example.courselingo.video.context.service;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.video.context.domain.CourseVideoChunk;
import com.example.courselingo.video.context.dto.CourseVideoContextChunkResponse;
import com.example.courselingo.video.context.dto.CourseVideoContextEvidenceItem;
import com.example.courselingo.video.context.dto.CourseVideoContextRebuildResponse;
import com.example.courselingo.video.context.dto.CourseVideoContextResponse;
import com.example.courselingo.video.context.mapper.CourseVideoChunkMapper;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.List;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CourseVideoContextServiceImpl implements CourseVideoContextService {

    private static final TypeReference<List<String>> STRING_LIST_TYPE = new TypeReference<>() {
    };
    private static final TypeReference<List<CourseVideoContextEvidenceItem>> EVIDENCE_LIST_TYPE = new TypeReference<>() {
    };

    private final CurrentUserService currentUserService;
    private final AnalysisTaskMapper analysisTaskMapper;
    private final CourseVideoChunkMapper chunkMapper;
    private final CourseVideoContextBuilder builder;
    private final ObjectMapper objectMapper;
    private final Clock clock;

    @Autowired
    public CourseVideoContextServiceImpl(
        CurrentUserService currentUserService,
        AnalysisTaskMapper analysisTaskMapper,
        CourseVideoChunkMapper chunkMapper,
        CourseVideoContextBuilder builder,
        ObjectMapper objectMapper
    ) {
        this(currentUserService, analysisTaskMapper, chunkMapper, builder, objectMapper, Clock.systemUTC());
    }

    public CourseVideoContextServiceImpl(
        CurrentUserService currentUserService,
        AnalysisTaskMapper analysisTaskMapper,
        CourseVideoChunkMapper chunkMapper,
        CourseVideoContextBuilder builder,
        ObjectMapper objectMapper,
        Clock clock
    ) {
        this.currentUserService = currentUserService;
        this.analysisTaskMapper = analysisTaskMapper;
        this.chunkMapper = chunkMapper;
        this.builder = builder;
        this.objectMapper = objectMapper == null ? new ObjectMapper() : objectMapper;
        this.clock = clock == null ? Clock.systemUTC() : clock;
    }

    @Override
    @Transactional(readOnly = true)
    public CourseVideoContextResponse get(String taskId, String authorizationHeader) {
        AnalysisTask task = requireOwnedTask(taskId, authorizationHeader);
        List<CourseVideoChunk> rows = chunkMapper.selectByTaskIdUserIdAndTargetLanguage(
            task.getId(),
            task.getUserId(),
            task.getTargetLanguage()
        );
        CourseVideoContextSourceSnapshot snapshot = builder.snapshot(task, rows);
        List<CourseVideoContextChunkResponse> chunks = rows.stream().map(this::toChunkResponse).toList();
        return new CourseVideoContextResponse(
            task.getId(),
            task.getTargetLanguage(),
            rows.stream().mapToLong(row -> row.getEndMillis() == null ? 0L : row.getEndMillis()).max().orElse(0L),
            inferredWindowSeconds(rows),
            rows.isEmpty() ? CourseVideoContextBuildVersion.VIDEO_CONTEXT_R1 : rows.getFirst().getBuildVersion(),
            snapshot.toStats(),
            snapshot.globalSummary(),
            snapshot.globalKeywords(),
            snapshot.chapters(),
            chunks
        );
    }

    @Override
    @Transactional
    public CourseVideoContextRebuildResponse rebuild(String taskId, String authorizationHeader) {
        AnalysisTask task = requireOwnedTask(taskId, authorizationHeader);
        CourseVideoContextBuildResult result = builder.build(task);
        LocalDateTime now = LocalDateTime.ofInstant(clock.instant(), clock.getZone());
        chunkMapper.deleteByTaskIdUserIdAndTargetLanguage(task.getId(), task.getUserId(), task.getTargetLanguage());
        for (CourseVideoContextChunkResponse chunk : result.chunks()) {
            CourseVideoChunk row = toRow(task, chunk, result.buildVersion(), now);
            if (chunkMapper.insert(row) != 1) {
                throw new BusinessException(ErrorCode.COMMON_INTERNAL_ERROR, "Course video chunk insert failed");
            }
        }
        return new CourseVideoContextRebuildResponse(
            task.getId(),
            task.getTargetLanguage(),
            result.chunks().size(),
            result.buildVersion(),
            now
        );
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

    private CourseVideoChunk toRow(AnalysisTask task, CourseVideoContextChunkResponse chunk, String buildVersion, LocalDateTime now) {
        CourseVideoChunk row = new CourseVideoChunk();
        row.setTaskId(task.getId());
        row.setUserId(task.getUserId());
        row.setTargetLanguage(task.getTargetLanguage());
        row.setChunkIndex(chunk.chunkIndex());
        row.setStartMillis(chunk.startMillis());
        row.setEndMillis(chunk.endMillis());
        row.setTimeText(chunk.timeText());
        row.setSummary(chunk.summary());
        row.setKeywordsJson(toJson(chunk.keywords()));
        row.setEvidenceJson(toJson(chunk.evidence()));
        row.setSourceTextPreview(chunk.sourceTextPreview());
        row.setTranslatedTextPreview(chunk.translatedTextPreview());
        row.setBuildVersion(buildVersion);
        row.setCreatedAt(now);
        row.setUpdatedAt(now);
        return row;
    }

    private CourseVideoContextChunkResponse toChunkResponse(CourseVideoChunk row) {
        return new CourseVideoContextChunkResponse(
            row.getChunkIndex(),
            row.getStartMillis(),
            row.getEndMillis(),
            row.getTimeText(),
            row.getSummary(),
            readStringList(row.getKeywordsJson()),
            row.getSourceTextPreview(),
            row.getTranslatedTextPreview(),
            readEvidence(row.getEvidenceJson())
        );
    }

    private static int inferredWindowSeconds(List<CourseVideoChunk> rows) {
        if (rows == null || rows.isEmpty()) {
            return 240;
        }
        CourseVideoChunk first = rows.getFirst();
        long durationMillis = Math.max(1000L, (first.getEndMillis() == null ? 0L : first.getEndMillis())
            - (first.getStartMillis() == null ? 0L : first.getStartMillis()));
        return (int) Math.max(1L, durationMillis / 1000L);
    }

    private List<String> readStringList(String json) {
        try {
            return json == null || json.isBlank() ? List.of() : objectMapper.readValue(json, STRING_LIST_TYPE);
        } catch (Exception ignored) {
            return List.of();
        }
    }

    private List<CourseVideoContextEvidenceItem> readEvidence(String json) {
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

    private static String validateTaskId(String taskId) {
        if (taskId == null || taskId.isBlank()) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, "Task id is required");
        }
        return taskId.strip();
    }
}
