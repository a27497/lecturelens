package com.example.courselingo.task.runner;

import com.example.courselingo.ai.asr.SpeechToTextProvider;
import com.example.courselingo.ai.asr.SpeechToTextRequest;
import com.example.courselingo.ai.asr.SpeechToTextResult;
import com.example.courselingo.ai.asr.SiliconFlowAsrException;
import com.example.courselingo.ai.asr.SpeechToTextProviderException;
import com.example.courselingo.ai.asr.TranscribedSegment;
import com.example.courselingo.ai.record.domain.AiCallStage;
import com.example.courselingo.ai.record.domain.AiCallType;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.logging.SafeLogSanitizer;
import com.example.courselingo.media.AudioChunk;
import com.example.courselingo.media.AudioChunker;
import com.example.courselingo.media.AudioDurationProbe;
import com.example.courselingo.media.AudioExtractionResult;
import com.example.courselingo.media.JavaSoundAudioDurationProbe;
import com.example.courselingo.task.claim.NoopTaskClaimService;
import com.example.courselingo.task.claim.TaskClaimService;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.task.model.AnalysisTaskStage;
import com.example.courselingo.task.model.AnalysisTaskStatus;
import com.example.courselingo.task.progress.NoopTaskProgressSnapshotService;
import com.example.courselingo.task.progress.TaskProgressSnapshot;
import com.example.courselingo.task.progress.TaskProgressSnapshotService;
import java.io.IOException;
import java.net.SocketException;
import java.net.http.HttpTimeoutException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletionService;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorCompletionService;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

final class TranscribeAudioStep implements PipelineAnalysisTaskStep {

    @FunctionalInterface
    interface ChunkCompletionObserver {

        void onCollected(int chunkIndex);
    }

    private static final Logger LOGGER = LoggerFactory.getLogger(TranscribeAudioStep.class);
    private static final ChunkCompletionObserver NOOP_CHUNK_COMPLETION_OBSERVER = ignored -> {
    };
    private static final Duration DEFAULT_ASR_TIMEOUT = Duration.ofSeconds(60);
    private static final String ASR_CHUNK_LIMIT_MESSAGE =
        "视频语音转写分片数量超过当前上限，请提高 ASR_CHUNK_MAX_CHUNKS 或使用更短视频后重试";
    private static final int ASR_PROGRESS_START = 20;
    private static final int ASR_PROGRESS_END = 55;
    private static final long CLAIM_REFRESH_INTERVAL_SECONDS = 60L;
    private static final Set<Integer> RETRYABLE_ASR_STATUS_CODES = Set.of(408, 429, 500, 502, 503, 504);
    private static final Set<Integer> NON_RETRYABLE_ASR_STATUS_CODES = Set.of(400, 401, 403, 404, 413);

    private final SpeechToTextProvider speechToTextProvider;
    private final AudioChunker audioChunker;
    private final AudioDurationProbe audioDurationProbe;
    private final AsrChunkingProperties chunkingProperties;
    private final PipelineRunnerWorkspace workspace;
    private final AnalysisTaskMapper analysisTaskMapper;
    private final TaskProgressSnapshotService progressSnapshotService;
    private final TaskClaimService taskClaimService;
    private final ChunkCompletionObserver chunkCompletionObserver;

    TranscribeAudioStep(SpeechToTextProvider speechToTextProvider) {
        this(speechToTextProvider, null, new AsrChunkingProperties(), null, null);
    }

    TranscribeAudioStep(SpeechToTextProvider speechToTextProvider, AudioDurationProbe audioDurationProbe) {
        this(
            speechToTextProvider,
            null,
            new AsrChunkingProperties(),
            null,
            null,
            new NoopTaskProgressSnapshotService(),
            new NoopTaskClaimService(),
            NOOP_CHUNK_COMPLETION_OBSERVER,
            audioDurationProbe
        );
    }

    TranscribeAudioStep(
        SpeechToTextProvider speechToTextProvider,
        AudioChunker audioChunker,
        AsrChunkingProperties chunkingProperties,
        PipelineRunnerWorkspace workspace,
        AnalysisTaskMapper analysisTaskMapper
    ) {
        this(
            speechToTextProvider,
            audioChunker,
            chunkingProperties,
            workspace,
            analysisTaskMapper,
            new NoopTaskProgressSnapshotService(),
            new NoopTaskClaimService()
        );
    }

    TranscribeAudioStep(
        SpeechToTextProvider speechToTextProvider,
        AudioChunker audioChunker,
        AsrChunkingProperties chunkingProperties,
        PipelineRunnerWorkspace workspace,
        AnalysisTaskMapper analysisTaskMapper,
        TaskProgressSnapshotService progressSnapshotService,
        TaskClaimService taskClaimService
    ) {
        this(
            speechToTextProvider,
            audioChunker,
            chunkingProperties,
            workspace,
            analysisTaskMapper,
            progressSnapshotService,
            taskClaimService,
            NOOP_CHUNK_COMPLETION_OBSERVER,
            new JavaSoundAudioDurationProbe()
        );
    }

