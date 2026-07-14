package com.example.courselingo.task.events;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.task.model.AnalysisTaskStatus;
import com.example.courselingo.task.progress.TaskProgressSnapshot;
import com.example.courselingo.task.progress.TaskProgressSnapshotService;
import java.io.IOException;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@Service
public class TaskEventStreamServiceImpl implements TaskEventStreamService {

    private static final Logger log = LoggerFactory.getLogger(TaskEventStreamServiceImpl.class);
    private static final Set<String> TERMINAL_STATUSES = Set.of(
        AnalysisTaskStatus.SUCCEEDED.name(),
        AnalysisTaskStatus.FAILED.name(),
        AnalysisTaskStatus.CANCELED.name()
    );

    private final CurrentUserService currentUserService;
    private final AnalysisTaskMapper analysisTaskMapper;
    private final TaskProgressSnapshotService progressSnapshotService;
    private final TaskEventStreamProperties properties;
    private final ScheduledExecutorService executor;
    private final AtomicInteger activeConnections = new AtomicInteger();

    public TaskEventStreamServiceImpl(
        CurrentUserService currentUserService,
        AnalysisTaskMapper analysisTaskMapper,
        TaskProgressSnapshotService progressSnapshotService,
        TaskEventStreamProperties properties,
        ScheduledExecutorService taskEventStreamExecutor
    ) {
        this.currentUserService = currentUserService;
        this.analysisTaskMapper = analysisTaskMapper;
        this.progressSnapshotService = progressSnapshotService;
        this.properties = properties;
        this.executor = taskEventStreamExecutor;
    }

    @Override
    public SseEmitter open(String authorizationHeader, String taskId) {
        CurrentUserResponse currentUser = currentUserService.currentUser(authorizationHeader);
        AnalysisTask task = analysisTaskMapper.selectByIdAndUserId(taskId, currentUser.userId());
        if (task == null) {
            throw new BusinessException(ErrorCode.TASK_NOT_FOUND);
        }

        SseEmitter emitter = new SseEmitter(properties.sseTimeout().toMillis());
        StreamState state = new StreamState(emitter);
        activeConnections.incrementAndGet();
        registerCleanupCallbacks(emitter, state);

        TaskEventPayload firstPayload = currentPayload(task);
        if (!sendEvent(emitter, "snapshot", firstPayload)) {
            state.release();
            return emitter;
        }
        if (completeIfTerminal(emitter, state, firstPayload)) {
            return emitter;
        }

        ScheduledFuture<?> future = executor.scheduleWithFixedDelay(
            () -> pollAndSend(taskId, currentUser.userId(), state),
            properties.pollInterval().toMillis(),
            properties.pollInterval().toMillis(),
            TimeUnit.MILLISECONDS
        );
        state.setFuture(future);
        return emitter;
    }

    public int activeConnectionCount() {
        return activeConnections.get();
    }

    private void pollAndSend(String taskId, Long userId, StreamState state) {
        if (state.released()) {
            return;
        }
        try {
            AnalysisTask task = analysisTaskMapper.selectByIdAndUserId(taskId, userId);
            if (task == null) {
                sendEvent(state.emitter(), "error", null);
                state.emitter().complete();
                state.release();
                return;
            }

            TaskEventPayload payload = currentPayload(task);
            if (!payload.equals(state.lastPayload())) {
                if (!sendEvent(state.emitter(), "progress", payload)) {
                    state.release();
                    return;
                }
                state.setLastPayload(payload);
            } else if (state.heartbeatDue()) {
                if (!sendEvent(state.emitter(), "heartbeat", heartbeatPayload(taskId))) {
                    state.release();
                    return;
                }
                state.markHeartbeatSent();
            }

            completeIfTerminal(state.emitter(), state, payload);
        } catch (RuntimeException exception) {
            log.warn("Task event stream polling failed for taskId={}", taskId, exception);
            if (sendEvent(state.emitter(), "error", null)) {
                state.emitter().complete();
            }
            state.release();
        }
    }

    private TaskEventPayload currentPayload(AnalysisTask task) {
        Optional<TaskProgressSnapshot> redisSnapshot = progressSnapshotService.find(task.getId())
            .filter(snapshot -> Objects.equals(task.getId(), snapshot.taskId()));
        return redisSnapshot.map(this::fromSnapshot).orElseGet(() -> fromMysql(task));
    }

    private TaskEventPayload fromSnapshot(TaskProgressSnapshot snapshot) {
        return new TaskEventPayload(
            snapshot.taskId(),
            snapshot.status(),
            snapshot.progressPercent(),
            snapshot.currentStage(),
            snapshot.errorCode(),
            snapshot.errorMessage(),
            snapshot.updatedAt(),
            snapshot.completedChunks(),
            snapshot.totalChunks(),
            snapshot.currentChunkIndex(),
            snapshot.stepDetail()
        );
    }

    private TaskEventPayload fromMysql(AnalysisTask task) {
        return new TaskEventPayload(
            task.getId(),
            task.getStatus(),
            task.getProgressPercent(),
            task.getCurrentStage(),
            task.getErrorCode(),
            task.getErrorMessage(),
            toInstant(task.getUpdatedAt(), task.getCreatedAt())
        );
    }

    private TaskEventPayload heartbeatPayload(String taskId) {
        return new TaskEventPayload(taskId, "HEARTBEAT", null, null, null, null, Instant.now());
    }

    private boolean completeIfTerminal(SseEmitter emitter, StreamState state, TaskEventPayload payload) {
        if (!TERMINAL_STATUSES.contains(payload.status())) {
            state.setLastPayload(payload);
            return false;
        }
        sendEvent(emitter, terminalEventName(payload.status()), payload);
        emitter.complete();
        state.release();
        return true;
    }

    private String terminalEventName(String status) {
        if (AnalysisTaskStatus.SUCCEEDED.name().equals(status)) {
            return "completed";
        }
        if (AnalysisTaskStatus.CANCELED.name().equals(status)) {
            return "canceled";
        }
        return "failed";
    }

    private boolean sendEvent(SseEmitter emitter, String eventName, TaskEventPayload payload) {
        try {
            SseEmitter.SseEventBuilder builder = SseEmitter.event().name(eventName);
            if (payload != null) {
                builder.data(payload);
            }
            emitter.send(builder);
            return true;
        } catch (IOException | IllegalStateException exception) {
            log.debug("Task event stream send failed for event={}", eventName, exception);
            emitter.completeWithError(exception);
            return false;
        }
    }

    private void registerCleanupCallbacks(SseEmitter emitter, StreamState state) {
        emitter.onCompletion(state::release);
        emitter.onTimeout(() -> {
            emitter.complete();
            state.release();
        });
        emitter.onError(error -> state.release());
    }

    private Instant toInstant(LocalDateTime primary, LocalDateTime fallback) {
        LocalDateTime value = primary != null ? primary : fallback;
        return value == null ? Instant.now() : value.toInstant(ZoneOffset.UTC);
    }

    private final class StreamState {

        private final SseEmitter emitter;
        private final AtomicReference<ScheduledFuture<?>> future = new AtomicReference<>();
        private final AtomicBoolean released = new AtomicBoolean(false);
        private volatile TaskEventPayload lastPayload;
        private volatile Instant lastHeartbeatAt = Instant.now();

        private StreamState(SseEmitter emitter) {
            this.emitter = emitter;
        }

        private SseEmitter emitter() {
            return emitter;
        }

        private TaskEventPayload lastPayload() {
            return lastPayload;
        }

        private void setLastPayload(TaskEventPayload lastPayload) {
            this.lastPayload = lastPayload;
        }

        private void setFuture(ScheduledFuture<?> scheduledFuture) {
            future.set(scheduledFuture);
            if (released()) {
                scheduledFuture.cancel(false);
            }
        }

        private boolean heartbeatDue() {
            return Instant.now().minus(properties.heartbeatInterval()).isAfter(lastHeartbeatAt);
        }

        private void markHeartbeatSent() {
            lastHeartbeatAt = Instant.now();
        }

        private boolean released() {
            return released.get();
        }

        private void release() {
            if (!released.compareAndSet(false, true)) {
                return;
            }
            ScheduledFuture<?> scheduledFuture = future.getAndSet(null);
            if (scheduledFuture != null) {
                scheduledFuture.cancel(false);
            }
            activeConnections.decrementAndGet();
        }
    }
}