    TranscribeAudioStep(
        SpeechToTextProvider speechToTextProvider,
        AudioChunker audioChunker,
        AsrChunkingProperties chunkingProperties,
        PipelineRunnerWorkspace workspace,
        AnalysisTaskMapper analysisTaskMapper,
        TaskProgressSnapshotService progressSnapshotService,
        TaskClaimService taskClaimService,
        ChunkCompletionObserver chunkCompletionObserver
    ) {
        this(
            speechToTextProvider,
            audioChunker,
            chunkingProperties,
            workspace,
            analysisTaskMapper,
            progressSnapshotService,
            taskClaimService,
            chunkCompletionObserver,
            new JavaSoundAudioDurationProbe()
        );
    }

    TranscribeAudioStep(
        SpeechToTextProvider speechToTextProvider,
        AudioChunker audioChunker,
        AsrChunkingProperties chunkingProperties,
        PipelineRunnerWorkspace workspace,
        AnalysisTaskMapper analysisTaskMapper,
        AudioDurationProbe audioDurationProbe
    ) {
        this(
            speechToTextProvider,
            audioChunker,
            chunkingProperties,
            workspace,
            analysisTaskMapper,
            new NoopTaskProgressSnapshotService(),
            new NoopTaskClaimService(),
            NOOP_CHUNK_COMPLETION_OBSERVER,
            audioDurationProbe
        );
    }

    TranscribeAudioStep(
        SpeechToTextProvider speechToTextProvider,
        AudioChunker audioChunker,
        AsrChunkingProperties chunkingProperties,
        PipelineRunnerWorkspace workspace,
        AnalysisTaskMapper analysisTaskMapper,
        TaskProgressSnapshotService progressSnapshotService,
        TaskClaimService taskClaimService,
        ChunkCompletionObserver chunkCompletionObserver,
        AudioDurationProbe audioDurationProbe
    ) {
        this.speechToTextProvider = Objects.requireNonNull(
            speechToTextProvider,
            "speech to text provider is required"
        );
        this.audioChunker = audioChunker;
        this.audioDurationProbe = Objects.requireNonNull(audioDurationProbe, "audio duration probe is required");
        this.chunkingProperties = chunkingProperties == null ? new AsrChunkingProperties() : chunkingProperties;
        this.workspace = workspace;
        this.analysisTaskMapper = analysisTaskMapper;
        this.progressSnapshotService = progressSnapshotService == null
            ? new NoopTaskProgressSnapshotService()
            : progressSnapshotService;
        this.taskClaimService = taskClaimService == null ? new NoopTaskClaimService() : taskClaimService;
        this.chunkCompletionObserver = chunkCompletionObserver == null
            ? NOOP_CHUNK_COMPLETION_OBSERVER
            : chunkCompletionObserver;
    }

    @Override
    public PipelineAnalysisTaskStepName name() {
        return PipelineAnalysisTaskStepName.TRANSCRIBE;
    }

    @Override
    public void execute(PipelineAnalysisTaskStepContext context) {
        AudioExtractionResult audio = context.requireAudioExtractionResult();
        long authoritativeAudioDurationMillis = audioDurationProbe.probeDurationMillis(audio.audioFile());
        long startedNanos = System.nanoTime();
        try {
            SpeechToTextResult result = transcribe(context, audio, authoritativeAudioDurationMillis);
            if (result == null) {
                throw new IllegalStateException("ASR result is required");
            }
            context.setSpeechToTextResult(result);
            context.addAiCallRecord(PipelineAiCallRecord.succeeded(
                AiCallType.ASR,
                AiCallStage.TRANSCRIPTION,
                firstNonBlank(result.provider(), speechToTextProvider.providerName()),
                null,
                durationMillis(result.duration(), startedNanos),
                null,
                null,
                null,
                millisToSeconds(result.audioDurationMillis()),
                result.segments().size(),
                null,
                null
            ));
        } catch (RuntimeException exception) {
            context.addAiCallRecord(PipelineAiCallRecord.failed(
                AiCallType.ASR,
                AiCallStage.TRANSCRIPTION,
                speechToTextProvider.providerName(),
                null,
                elapsedMillis(startedNanos),
                "AI_PROVIDER_FAILED",
                exception.getMessage(),
                true,
                null,
                null
            ));
            throw exception;
        }
    }

    private SpeechToTextResult transcribe(
        PipelineAnalysisTaskStepContext context,
        AudioExtractionResult audio,
        long authoritativeAudioDurationMillis
    ) {
        Path audioFile = audio.audioFile();
        long audioSizeBytes = readFileSize(audioFile, "ASR audio file size cannot be read");
        long maxAudioSizeBytes = chunkingProperties.effectiveMaxAudioFileSizeBytes();
        if (maxAudioSizeBytes <= 0L) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, "ASR max audio file size is not configured");
        }
        if (audioSizeBytes <= maxAudioSizeBytes) {
            LOGGER.info(
                "ASR single-file mode selected: taskId={}, audioSizeBytes={}, maxAudioSizeBytes={}",
                context.taskId(),
                audioSizeBytes,
                maxAudioSizeBytes
            );
            return clampSingleResult(
                context,
                transcribeOne(audio.audioFile(), context),
                authoritativeAudioDurationMillis
            );
        }
        if (!chunkingProperties.isEnabled()) {
            throw new BusinessException(
                ErrorCode.COMMON_VALIDATION_FAILED,
                "ASR chunking disabled; audio file exceeds configured limit"
            );
        }
        if (audioChunker == null || workspace == null) {
            throw new BusinessException(
                ErrorCode.COMMON_VALIDATION_FAILED,
                "ASR chunking is not configured; audio file exceeds configured limit"
            );
        }
        LOGGER.info(
            "ASR chunked mode selected: taskId={}, audioSizeBytes={}, maxAudioSizeBytes={}, chunkDurationSeconds={}",
            context.taskId(),
            audioSizeBytes,
            maxAudioSizeBytes,
            chunkingProperties.getChunkDuration().toSeconds()
        );
        Path chunkDirectory = workspace.asrChunksOutputDirectory(context);
        try {
            List<AudioChunk> chunks = audioChunker.split(
                audioFile,
                chunkDirectory,
                chunkingProperties.getChunkDuration(),
                chunkingProperties.getMaxChunks()
            );
            ChunkSizeStats chunkSizeStats = validateChunks(chunks, authoritativeAudioDurationMillis);
            LOGGER.info(
                "ASR chunks created: taskId={}, chunkCount={}, maxChunkSizeBytes={}, minChunkSizeBytes={}, concurrency={}",
                context.taskId(),
                chunks.size(),
                chunkSizeStats.maxChunkSizeBytes(),
                chunkSizeStats.minChunkSizeBytes(),
                Math.min(chunks.size(), chunkingProperties.effectiveConcurrency())
            );
            List<ChunkTranscriptionResult> chunkResults = transcribeChunksConcurrently(context, chunks);
            return mergeChunkResults(
                context,
                chunkResults.stream()
                    .sorted(Comparator.comparingInt(ChunkTranscriptionResult::chunkIndex))
                    .map(ChunkTranscriptionResult::result)
                    .toList(),
                chunks,
                authoritativeAudioDurationMillis
            );
        } finally {
            deleteDirectoryQuietly(chunkDirectory);
        }
    }

    private List<ChunkTranscriptionResult> transcribeChunksConcurrently(
        PipelineAnalysisTaskStepContext context,
        List<AudioChunk> chunks
    ) {
        int totalChunks = chunks.size();
        int concurrency = Math.min(totalChunks, chunkingProperties.effectiveConcurrency());
        AtomicInteger completedChunks = new AtomicInteger(0);
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
            concurrency,
            concurrency,
            0L,
            TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<>(Math.max(1, totalChunks)),
            new AsrChunkThreadFactory(context.taskId()),
            new ThreadPoolExecutor.AbortPolicy()
        );
        ScheduledExecutorService keepAliveExecutor = java.util.concurrent.Executors.newSingleThreadScheduledExecutor(
            new AsrChunkThreadFactory(context.taskId() + "-claim-refresh")
        );
        ScheduledFuture<?> keepAlive = keepAliveExecutor.scheduleAtFixedRate(
            () -> refreshClaim(context, "periodic"),
            CLAIM_REFRESH_INTERVAL_SECONDS,
            CLAIM_REFRESH_INTERVAL_SECONDS,
            TimeUnit.SECONDS
        );
        try {
            CompletionService<ChunkTranscriptionResult> completionService = new ExecutorCompletionService<>(executor);
            for (int i = 0; i < totalChunks; i++) {
                int chunkIndex = i;
                AudioChunk chunk = chunks.get(i);
                completionService.submit(() -> transcribeChunk(context, chunk, chunkIndex, totalChunks, completedChunks));
            }

            List<ChunkTranscriptionResult> results = new ArrayList<>(totalChunks);
            for (int i = 0; i < totalChunks; i++) {
                try {
                    ChunkTranscriptionResult completed = completionService.take().get();
                    chunkCompletionObserver.onCollected(completed.chunkIndex());
                    results.add(completed);
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                    executor.shutdownNow();
                    throw new SiliconFlowAsrException("SiliconFlow ASR chunk wait was interrupted", true, exception);
                } catch (ExecutionException exception) {
                    executor.shutdownNow();
                    Throwable cause = exception.getCause();
                    if (cause instanceof RuntimeException runtimeException) {
                        throw runtimeException;
                    }
                    throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "ASR chunk failed", cause);
                }
            }
            return results;
        } finally {
            keepAlive.cancel(false);
            keepAliveExecutor.shutdownNow();
            executor.shutdownNow();
        }
    }

    private ChunkTranscriptionResult transcribeChunk(
        PipelineAnalysisTaskStepContext context,
        AudioChunk chunk,
        int zeroBasedChunkIndex,
        int totalChunks,
        AtomicInteger completedChunks
    ) {
        int chunkNumber = zeroBasedChunkIndex + 1;
        ensureTaskStillRunning(context);
        refreshClaim(context, "chunk-start");
        updateAsrProgress(context, completedChunks.get(), totalChunks, chunkNumber);
        long chunkStartedNanos = System.nanoTime();
        long chunkSizeBytes = readFileSize(chunk.audioFile(), "ASR chunk file size cannot be read");
        LOGGER.info(
            "ASR chunk started: taskId={}, chunkIndex={}/{}, chunkSizeBytes={}, offsetMillis={}",
            context.taskId(),
            chunkNumber,
            totalChunks,
            chunkSizeBytes,
            chunk.offsetMillis()
        );
        try {
            SpeechToTextResult chunkResult = transcribeChunkWithRetry(
                chunk.audioFile(),
                context,
                chunkNumber,
                totalChunks
            );
            int nextCompleted = completedChunks.incrementAndGet();
            LOGGER.info(
                "ASR chunk completed: taskId={}, chunkIndex={}/{}, segmentCount={}, durationMillis={}",
                context.taskId(),
                chunkNumber,
                totalChunks,
                chunkResult.segments().size(),
                elapsedMillis(chunkStartedNanos)
            );
            updateAsrProgress(context, nextCompleted, totalChunks, chunkNumber);
            refreshClaim(context, "chunk-complete");
            return new ChunkTranscriptionResult(zeroBasedChunkIndex, chunk.offsetMillis(), chunkResult);
        } catch (RuntimeException exception) {
            throw sanitizedChunkFailure(context, chunkNumber, totalChunks, exception);
        }
    }

    private SpeechToTextResult transcribeOne(Path audioFile, PipelineAnalysisTaskStepContext context) {
        return speechToTextProvider.transcribe(new SpeechToTextRequest(
            audioFile,
            context.targetLanguage(),
            context.requestId(),
            context.taskId(),
            DEFAULT_ASR_TIMEOUT
        ));
    }

    private SpeechToTextResult transcribeChunkWithRetry(
        Path audioFile,
        PipelineAnalysisTaskStepContext context,
        int chunkNumber,
        int totalChunks
    ) {
        int maxAttempts = Math.max(1, chunkingProperties.getChunkRetry().getMaxAttempts());
        RuntimeException lastFailure = null;
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            ensureTaskStillRunning(context);
            long attemptStartedNanos = System.nanoTime();
            refreshClaim(context, "chunk-attempt-start");
            try {
                SpeechToTextResult result = transcribeOne(audioFile, context);
                refreshClaim(context, "chunk-attempt-complete");
                return result;
            } catch (RuntimeException exception) {
                lastFailure = exception;
                AsrRetryFailure failure = classifyAsrFailure(exception);
                boolean shouldRetry = failure.retryable() && attempt < maxAttempts;
                refreshClaim(context, "chunk-attempt-failed");
                if (!shouldRetry) {
                    LOGGER.warn(
                        "ASR chunk failed without retry: taskId={}, chunkIndex={}/{}, attempt={}, maxAttempts={}, failureType={}, httpStatus={}, durationMillis={}",
                        context.taskId(),
                        chunkNumber,
                        totalChunks,
                        attempt,
                        maxAttempts,
                        failure.failureType(),
                        failure.httpStatus(),
                        elapsedMillis(attemptStartedNanos)
                    );
                    throw exception;
                }
                LOGGER.warn(
                    "ASR chunk failed, retrying: taskId={}, chunkIndex={}/{}, attempt={}, maxAttempts={}, failureType={}, httpStatus={}, durationMillis={}",
                    context.taskId(),
                    chunkNumber,
                    totalChunks,
                    attempt,
                    maxAttempts,
                    failure.failureType(),
                    failure.httpStatus(),
                    elapsedMillis(attemptStartedNanos)
                );
                refreshClaim(context, "chunk-retry-before-backoff");
                sleepBeforeRetry(attempt);
                refreshClaim(context, "chunk-retry-after-backoff");
            }
        }
        throw lastFailure == null ? new IllegalStateException("ASR chunk retry failed unexpectedly") : lastFailure;
    }

    private void sleepBeforeRetry(int failedAttempt) {
        Duration backoff = resolveBackoff(failedAttempt);
        if (backoff.isZero() || backoff.isNegative()) {
            return;
        }
        try {
            Thread.sleep(backoff.toMillis());
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new SiliconFlowAsrException("SiliconFlow ASR retry wait was interrupted", true, exception);
        }
    }

    private Duration resolveBackoff(int failedAttempt) {
        List<Duration> backoff = chunkingProperties.getChunkRetry().getBackoff();
        if (backoff == null || backoff.isEmpty()) {
            return Duration.ZERO;
        }
        int index = Math.min(Math.max(0, failedAttempt - 1), backoff.size() - 1);
        Duration delay = backoff.get(index);
        return delay == null ? Duration.ZERO : delay;
    }

    private static AsrRetryFailure classifyAsrFailure(RuntimeException exception) {
        if (exception instanceof BusinessException) {
            return new AsrRetryFailure(false, "business", null);
        }
        if (exception instanceof SiliconFlowAsrException siliconFlowException) {
            Integer statusCode = siliconFlowException.statusCode().orElse(null);
            if (statusCode != null && NON_RETRYABLE_ASR_STATUS_CODES.contains(statusCode)) {
                return new AsrRetryFailure(false, "http_" + statusCode, statusCode);
            }
            if (statusCode != null && RETRYABLE_ASR_STATUS_CODES.contains(statusCode)) {
                return new AsrRetryFailure(true, "http_" + statusCode, statusCode);
            }
            if (!siliconFlowException.retryable()) {
                return new AsrRetryFailure(false, "provider_non_retryable", statusCode);
            }
            return new AsrRetryFailure(true, "provider_retryable", statusCode);
        }
        if (exception instanceof SpeechToTextProviderException && isNonRetryableProviderMessage(exception.getMessage())) {
            return new AsrRetryFailure(false, "provider_non_retryable", null);
        }
        if (hasRetryableCause(exception) || isRetryableProviderMessage(exception.getMessage())) {
            return new AsrRetryFailure(true, "provider_retryable", null);
        }
        return new AsrRetryFailure(false, "provider_non_retryable", null);
    }

    private static boolean hasRetryableCause(Throwable throwable) {
        Set<Throwable> visited = new HashSet<>();
        Throwable current = throwable;
        while (current != null && visited.add(current)) {
            if (current instanceof HttpTimeoutException || current instanceof SocketException) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }

    private static boolean isNonRetryableProviderMessage(String message) {
        String normalized = normalizeMessage(message);
        return normalized.contains("api key")
            || normalized.contains("401")
            || normalized.contains("403")
            || normalized.contains("audio file exceeds configured limit")
            || normalized.contains("unsupported format")
            || normalized.contains("request is invalid")
            || normalized.contains("configuration is invalid")
            || normalized.contains("response json is invalid");
    }

    private static boolean isRetryableProviderMessage(String message) {
        String normalized = normalizeMessage(message);
        return normalized.contains("timeout")
            || normalized.contains("timed out")
            || normalized.contains("connection reset")
            || normalized.contains("econnreset")
            || normalized.contains("socket hang up")
            || normalized.contains("temporarily unavailable")
            || normalized.contains("temporary unavailable")
            || normalized.contains("network call failed");
    }

    private static String normalizeMessage(String message) {
        return message == null ? "" : message.toLowerCase(Locale.ROOT);
    }

    private static long readFileSize(Path audioFile, String errorMessage) {
        try {
            return Files.size(audioFile);
        } catch (IOException exception) {
            throw new BusinessException(ErrorCode.MEDIA_INPUT_INVALID, errorMessage, exception);
        }
    }

    private ChunkSizeStats validateChunks(List<AudioChunk> chunks, long authoritativeAudioDurationMillis) {
        if (chunks == null || chunks.isEmpty()) {
            throw new BusinessException(ErrorCode.MEDIA_FFMPEG_FAILED, "ASR chunking produced no chunks");
        }
        if (chunks.size() > chunkingProperties.getMaxChunks()) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, ASR_CHUNK_LIMIT_MESSAGE);
        }
        long maxChunkBytes = chunkingProperties.effectiveMaxChunkFileSizeBytes();
        long minChunkSizeBytes = Long.MAX_VALUE;
        long maxChunkSizeBytes = 0L;
        for (AudioChunk chunk : chunks) {
            if (chunk == null || chunk.offsetMillis() < 0L || chunk.offsetMillis() >= authoritativeAudioDurationMillis) {
                throw new BusinessException(
                    ErrorCode.MEDIA_INPUT_INVALID,
                    "ASR chunk starts outside authoritative audio duration"
                );
            }
            long chunkSizeBytes = readFileSize(chunk.audioFile(), "ASR chunk file size cannot be read");
            minChunkSizeBytes = Math.min(minChunkSizeBytes, chunkSizeBytes);
            maxChunkSizeBytes = Math.max(maxChunkSizeBytes, chunkSizeBytes);
            if (maxChunkBytes > 0L && chunkSizeBytes > maxChunkBytes) {
                throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, "ASR chunk file exceeds configured limit");
            }
        }
        return new ChunkSizeStats(minChunkSizeBytes, maxChunkSizeBytes);
    }

    private SpeechToTextResult mergeChunkResults(
        PipelineAnalysisTaskStepContext context,
        List<SpeechToTextResult> results,
        List<AudioChunk> chunks,
        long authoritativeAudioDurationMillis
    ) {
        List<TranscribedSegment> segments = new ArrayList<>();
        Duration totalDuration = Duration.ZERO;
        long providerReportedDurationMillis = 0L;
        int timelineClampedSegmentCount = 0;
        int timelineDroppedSegmentCount = 0;
        String provider = speechToTextProvider.providerName();
        for (int chunkIndex = 0; chunkIndex < results.size(); chunkIndex++) {
            SpeechToTextResult result = results.get(chunkIndex);
            AudioChunk chunk = chunks.get(chunkIndex);
            if (result == null) {
                throw new IllegalStateException("ASR chunk result is required");
            }
            provider = firstNonBlank(result.provider(), provider);
            totalDuration = totalDuration.plus(result.duration());
            List<TranscribedSegment> chunkSegments = result.segments() == null ? List.of() : result.segments();
            long chunkStartMillis = chunk.offsetMillis();
            long chunkEndMillis = resolveChunkEndMillis(
                chunkIndex,
                chunks,
                authoritativeAudioDurationMillis
            );
            providerReportedDurationMillis = Math.max(
                providerReportedDurationMillis,
                safeAdd(chunkStartMillis, Math.max(0L, result.audioDurationMillis()))
            );
            for (int segmentIndex = 0; segmentIndex < chunkSegments.size(); segmentIndex++) {
                TranscribedSegment segment = chunkSegments.get(segmentIndex);
                boolean segmentHasValidTime = hasValidSegmentTime(segment);
                SegmentTimeRange range = resolveSegmentTimeRange(
                    chunkStartMillis,
                    chunkEndMillis,
                    segment,
                    segmentIndex,
                    chunkSegments.size()
                );
                if (range == null) {
                    timelineDroppedSegmentCount++;
                    continue;
                }
                if (segmentHasValidTime) {
                    long rawStartMillis = safeAdd(chunkStartMillis, segment.startMillis());
                    long rawEndMillis = safeAdd(chunkStartMillis, segment.endMillis());
                    if (range.startMillis() != rawStartMillis || range.endMillis() != rawEndMillis) {
                        timelineClampedSegmentCount++;
                    }
                }
                segments.add(new TranscribedSegment(
                    segments.size(),
                    range.startMillis(),
                    range.endMillis(),
                    segment.text()
                ));
            }
        }
        if (segments.isEmpty()) {
            throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "ASR produced no valid timeline segments");
        }
        String fullText = buildFullText(segments);
        LOGGER.info(
            "ASR timeline bounded: taskId={}, authoritativeAudioDurationMillis={}, providerReportedDurationMillis={}, timelineClampedSegmentCount={}, timelineDroppedSegmentCount={}, chunkCount={}",
            context.taskId(),
            authoritativeAudioDurationMillis,
            providerReportedDurationMillis,
            timelineClampedSegmentCount,
            timelineDroppedSegmentCount,
            chunks.size()
        );
        return new SpeechToTextResult(
            provider,
            context.targetLanguage(),
            fullText,
            segments,
            totalDuration,
            authoritativeAudioDurationMillis,
            Map.of("chunkCount", chunks.size(), "chunkDurationSeconds", chunkingProperties.getChunkDuration().toSeconds())
        );
    }

    private long resolveChunkEndMillis(
        int chunkIndex,
        List<AudioChunk> chunks,
        long authoritativeAudioDurationMillis
    ) {
        AudioChunk chunk = chunks.get(chunkIndex);
        if (chunkIndex + 1 < chunks.size()) {
            return Math.min(chunks.get(chunkIndex + 1).offsetMillis(), authoritativeAudioDurationMillis);
        }
        return authoritativeAudioDurationMillis;
    }

    private static SegmentTimeRange resolveSegmentTimeRange(
        long chunkStartMillis,
        long chunkEndMillis,
        TranscribedSegment segment,
        int segmentIndex,
        int segmentCount
    ) {
        if (hasValidSegmentTime(segment)) {
            long startMillis = Math.max(chunkStartMillis, safeAdd(chunkStartMillis, segment.startMillis()));
            long endMillis = Math.min(chunkEndMillis, safeAdd(chunkStartMillis, segment.endMillis()));
            return startMillis < chunkEndMillis && endMillis > startMillis
                ? new SegmentTimeRange(startMillis, endMillis)
                : null;
        }
        long chunkDurationMillis = Math.max(1L, chunkEndMillis - chunkStartMillis);
        int safeSegmentCount = Math.max(1, segmentCount);
        long startMillis = chunkStartMillis + Math.floorDiv(chunkDurationMillis * segmentIndex, safeSegmentCount);
        long endMillis = chunkStartMillis + Math.floorDiv(chunkDurationMillis * (segmentIndex + 1), safeSegmentCount);
        return new SegmentTimeRange(startMillis, Math.max(startMillis + 1L, endMillis));
    }

    private SpeechToTextResult clampSingleResult(
        PipelineAnalysisTaskStepContext context,
        SpeechToTextResult result,
        long authoritativeAudioDurationMillis
    ) {
        if (result == null) {
            throw new IllegalStateException("ASR result is required");
        }
        List<TranscribedSegment> source = result.segments() == null ? List.of() : result.segments();
        List<TranscribedSegment> bounded = new ArrayList<>();
        int clamped = 0;
        int dropped = 0;
        for (int index = 0; index < source.size(); index++) {
            TranscribedSegment segment = source.get(index);
            SegmentTimeRange range = resolveSegmentTimeRange(
                0L,
                authoritativeAudioDurationMillis,
                segment,
                index,
                source.size()
            );
            if (range == null) {
                dropped++;
                continue;
            }
            if (hasValidSegmentTime(segment)
                && (range.startMillis() != segment.startMillis() || range.endMillis() != segment.endMillis())) {
                clamped++;
            }
            bounded.add(new TranscribedSegment(
                bounded.size(),
                range.startMillis(),
                range.endMillis(),
                segment.text()
            ));
        }
        if (bounded.isEmpty()) {
            throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "ASR produced no valid timeline segments");
        }
        LOGGER.info(
            "ASR timeline bounded: taskId={}, authoritativeAudioDurationMillis={}, providerReportedDurationMillis={}, timelineClampedSegmentCount={}, timelineDroppedSegmentCount={}, chunkCount={}",
            context.taskId(),
            authoritativeAudioDurationMillis,
            result.audioDurationMillis(),
            clamped,
            dropped,
            1
        );
        return new SpeechToTextResult(
            result.provider(),
            result.language(),
            buildFullText(bounded),
            bounded,
            result.duration(),
            authoritativeAudioDurationMillis,
            result.metadata()
        );
    }

    TranscribeAudioStep(
        SpeechToTextProvider speechToTextProvider,
        AudioChunker audioChunker,
        AsrChunkingProperties chunkingProperties,
        PipelineRunnerWorkspace workspace,
        AnalysisTaskMapper analysisTaskMapper,
        TaskProgressSnapshotService progressSnapshotService,
        TaskClaimService taskClaimService,
        AudioDurationProbe audioDurationProbe
    ) {
        this(
            speechToTextProvider,
            audioChunker,
            chunkingProperties,
            workspace,
            analysisTaskMapper,
            progressSnapshotService,
            taskClaimService,
            NOOP_CHUNK_COMPLETION_OBSERVER,
            audioDurationProbe
        );
    }

    private static long safeAdd(long left, long right) {
        if (right > 0L && left > Long.MAX_VALUE - right) {
            return Long.MAX_VALUE;
        }
        return left + right;
    }

    private static boolean hasValidSegmentTime(TranscribedSegment segment) {
        return segment != null && segment.startMillis() >= 0L && segment.endMillis() > segment.startMillis();
    }

    private void ensureTaskStillRunning(PipelineAnalysisTaskStepContext context) {
        if (analysisTaskMapper == null) {
            return;
        }
        AnalysisTask task = analysisTaskMapper.selectByIdAndUserId(context.taskId(), context.userId());
        if (task == null) {
            throw new BusinessException(ErrorCode.TASK_NOT_FOUND);
        }
        AnalysisTaskStatus status = AnalysisTaskStatus.fromDatabaseValue(task.getStatus());
        if (status == AnalysisTaskStatus.CANCELED) {
            throw new BusinessException(ErrorCode.TASK_INVALID_STATUS, "Analysis task was canceled before ASR chunk processing");
        }
    }

    private void updateAsrProgress(
        PipelineAnalysisTaskStepContext context,
        int completedChunks,
        int totalChunks,
        int currentChunkIndex
    ) {
        if (totalChunks <= 0) {
            return;
        }
        int progress = ASR_PROGRESS_START
            + (int) Math.floor((ASR_PROGRESS_END - ASR_PROGRESS_START) * (completedChunks / (double) totalChunks));
        int normalizedProgress = Math.min(ASR_PROGRESS_END, Math.max(ASR_PROGRESS_START, progress));
        if (analysisTaskMapper != null) {
            int updated = analysisTaskMapper.updateRunningProgressByIdAndUserId(
                context.taskId(),
                context.userId(),
                normalizedProgress,
                AnalysisTaskStage.ASR.name()
            );
            if (updated != 1) {
                return;
            }
        }
        updateAsrProgressSnapshot(context, completedChunks, totalChunks, currentChunkIndex, normalizedProgress);
    }

    private void updateAsrProgressSnapshot(
        PipelineAnalysisTaskStepContext context,
        int completedChunks,
        int totalChunks,
        int currentChunkIndex,
        int normalizedProgress
    ) {
        try {
            progressSnapshotService.save(new TaskProgressSnapshot(
                context.taskId(),
                AnalysisTaskStatus.RUNNING.name(),
                normalizedProgress,
                AnalysisTaskStage.ASR.name(),
                null,
                null,
                Instant.now(),
                completedChunks,
                totalChunks,
                currentChunkIndex,
                "语音转文字中：已完成 %d / %d 段".formatted(completedChunks, totalChunks)
            ));
        } catch (RuntimeException exception) {
            LOGGER.warn(
                "ASR progress snapshot update failed: taskId={}, chunkIndex={}/{}, errorType={}",
                SafeLogSanitizer.sanitize(context.taskId()),
                currentChunkIndex,
                totalChunks,
                exception.getClass().getSimpleName()
            );
        }
    }

    private void refreshClaim(PipelineAnalysisTaskStepContext context, String reason) {
        try {
            boolean refreshed = taskClaimService.refresh(context.taskId(), context.requestId());
            if (!refreshed) {
                LOGGER.warn(
                    "ASR task claim refresh skipped: taskId={}, reason={}",
                    SafeLogSanitizer.sanitize(context.taskId()),
                    SafeLogSanitizer.sanitize(reason)
                );
            }
        } catch (RuntimeException exception) {
            LOGGER.warn(
                "ASR task claim refresh failed: taskId={}, reason={}, errorType={}",
                SafeLogSanitizer.sanitize(context.taskId()),
                SafeLogSanitizer.sanitize(reason),
                exception.getClass().getSimpleName()
            );
        }
    }

    private static BusinessException sanitizedChunkFailure(
        PipelineAnalysisTaskStepContext context,
        int chunkNumber,
        int totalChunks,
        RuntimeException exception
    ) {
        String reason = SafeLogSanitizer.sanitizeAndLimit(exception.getMessage(), 255);
        String message = "ASR chunk failed: taskId=%s, chunkIndex=%d/%d, reason=%s".formatted(
            SafeLogSanitizer.sanitize(context.taskId()),
            chunkNumber,
            totalChunks,
            reason == null || reason.isBlank() ? exception.getClass().getSimpleName() : reason
        );
        return new BusinessException(ErrorCode.AI_PROVIDER_FAILED, message, exception);
    }

    private static String buildFullText(List<TranscribedSegment> segments) {
        String text = segments.stream()
            .sorted(Comparator.comparingLong(TranscribedSegment::startMillis))
            .map(TranscribedSegment::text)
            .filter(value -> value != null && !value.isBlank())
            .map(value -> value.replaceAll("\\s+", " ").strip())
            .reduce("", (left, right) -> left.isBlank() ? right : left + "\n\n" + right);
        return text.strip();
    }

    private static void deleteDirectoryQuietly(Path directory) {
        if (directory == null || !Files.exists(directory)) {
            return;
        }
        try (var paths = Files.walk(directory)) {
            for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                Files.deleteIfExists(path);
            }
        } catch (IOException ignored) {
            // Best effort cleanup for temporary ASR chunks.
        }
    }

    private static Long durationMillis(Duration duration, long startedNanos) {
        if (duration == null || duration.isNegative()) {
            return elapsedMillis(startedNanos);
        }
        return duration.toMillis();
    }

    private static long elapsedMillis(long startedNanos) {
        return Duration.ofNanos(System.nanoTime() - startedNanos).toMillis();
    }

    private static Integer millisToSeconds(long millis) {
        if (millis < 0) {
            return null;
        }
        return Math.toIntExact(Math.min(Integer.MAX_VALUE, Math.max(1L, (millis + 999L) / 1000L)));
    }

    private static String firstNonBlank(String first, String fallback) {
        return first == null || first.isBlank() ? fallback : first;
    }

    private record ChunkSizeStats(long minChunkSizeBytes, long maxChunkSizeBytes) {
    }

    private record SegmentTimeRange(long startMillis, long endMillis) {
    }

    private record AsrRetryFailure(boolean retryable, String failureType, Integer httpStatus) {
    }

    private record ChunkTranscriptionResult(
        int chunkIndex,
        long offsetMillis,
        SpeechToTextResult result
    ) {
    }

    private static final class AsrChunkThreadFactory implements ThreadFactory {

        private final String taskId;
        private final AtomicInteger nextIndex = new AtomicInteger(1);

        private AsrChunkThreadFactory(String taskId) {
            this.taskId = SafeLogSanitizer.sanitize(taskId);
        }

        @Override
        public Thread newThread(Runnable runnable) {
            Thread thread = new Thread(runnable);
            thread.setName("courselingo-asr-chunk-" + taskId + "-" + nextIndex.getAndIncrement());
            thread.setDaemon(true);
            return thread;
        }
    }
}
