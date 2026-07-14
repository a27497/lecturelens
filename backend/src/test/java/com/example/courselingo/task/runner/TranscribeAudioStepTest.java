package com.example.courselingo.task.runner;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.courselingo.ai.record.domain.AiCallStage;
import com.example.courselingo.ai.record.domain.AiCallType;
import com.example.courselingo.ai.asr.SiliconFlowAsrException;
import com.example.courselingo.ai.asr.SpeechToTextProvider;
import com.example.courselingo.ai.asr.SpeechToTextRequest;
import com.example.courselingo.ai.asr.SpeechToTextResult;
import com.example.courselingo.ai.asr.TranscribedSegment;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.media.AudioChunk;
import com.example.courselingo.media.AudioChunker;
import com.example.courselingo.media.AudioDurationProbe;
import com.example.courselingo.media.AudioExtractionResult;
import com.example.courselingo.task.claim.TaskClaimResult;
import com.example.courselingo.task.claim.TaskClaimService;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.task.model.AnalysisTaskStatus;
import com.example.courselingo.task.progress.TaskProgressSnapshot;
import com.example.courselingo.task.progress.TaskProgressSnapshotService;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.util.unit.DataSize;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.times;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.eq;

import org.mockito.InOrder;

class TranscribeAudioStepTest {

    @TempDir
    private Path tempDir;

    @Test
    void transcribeSingleAudioClampsProviderTimelineToAuthoritativeDuration() throws Exception {
        Path audioFile = Files.writeString(tempDir.resolve("single.wav"), "audio");
        SpeechToTextResult providerResult = new SpeechToTextResult(
            "fake-asr",
            "en",
            "bounded",
            List.of(new TranscribedSegment(9, 0L, 5_000L, "bounded")),
            Duration.ofMillis(10),
            6_000L,
            Map.of()
        );
        PipelineAnalysisTaskStepContext context = context();
        context.setAudioExtractionResult(new AudioExtractionResult(audioFile, "wav", 16000, 1));

        new TranscribeAudioStep(
            new FakeSpeechToTextProvider(new AtomicReference<>(), providerResult),
            authoritativeDuration(3_000L)
        ).execute(context);

        SpeechToTextResult result = context.requireSpeechToTextResult();
        assertThat(result.audioDurationMillis()).isEqualTo(3_000L);
        assertThat(result.segments()).singleElement().satisfies(segment -> {
            assertThat(segment.index()).isZero();
            assertThat(segment.startMillis()).isZero();
            assertThat(segment.endMillis()).isEqualTo(3_000L);
        });
        assertThat(context.pendingAiCallRecords()).singleElement()
            .satisfies(record -> assertThat(record.inputUnits()).isEqualTo(3));
    }

    @Test
    void transcribeSixtyEightMinuteAudioUsesAuthoritativeEndInsteadOfSixtyNineFullChunks() throws Exception {
        long authoritativeDurationMillis = 4_090_265L;
        Path audioFile = Files.writeString(tempDir.resolve("long.wav"), "large audio");
        AsrChunkingProperties properties = new AsrChunkingProperties();
        properties.setMaxAudioFileSize(DataSize.ofBytes(1));
        properties.setMaxChunkFileSize(DataSize.ofKilobytes(1));
        properties.setChunkDuration(Duration.ofSeconds(60));
        properties.setMaxChunks(180);
        PipelineAnalysisTaskStepContext context = context();
        context.setAudioExtractionResult(new AudioExtractionResult(audioFile, "wav", 16000, 1));
        PipelineRunnerWorkspace workspace = new PipelineRunnerWorkspace(
            new AnalysisTaskRunnerProperties(tempDir.resolve("runner"))
        );

        new TranscribeAudioStep(
            new FullMinuteChunkSpeechToTextProvider(),
            new ManyAudioChunksChunker(69),
            properties,
            workspace,
            null,
            new RecordingTaskProgressSnapshotService(),
            new RecordingTaskClaimService(),
            ignored -> { },
            authoritativeDuration(authoritativeDurationMillis)
        ).execute(context);

        SpeechToTextResult result = context.requireSpeechToTextResult();
        assertThat(result.audioDurationMillis()).isEqualTo(authoritativeDurationMillis);
        assertThat(result.segments()).hasSize(69);
        assertThat(result.segments()).extracting(TranscribedSegment::index)
            .containsExactlyElementsOf(java.util.stream.IntStream.range(0, 69).boxed().toList());
        assertThat(result.segments().getLast().startMillis()).isEqualTo(4_080_000L);
        assertThat(result.segments().getLast().endMillis()).isEqualTo(authoritativeDurationMillis);
        assertThat(result.segments()).allSatisfy(segment -> {
            assertThat(segment.startMillis()).isNotNegative();
            assertThat(segment.endMillis()).isLessThanOrEqualTo(authoritativeDurationMillis);
            assertThat(segment.endMillis()).isGreaterThan(segment.startMillis());
        });
        assertThat(context.pendingAiCallRecords()).singleElement()
            .satisfies(record -> assertThat(record.inputUnits()).isEqualTo(4_091));
    }

    @Test
    void transcribeDropsSegmentEntirelyAfterAuthoritativeEnd() throws Exception {
        Path audioFile = Files.writeString(tempDir.resolve("after-end.wav"), "audio");
        SpeechToTextResult providerResult = new SpeechToTextResult(
            "fake-asr",
            "en",
            "valid ignored",
            List.of(
                new TranscribedSegment(4, 0L, 1_000L, "valid"),
                new TranscribedSegment(5, 4_000L, 5_000L, "ignored")
            ),
            Duration.ofMillis(10),
            5_000L,
            Map.of()
        );
        PipelineAnalysisTaskStepContext context = context();
        context.setAudioExtractionResult(new AudioExtractionResult(audioFile, "wav", 16000, 1));

        new TranscribeAudioStep(
            new FakeSpeechToTextProvider(new AtomicReference<>(), providerResult),
            authoritativeDuration(3_000L)
        ).execute(context);

        assertThat(context.requireSpeechToTextResult().segments()).singleElement().satisfies(segment -> {
            assertThat(segment.index()).isZero();
            assertThat(segment.text()).isEqualTo("valid");
            assertThat(segment.endMillis()).isEqualTo(1_000L);
        });
    }

    @Test
    void transcribeFailsWhenEveryProviderSegmentIsAfterAuthoritativeEnd() throws Exception {
        Path audioFile = Files.writeString(tempDir.resolve("all-after-end.wav"), "audio");
        SpeechToTextResult providerResult = new SpeechToTextResult(
            "fake-asr",
            "en",
            "ignored",
            List.of(new TranscribedSegment(7, 4_000L, 5_000L, "ignored")),
            Duration.ofMillis(10),
            5_000L,
            Map.of()
        );
        PipelineAnalysisTaskStepContext context = context();
        context.setAudioExtractionResult(new AudioExtractionResult(audioFile, "wav", 16000, 1));

        assertThatThrownBy(() -> new TranscribeAudioStep(
            new FakeSpeechToTextProvider(new AtomicReference<>(), providerResult),
            authoritativeDuration(3_000L)
        ).execute(context))
            .isInstanceOf(BusinessException.class)
            .hasMessageContaining("no valid timeline segments");
    }

    @Test
    void transcribeRejectsChunkStartingAtAuthoritativeEndBeforeProviderCall() throws Exception {
        Path audioFile = Files.writeString(tempDir.resolve("extra-chunk.wav"), "large audio");
        AsrChunkingProperties properties = new AsrChunkingProperties();
        properties.setMaxAudioFileSize(DataSize.ofBytes(1));
        properties.setMaxChunkFileSize(DataSize.ofKilobytes(1));
        properties.setChunkDuration(Duration.ofSeconds(60));
        PipelineAnalysisTaskStepContext context = context();
        context.setAudioExtractionResult(new AudioExtractionResult(audioFile, "wav", 16000, 1));
        PipelineRunnerWorkspace workspace = new PipelineRunnerWorkspace(
            new AnalysisTaskRunnerProperties(tempDir.resolve("runner"))
        );

        assertThatThrownBy(() -> new TranscribeAudioStep(
            new GuardSpeechToTextProvider(),
            new ManyAudioChunksChunker(2),
            properties,
            workspace,
            null,
            authoritativeDuration(60_000L)
        ).execute(context))
            .isInstanceOf(BusinessException.class)
            .hasMessageContaining("outside authoritative audio duration");
    }

    @Test
    void transcribeTenMinuteChunkedAudioKeepsExactAuthoritativeEnd() throws Exception {
        Path audioFile = Files.writeString(tempDir.resolve("ten-minutes.wav"), "large audio");
        AsrChunkingProperties properties = new AsrChunkingProperties();
        properties.setMaxAudioFileSize(DataSize.ofBytes(1));
        properties.setMaxChunkFileSize(DataSize.ofKilobytes(1));
        properties.setChunkDuration(Duration.ofSeconds(60));
        PipelineAnalysisTaskStepContext context = context();
        context.setAudioExtractionResult(new AudioExtractionResult(audioFile, "wav", 16000, 1));
        PipelineRunnerWorkspace workspace = new PipelineRunnerWorkspace(
            new AnalysisTaskRunnerProperties(tempDir.resolve("runner"))
        );

        new TranscribeAudioStep(
            new FullMinuteChunkSpeechToTextProvider(),
            new ManyAudioChunksChunker(10),
            properties,
            workspace,
            null,
            authoritativeDuration(600_000L)
        ).execute(context);

        SpeechToTextResult result = context.requireSpeechToTextResult();
        assertThat(result.audioDurationMillis()).isEqualTo(600_000L);
        assertThat(result.segments()).hasSize(10);
        assertThat(result.segments().getLast().endMillis()).isEqualTo(600_000L);
    }

    @Test
    void transcribeAudioStoresAsrResultWithoutExposingAudioPathOrTextInContext() throws Exception {
        Path audioFile = tempDir.resolve("task_1.wav");
        Files.writeString(audioFile, "audio");
        AtomicReference<SpeechToTextRequest> capturedRequest = new AtomicReference<>();
        SpeechToTextResult result = result();
        SpeechToTextProvider provider = new FakeSpeechToTextProvider(capturedRequest, result);
        PipelineAnalysisTaskStepContext context = context();
        context.setAudioExtractionResult(new AudioExtractionResult(audioFile, "wav", 16000, 1));

        new TranscribeAudioStep(provider, authoritativeDuration(1_200L)).execute(context);

        assertThat(capturedRequest.get().audioFile()).isEqualTo(audioFile);
        assertThat(capturedRequest.get().language()).isEqualTo("zh-CN");
        assertThat(capturedRequest.get().taskId()).isEqualTo("task_1");
        assertThat(capturedRequest.get().requestId()).isEqualTo("req_1");
        assertThat(capturedRequest.get().timeout()).isPositive();
        assertThat(context.speechToTextResult()).contains(result);
        assertThat(context.pendingAiCallRecords()).singleElement().satisfies(record -> {
            assertThat(record.callType()).isEqualTo(AiCallType.ASR);
            assertThat(record.stage()).isEqualTo(AiCallStage.TRANSCRIPTION);
            assertThat(record.provider()).isEqualTo("fake-asr");
            assertThat(record.durationMillis()).isEqualTo(10L);
            assertThat(record.inputUnits()).isEqualTo(2);
            assertThat(record.outputUnits()).isEqualTo(1);
            assertThat(record.errorMessage()).isNull();
        });
        assertThat(context.toString()).doesNotContain(audioFile.toString());
        assertThat(context.toString()).doesNotContain("hello course");
    }

    @Test
    void transcribeAudioAddsSanitizedFailureRecordWhenProviderFails() throws Exception {
        Path audioFile = tempDir.resolve("task_1.wav");
        Files.writeString(audioFile, "audio");
        SpeechToTextProvider provider = new FailingSpeechToTextProvider();
        PipelineAnalysisTaskStepContext context = context();
        context.setAudioExtractionResult(new AudioExtractionResult(audioFile, "wav", 16000, 1));

        assertThatThrownBy(() -> new TranscribeAudioStep(provider, authoritativeDuration(1_200L)).execute(context))
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("Authorization Bearer token")
            .hasMessageContaining("C:\\secret\\audio.wav");

        assertThat(context.pendingAiCallRecords()).singleElement().satisfies(record -> {
            assertThat(record.callType()).isEqualTo(AiCallType.ASR);
            assertThat(record.stage()).isEqualTo(AiCallStage.TRANSCRIPTION);
            assertThat(record.provider()).isEqualTo("fake-asr");
            assertThat(record.errorCode()).isEqualTo("AI_PROVIDER_FAILED");
            assertThat(record.errorMessage()).doesNotContainIgnoringCase("authorization");
            assertThat(record.errorMessage()).doesNotContainIgnoringCase("token");
            assertThat(record.errorMessage()).doesNotContain("C:\\secret");
        });
        assertThat(context.toString()).doesNotContain(audioFile.toString());
        assertThat(context.toString()).doesNotContainIgnoringCase("token");
    }

    @Test
    void transcribeAudioRequiresPriorAudioExtractionResult() {
        TranscribeAudioStep step = new TranscribeAudioStep(new FakeSpeechToTextProvider(new AtomicReference<>(), result()));

        assertThatThrownBy(() -> step.execute(context()))
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("audio extraction result is required")
            .hasMessageNotContaining(windowsDrivePrefix())
            .hasMessageNotContaining(sensitiveWord("object", "Key"))
            .satisfies(error -> assertThat(error.getMessage()).doesNotContainIgnoringCase("token"));
    }

    @Test
    void transcribeLargeAudioSplitsChunksMergesOffsetsReindexesAndCleansTempFiles() throws Exception {
        Path audioFile = tempDir.resolve("large.wav");
        Files.writeString(audioFile, "large audio");
        RecordingSpeechToTextProvider provider = new RecordingSpeechToTextProvider();
        FakeAudioChunker chunker = new FakeAudioChunker();
        AsrChunkingProperties properties = new AsrChunkingProperties();
        properties.setMaxAudioFileSize(DataSize.ofBytes(1));
        properties.setMaxChunkFileSize(DataSize.ofKilobytes(1));
        properties.setChunkDuration(Duration.ofSeconds(600));
        AnalysisTaskMapper taskMapper = mock(AnalysisTaskMapper.class);
        AnalysisTask task = new AnalysisTask();
        task.setId("task_1");
        task.setUserId(7L);
        task.setStatus(AnalysisTaskStatus.RUNNING.name());
        when(taskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task);
        PipelineAnalysisTaskStepContext context = context();
        context.setAudioExtractionResult(new AudioExtractionResult(audioFile, "wav", 16000, 1));
        PipelineRunnerWorkspace workspace = new PipelineRunnerWorkspace(
            new AnalysisTaskRunnerProperties(tempDir.resolve("runner"))
        );

        new TranscribeAudioStep(
            provider,
            chunker,
            properties,
            workspace,
            taskMapper,
            authoritativeDuration(600_600L)
        ).execute(context);

        SpeechToTextResult result = context.requireSpeechToTextResult();
        assertThat(provider.requests).hasSize(2);
        assertThat(provider.requests).noneMatch(request -> request.audioFile().equals(audioFile));
        assertThat(result.fullText()).isEqualTo("chunk zero\n\nchunk one");
        assertThat(result.segments()).extracting(TranscribedSegment::index).containsExactly(0, 1);
        assertThat(result.segments()).extracting(TranscribedSegment::startMillis).containsExactly(0L, 600_100L);
        assertThat(result.segments()).extracting(TranscribedSegment::endMillis).containsExactly(500L, 600_600L);
        assertThat(result.audioDurationMillis()).isEqualTo(600_600L);
        assertThat(chunker.outputDirectory).doesNotExist();
        verify(taskMapper, times(4)).updateRunningProgressByIdAndUserId(
            org.mockito.Mockito.eq("task_1"),
            org.mockito.Mockito.eq(7L),
            org.mockito.Mockito.anyInt(),
            org.mockito.Mockito.eq("ASR")
        );
    }

    @Test
    void asrSnapshotsFollowSuccessfulMysqlProgressUpdates() throws Exception {
        AnalysisTaskMapper taskMapper = runningTaskMapper();
        TaskProgressSnapshotService snapshotService = mock(TaskProgressSnapshotService.class);
        when(taskMapper.updateRunningProgressByIdAndUserId(eq("task_1"), eq(7L), anyInt(), eq("ASR")))
            .thenReturn(1);

        executeSingleChunkWithProgress(taskMapper, snapshotService);

        InOrder order = inOrder(taskMapper, snapshotService);
        order.verify(taskMapper).updateRunningProgressByIdAndUserId("task_1", 7L, 20, "ASR");
        order.verify(snapshotService).save(any(TaskProgressSnapshot.class));
        order.verify(taskMapper).updateRunningProgressByIdAndUserId("task_1", 7L, 55, "ASR");
        order.verify(snapshotService).save(any(TaskProgressSnapshot.class));
    }

    @Test
    void deletedOrNonRunningTaskSkipsBothAsrSnapshotsWhenMysqlUpdatesNoRows() throws Exception {
        AnalysisTaskMapper taskMapper = runningTaskMapper();
        TaskProgressSnapshotService snapshotService = mock(TaskProgressSnapshotService.class);
        when(taskMapper.updateRunningProgressByIdAndUserId(eq("task_1"), eq(7L), anyInt(), eq("ASR")))
            .thenReturn(0);

        executeSingleChunkWithProgress(taskMapper, snapshotService);

        verify(taskMapper, times(2)).updateRunningProgressByIdAndUserId(
            eq("task_1"),
            eq(7L),
            anyInt(),
            eq("ASR")
        );
        verify(snapshotService, never()).save(any(TaskProgressSnapshot.class));
    }

    @Test
    void mysqlProgressFailurePropagatesWithoutWritingAsrSnapshot() throws Exception {
        AnalysisTaskMapper taskMapper = runningTaskMapper();
        TaskProgressSnapshotService snapshotService = mock(TaskProgressSnapshotService.class);
        doThrow(new IllegalStateException("fixture database unavailable"))
            .when(taskMapper)
            .updateRunningProgressByIdAndUserId(eq("task_1"), eq(7L), anyInt(), eq("ASR"));

        assertThatThrownBy(() -> executeSingleChunkWithProgress(taskMapper, snapshotService))
            .isInstanceOf(RuntimeException.class);

        verify(snapshotService, never()).save(any(TaskProgressSnapshot.class));
    }

    @Test
    void mapperlessCompatibilityPathKeepsAsrSnapshots() throws Exception {
        TaskProgressSnapshotService snapshotService = mock(TaskProgressSnapshotService.class);

        executeSingleChunkWithProgress(null, snapshotService);

        verify(snapshotService, times(2)).save(any(TaskProgressSnapshot.class));
    }

    @Test
    void transcribeLargeAudioRunsChunksConcurrentlyAndMergesByChunkIndex() throws Exception {
        Path audioFile = tempDir.resolve("large-concurrent.wav");
        Files.writeString(audioFile, "large audio");
        CountDownLatch releaseChunkZero = new CountDownLatch(1);
        List<Integer> collectedCompletionOrder = new CopyOnWriteArrayList<>();
        CoordinatedConcurrentSpeechToTextProvider provider =
            new CoordinatedConcurrentSpeechToTextProvider(releaseChunkZero);
        FakeAudioChunker chunker = new FakeAudioChunker();
        AsrChunkingProperties properties = new AsrChunkingProperties();
        properties.setMaxAudioFileSize(DataSize.ofBytes(1));
        properties.setMaxChunkFileSize(DataSize.ofKilobytes(1));
        properties.setChunkDuration(Duration.ofSeconds(600));
        properties.setConcurrency(2);
        properties.setMaxConcurrency(4);
        RecordingTaskProgressSnapshotService progressSnapshots = new RecordingTaskProgressSnapshotService();
        RecordingTaskClaimService claimService = new RecordingTaskClaimService();
        AnalysisTaskMapper taskMapper = runningTaskMapper();
        PipelineAnalysisTaskStepContext context = context();
        context.setAudioExtractionResult(new AudioExtractionResult(audioFile, "wav", 16000, 1));
        PipelineRunnerWorkspace workspace = new PipelineRunnerWorkspace(
            new AnalysisTaskRunnerProperties(tempDir.resolve("runner"))
        );

        new TranscribeAudioStep(
            provider,
            chunker,
            properties,
            workspace,
            taskMapper,
            progressSnapshots,
            claimService,
            chunkIndex -> {
                collectedCompletionOrder.add(chunkIndex);
                if (chunkIndex == 1) {
                    releaseChunkZero.countDown();
                }
            },
            authoritativeDuration(600_700L)
        ).execute(context);

        SpeechToTextResult result = context.requireSpeechToTextResult();
        assertThat(provider.maxActive.get()).isGreaterThan(1);
        assertThat(provider.startedChunkIndexes).containsExactly(0, 1);
        assertThat(collectedCompletionOrder).containsExactly(1, 0);
        assertThat(result.fullText()).isEqualTo("chunk zero\n\nchunk one");
        assertThat(result.segments()).extracting(TranscribedSegment::text).containsExactly("chunk zero", "chunk one");
        assertThat(progressSnapshots.snapshots)
            .anySatisfy(snapshot -> {
                assertThat(snapshot.completedChunks()).isEqualTo(0);
                assertThat(snapshot.totalChunks()).isEqualTo(2);
                assertThat(snapshot.currentChunkIndex()).isIn(1, 2);
                assertThat(snapshot.stepDetail()).contains("0 / 2");
            })
            .anySatisfy(snapshot -> {
                assertThat(snapshot.completedChunks()).isEqualTo(2);
                assertThat(snapshot.totalChunks()).isEqualTo(2);
                assertThat(snapshot.stepDetail()).contains("2 / 2");
            });
        assertThat(claimService.refreshCalls).isNotEmpty();
        assertThat(claimService.refreshCalls).allMatch(call -> call.equals("task_1:req_1"));
    }

    @Test
    void transcribeChunkFailureIncludesChunkIndexAndSanitizesSensitiveDetails() throws Exception {
        Path audioFile = tempDir.resolve("large-failing-sensitive.wav");
        Files.writeString(audioFile, "large audio");
        AsrChunkingProperties properties = retryableChunkingProperties();
        properties.getChunkRetry().setMaxAttempts(1);
        PipelineAnalysisTaskStepContext context = context();
        context.setAudioExtractionResult(new AudioExtractionResult(audioFile, "wav", 16000, 1));
        PipelineRunnerWorkspace workspace = new PipelineRunnerWorkspace(
            new AnalysisTaskRunnerProperties(tempDir.resolve("runner"))
        );

        assertThatThrownBy(() -> new TranscribeAudioStep(
            new SensitiveFailingChunkSpeechToTextProvider(),
            new FakeAudioChunker(),
            properties,
            workspace,
            runningTaskMapper(),
            new RecordingTaskProgressSnapshotService(),
            new RecordingTaskClaimService(),
            authoritativeDuration(1_200_000L)
        ).execute(context))
            .hasMessageContaining("chunkIndex=")
            .hasMessageContaining("/2")
            .hasMessageNotContaining(windowsDrivePrefix())
            .hasMessageNotContaining(sensitiveWord("object", "Key"))
            .satisfies(error -> {
                assertThat(error.getMessage()).doesNotContainIgnoringCase(sensitiveWord("to", "ken"));
                assertThat(error.getMessage()).doesNotContainIgnoringCase(sensitiveWord("api ", "key"));
            });
    }

    @Test
    void asrChunkConcurrencyIsClampedToSafeBounds() {
        AsrChunkingProperties properties = new AsrChunkingProperties();

        properties.setConcurrency(0);
        properties.setMaxConcurrency(4);
        assertThat(properties.effectiveConcurrency()).isEqualTo(1);

        properties.setConcurrency(12);
        properties.setMaxConcurrency(12);
        assertThat(properties.effectiveConcurrency()).isEqualTo(4);
    }

    @Test
    void transcribeTwoHourAudioStaysWithinRecommendedChunkLimit() throws Exception {
        Path audioFile = tempDir.resolve("two-hour-course.wav");
        Files.writeString(audioFile, "large audio");
        RecordingSpeechToTextProvider provider = new RecordingSpeechToTextProvider();
        ManyAudioChunksChunker chunker = new ManyAudioChunksChunker(120);
        AsrChunkingProperties properties = new AsrChunkingProperties();
        properties.setMaxAudioFileSize(DataSize.ofBytes(1));
        properties.setMaxChunkFileSize(DataSize.ofKilobytes(1));
        properties.setChunkDuration(Duration.ofSeconds(60));
        properties.setMaxChunks(180);
        PipelineAnalysisTaskStepContext context = context();
        context.setAudioExtractionResult(new AudioExtractionResult(audioFile, "wav", 16000, 1));
        PipelineRunnerWorkspace workspace = new PipelineRunnerWorkspace(
            new AnalysisTaskRunnerProperties(tempDir.resolve("runner"))
        );

        new TranscribeAudioStep(
            provider,
            chunker,
            properties,
            workspace,
            null,
            authoritativeDuration(7_200_000L)
        ).execute(context);

        assertThat(provider.requests).hasSize(120);
        assertThat(context.requireSpeechToTextResult().metadata())
            .containsEntry("chunkCount", 120)
            .containsEntry("chunkDurationSeconds", 60L);
    }

    @Test
    void transcribeLargeAudioRejectsChunkCountWithFriendlyMessage() throws Exception {
        Path audioFile = tempDir.resolve("too-many-chunks.wav");
        Files.writeString(audioFile, "large audio");
        AsrChunkingProperties properties = new AsrChunkingProperties();
        properties.setMaxAudioFileSize(DataSize.ofBytes(1));
        properties.setMaxChunkFileSize(DataSize.ofKilobytes(1));
        properties.setChunkDuration(Duration.ofSeconds(60));
        properties.setMaxChunks(180);
        PipelineAnalysisTaskStepContext context = context();
        context.setAudioExtractionResult(new AudioExtractionResult(audioFile, "wav", 16000, 1));
        PipelineRunnerWorkspace workspace = new PipelineRunnerWorkspace(
            new AnalysisTaskRunnerProperties(tempDir.resolve("runner"))
        );

        assertThatThrownBy(() -> new TranscribeAudioStep(
            new GuardSpeechToTextProvider(),
            new ManyAudioChunksChunker(181),
            properties,
            workspace,
            null,
            authoritativeDuration(10_860_000L)
        ).execute(context))
            .isInstanceOf(BusinessException.class)
            .hasMessageContaining("视频语音转写分片数量超过当前上限")
            .hasMessageContaining("ASR_CHUNK_MAX_CHUNKS");
    }

    @Test
    void transcribeChunkRetriesRetryable502AndContinues() throws Exception {
        Path audioFile = tempDir.resolve("large-retryable.wav");
        Files.writeString(audioFile, "large audio");
        FailOnceRetryableSpeechToTextProvider provider = new FailOnceRetryableSpeechToTextProvider();
        FakeAudioChunker chunker = new FakeAudioChunker();
        AsrChunkingProperties properties = retryableChunkingProperties();
        PipelineAnalysisTaskStepContext context = context();
        context.setAudioExtractionResult(new AudioExtractionResult(audioFile, "wav", 16000, 1));
        PipelineRunnerWorkspace workspace = new PipelineRunnerWorkspace(
            new AnalysisTaskRunnerProperties(tempDir.resolve("runner"))
        );

        new TranscribeAudioStep(
            provider,
            chunker,
            properties,
            workspace,
            null,
            authoritativeDuration(600_700L)
        ).execute(context);

        SpeechToTextResult result = context.requireSpeechToTextResult();
        assertThat(provider.requests).hasSize(3);
        assertThat(provider.firstChunkAttempts.get()).isEqualTo(2);
        assertThat(result.fullText()).isEqualTo("chunk zero\n\nchunk one");
        assertThat(result.segments()).extracting(TranscribedSegment::index).containsExactly(0, 1);
    }

    @Test
    void transcribeChunkFailsAfterRetryable502AttemptsAreExhausted() throws Exception {
        Path audioFile = tempDir.resolve("large-retry-exhausted.wav");
        Files.writeString(audioFile, "large audio");
        AlwaysRetryableSpeechToTextProvider provider = new AlwaysRetryableSpeechToTextProvider();
        ManyAudioChunksChunker chunker = new ManyAudioChunksChunker(1);
        AsrChunkingProperties properties = retryableChunkingProperties();
        PipelineAnalysisTaskStepContext context = context();
        context.setAudioExtractionResult(new AudioExtractionResult(audioFile, "wav", 16000, 1));
        PipelineRunnerWorkspace workspace = new PipelineRunnerWorkspace(
            new AnalysisTaskRunnerProperties(tempDir.resolve("runner"))
        );

        assertThatThrownBy(() -> new TranscribeAudioStep(
            provider, chunker, properties, workspace, null, authoritativeDuration(600_000L))
            .execute(context))
            .isInstanceOf(BusinessException.class)
            .hasMessageContaining("chunkIndex=")
            .hasMessageContaining("HTTP 502");

        Map<String, Long> attemptsByChunk = requestCountsByChunkFile(provider.requests);
        assertThat(attemptsByChunk).isEqualTo(Map.of("chunk-000.wav", 3L));
        assertThat(context.speechToTextResult()).isEmpty();
    }

    @Test
    void transcribeChunkDoesNotRetryUnauthorizedProviderFailures() throws Exception {
        Path audioFile = tempDir.resolve("large-unauthorized.wav");
        Files.writeString(audioFile, "large audio");
        AlwaysUnauthorizedSpeechToTextProvider provider = new AlwaysUnauthorizedSpeechToTextProvider();
        FakeAudioChunker chunker = new FakeAudioChunker();
        AsrChunkingProperties properties = retryableChunkingProperties();
        PipelineAnalysisTaskStepContext context = context();
        context.setAudioExtractionResult(new AudioExtractionResult(audioFile, "wav", 16000, 1));
        PipelineRunnerWorkspace workspace = new PipelineRunnerWorkspace(
            new AnalysisTaskRunnerProperties(tempDir.resolve("runner"))
        );

        assertThatThrownBy(() -> new TranscribeAudioStep(
            provider, chunker, properties, workspace, null, authoritativeDuration(1_200_000L))
            .execute(context))
            .isInstanceOf(BusinessException.class)
            .hasMessageContaining("chunkIndex=")
            .hasMessageContaining("HTTP 401");

        Map<String, Long> attemptsByChunk = requestCountsByChunkFile(provider.requests);
        assertThat(attemptsByChunk)
            .isNotEmpty()
            .allSatisfy((chunkName, attempts) -> {
                assertThat(chunkName).isIn("chunk-000.wav", "chunk-001.wav");
                assertThat(attempts).isEqualTo(1L);
            });
    }

    @Test
    void transcribeChunkDoesNotRetryProvider400Or403Failures() throws Exception {
        for (int statusCode : List.of(400, 403)) {
            Path audioFile = tempDir.resolve("large-non-retryable-%d.wav".formatted(statusCode));
            Files.writeString(audioFile, "large audio");
            StatusCodeFailingSpeechToTextProvider provider = new StatusCodeFailingSpeechToTextProvider(statusCode);
            FakeAudioChunker chunker = new FakeAudioChunker();
            AsrChunkingProperties properties = retryableChunkingProperties();
            PipelineAnalysisTaskStepContext context = context();
            context.setAudioExtractionResult(new AudioExtractionResult(audioFile, "wav", 16000, 1));
            PipelineRunnerWorkspace workspace = new PipelineRunnerWorkspace(
                new AnalysisTaskRunnerProperties(tempDir.resolve("runner-%d".formatted(statusCode)))
            );

            assertThatThrownBy(() -> new TranscribeAudioStep(
                provider, chunker, properties, workspace, null, authoritativeDuration(1_200_000L))
                .execute(context))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("chunkIndex=")
                .hasMessageContaining("HTTP " + statusCode);

            Map<String, Long> attemptsByChunk = requestCountsByChunkFile(provider.requests);
            assertThat(attemptsByChunk)
                .isNotEmpty()
                .allSatisfy((chunkName, attempts) -> {
                    assertThat(chunkName).isIn("chunk-000.wav", "chunk-001.wav");
                    assertThat(attempts).isEqualTo(1L);
                });
        }
    }

    @Test
    void transcribeChunkDoesNotRetryAudioLimitFailures() throws Exception {
        Path audioFile = tempDir.resolve("large-audio-limit.wav");
        Files.writeString(audioFile, "large audio");
        AudioLimitFailureSpeechToTextProvider provider = new AudioLimitFailureSpeechToTextProvider();
        ManyAudioChunksChunker chunker = new ManyAudioChunksChunker(1);
        AsrChunkingProperties properties = retryableChunkingProperties();
        PipelineAnalysisTaskStepContext context = context();
        context.setAudioExtractionResult(new AudioExtractionResult(audioFile, "wav", 16000, 1));
        PipelineRunnerWorkspace workspace = new PipelineRunnerWorkspace(
            new AnalysisTaskRunnerProperties(tempDir.resolve("runner"))
        );

        assertThatThrownBy(() -> new TranscribeAudioStep(
            provider, chunker, properties, workspace, null, authoritativeDuration(1_200_000L))
            .execute(context))
            .isInstanceOf(BusinessException.class)
            .hasMessageContaining("chunkIndex=")
            .hasMessageContaining("audio file exceeds configured limit");

        assertThat(provider.requests).singleElement().satisfies(request ->
            assertThat(request.audioFile().getFileName().toString()).isEqualTo("chunk-000.wav")
        );
    }

    @Test
    void transcribeChunkedAudioUsesChunkRangesWhenProviderReturnsPointTimestamps() throws Exception {
        Path audioFile = tempDir.resolve("large-zero-timestamps.wav");
        Files.writeString(audioFile, "large audio");
        PointTimestampSpeechToTextProvider provider = new PointTimestampSpeechToTextProvider();
        FakeAudioChunker chunker = new FakeAudioChunker();
        AsrChunkingProperties properties = new AsrChunkingProperties();
        properties.setMaxAudioFileSize(DataSize.ofBytes(1));
        properties.setMaxChunkFileSize(DataSize.ofKilobytes(1));
        properties.setChunkDuration(Duration.ofSeconds(600));
        PipelineAnalysisTaskStepContext context = context();
        context.setAudioExtractionResult(new AudioExtractionResult(audioFile, "wav", 16000, 1));
        PipelineRunnerWorkspace workspace = new PipelineRunnerWorkspace(
            new AnalysisTaskRunnerProperties(tempDir.resolve("runner"))
        );

        new TranscribeAudioStep(
            provider, chunker, properties, workspace, null, authoritativeDuration(609_000L)
        ).execute(context);

        SpeechToTextResult result = context.requireSpeechToTextResult();
        assertThat(result.segments()).extracting(TranscribedSegment::index).containsExactly(0, 1);
        assertThat(result.segments()).extracting(TranscribedSegment::startMillis).containsExactly(0L, 600_000L);
        assertThat(result.segments()).extracting(TranscribedSegment::endMillis).containsExactly(600_000L, 609_000L);
    }

    @Test
    void transcribeSmallAudioUsesSingleFileAsr() throws Exception {
        Path audioFile = tempDir.resolve("small.wav");
        Files.writeString(audioFile, "small audio");
        RecordingSpeechToTextProvider provider = new RecordingSpeechToTextProvider();
        FakeAudioChunker chunker = new FakeAudioChunker();
        AsrChunkingProperties properties = new AsrChunkingProperties();
        properties.setMaxAudioFileSize(DataSize.ofMegabytes(1));
        PipelineAnalysisTaskStepContext context = context();
        context.setAudioExtractionResult(new AudioExtractionResult(audioFile, "wav", 16000, 1));
        PipelineRunnerWorkspace workspace = new PipelineRunnerWorkspace(
            new AnalysisTaskRunnerProperties(tempDir.resolve("runner"))
        );

        new TranscribeAudioStep(
            provider, chunker, properties, workspace, null, authoritativeDuration(1_200L)
        ).execute(context);

        assertThat(provider.requests).singleElement()
            .satisfies(request -> assertThat(request.audioFile()).isEqualTo(audioFile));
        assertThat(chunker.outputDirectory).isNull();
    }

    @Test
    void transcribeLargeAudioFailsBeforeProviderWhenChunkingIsDisabled() throws Exception {
        Path audioFile = tempDir.resolve("large-disabled.wav");
        Files.writeString(audioFile, "large audio");
        AsrChunkingProperties properties = new AsrChunkingProperties();
        properties.setEnabled(false);
        properties.setMaxAudioFileSize(DataSize.ofBytes(1));
        PipelineAnalysisTaskStepContext context = context();
        context.setAudioExtractionResult(new AudioExtractionResult(audioFile, "wav", 16000, 1));

        assertThatThrownBy(() -> new TranscribeAudioStep(
            new GuardSpeechToTextProvider(), null, properties, null, null, authoritativeDuration(1_200L))
            .execute(context))
            .isInstanceOf(BusinessException.class)
            .hasMessageContaining("ASR chunking disabled");
    }

    @Test
    void transcribeLargeAudioFailsBeforeProviderWhenChunkingInfrastructureIsMissing() throws Exception {
        Path audioFile = tempDir.resolve("large-missing-infra.wav");
        Files.writeString(audioFile, "large audio");
        AsrChunkingProperties properties = new AsrChunkingProperties();
        properties.setMaxAudioFileSize(DataSize.ofBytes(1));
        PipelineAnalysisTaskStepContext context = context();
        context.setAudioExtractionResult(new AudioExtractionResult(audioFile, "wav", 16000, 1));

        assertThatThrownBy(() -> new TranscribeAudioStep(
            new GuardSpeechToTextProvider(), null, properties, null, null, authoritativeDuration(1_200L))
            .execute(context))
            .isInstanceOf(BusinessException.class)
            .hasMessageContaining("ASR chunking is not configured");
    }

    @Test
    void transcribeLargeAudioRejectsOversizedChunkBeforeProviderCall() throws Exception {
        Path audioFile = tempDir.resolve("large-oversized-chunk.wav");
        Files.writeString(audioFile, "large audio");
        AsrChunkingProperties properties = new AsrChunkingProperties();
        properties.setMaxAudioFileSize(DataSize.ofBytes(1));
        properties.setMaxChunkFileSize(DataSize.ofBytes(1));
        PipelineAnalysisTaskStepContext context = context();
        context.setAudioExtractionResult(new AudioExtractionResult(audioFile, "wav", 16000, 1));
        PipelineRunnerWorkspace workspace = new PipelineRunnerWorkspace(
            new AnalysisTaskRunnerProperties(tempDir.resolve("runner"))
        );

        assertThatThrownBy(() -> new TranscribeAudioStep(
            new GuardSpeechToTextProvider(),
            new OversizedAudioChunker(),
            properties,
            workspace,
            null,
            authoritativeDuration(1_200_000L)
        ).execute(context))
            .isInstanceOf(BusinessException.class)
            .hasMessageContaining("ASR chunk file exceeds configured limit");
    }

    private static PipelineAnalysisTaskStepContext context() {
        return new PipelineAnalysisTaskStepContext(
            new AnalysisTaskExecutionContext("task_1", "up_1", 7L, "zh-CN", "req_1")
        );
    }

    private static SpeechToTextResult result() {
        return new SpeechToTextResult(
            "fake-asr",
            "zh-CN",
            "hello course",
            List.of(new TranscribedSegment(0, 0, 1200, "hello course")),
            Duration.ofMillis(10),
            1200,
            Map.of("safe", "metadata")
        );
    }

    private static AsrChunkingProperties retryableChunkingProperties() {
        AsrChunkingProperties properties = new AsrChunkingProperties();
        properties.setMaxAudioFileSize(DataSize.ofBytes(1));
        properties.setMaxChunkFileSize(DataSize.ofKilobytes(1));
        properties.setChunkDuration(Duration.ofSeconds(600));
        properties.getChunkRetry().setMaxAttempts(3);
        properties.getChunkRetry().setBackoff(List.of(Duration.ZERO, Duration.ZERO, Duration.ZERO));
        return properties;
    }

    private static AudioDurationProbe authoritativeDuration(long durationMillis) {
        return ignored -> durationMillis;
    }

    private static Map<String, Long> requestCountsByChunkFile(List<SpeechToTextRequest> requests) {
        return requests.stream()
            .collect(java.util.stream.Collectors.groupingBy(
                request -> request.audioFile().getFileName().toString(),
                java.util.stream.Collectors.counting()
            ));
    }

    private static AnalysisTaskMapper runningTaskMapper() {
        AnalysisTaskMapper taskMapper = mock(AnalysisTaskMapper.class);
        AnalysisTask task = new AnalysisTask();
        task.setId("task_1");
        task.setUserId(7L);
        task.setStatus(AnalysisTaskStatus.RUNNING.name());
        when(taskMapper.selectByIdAndUserId("task_1", 7L)).thenReturn(task);
        when(taskMapper.updateRunningProgressByIdAndUserId(eq("task_1"), eq(7L), anyInt(), eq("ASR")))
            .thenReturn(1);
        return taskMapper;
    }

    private void executeSingleChunkWithProgress(
        AnalysisTaskMapper taskMapper,
        TaskProgressSnapshotService snapshotService
    ) throws Exception {
        Path audioFile = Files.writeString(tempDir.resolve("progress-fixture.wav"), "large audio");
        AsrChunkingProperties properties = new AsrChunkingProperties();
        properties.setMaxAudioFileSize(DataSize.ofBytes(1));
        properties.setMaxChunkFileSize(DataSize.ofKilobytes(1));
        properties.setChunkDuration(Duration.ofSeconds(60));
        properties.setConcurrency(1);
        PipelineAnalysisTaskStepContext context = context();
        context.setAudioExtractionResult(new AudioExtractionResult(audioFile, "wav", 16000, 1));
        PipelineRunnerWorkspace workspace = new PipelineRunnerWorkspace(
            new AnalysisTaskRunnerProperties(tempDir.resolve("progress-runner"))
        );

        new TranscribeAudioStep(
            new FullMinuteChunkSpeechToTextProvider(),
            new ManyAudioChunksChunker(1),
            properties,
            workspace,
            taskMapper,
            snapshotService,
            new RecordingTaskClaimService(),
            ignored -> { },
            authoritativeDuration(60_000L)
        ).execute(context);
    }

    private record FakeSpeechToTextProvider(
        AtomicReference<SpeechToTextRequest> capturedRequest,
        SpeechToTextResult result
    ) implements SpeechToTextProvider {

        @Override
        public SpeechToTextResult transcribe(SpeechToTextRequest request) {
            capturedRequest.set(request);
            return result;
        }

        @Override
        public String providerName() {
            return "fake-asr";
        }
    }

    private static final class RecordingSpeechToTextProvider implements SpeechToTextProvider {

        private final List<SpeechToTextRequest> requests = Collections.synchronizedList(new ArrayList<>());

        @Override
        public SpeechToTextResult transcribe(SpeechToTextRequest request) {
            requests.add(request);
            if (request.audioFile().getFileName().toString().contains("001")) {
                return new SpeechToTextResult(
                    "fake-asr",
                    "en",
                    "chunk one",
                    List.of(new TranscribedSegment(7, 100, 700, "chunk one")),
                    Duration.ofMillis(20),
                    600L,
                    Map.of()
                );
            }
            return new SpeechToTextResult(
                "fake-asr",
                "en",
                "chunk zero",
                List.of(new TranscribedSegment(3, 0, 500, "chunk zero")),
                Duration.ofMillis(10),
                500L,
                Map.of()
            );
        }

        @Override
        public String providerName() {
            return "fake-asr";
        }
    }

    private static final class FailOnceRetryableSpeechToTextProvider implements SpeechToTextProvider {

        private final List<SpeechToTextRequest> requests = Collections.synchronizedList(new ArrayList<>());
        private final AtomicInteger firstChunkAttempts = new AtomicInteger();

        @Override
        public SpeechToTextResult transcribe(SpeechToTextRequest request) {
            requests.add(request);
            String name = request.audioFile().getFileName().toString();
            if (!name.contains("001") && firstChunkAttempts.incrementAndGet() == 1) {
                throw new SiliconFlowAsrException("SiliconFlow ASR request failed with HTTP 502", true, 502);
            }
            return chunkResult(name);
        }

        @Override
        public String providerName() {
            return "fake-asr";
        }
    }

    private static final class AlwaysRetryableSpeechToTextProvider implements SpeechToTextProvider {

        private final List<SpeechToTextRequest> requests = Collections.synchronizedList(new ArrayList<>());

        @Override
        public SpeechToTextResult transcribe(SpeechToTextRequest request) {
            requests.add(request);
            throw new SiliconFlowAsrException("SiliconFlow ASR request failed with HTTP 502", true, 502);
        }

        @Override
        public String providerName() {
            return "fake-asr";
        }
    }

    private static final class AlwaysUnauthorizedSpeechToTextProvider implements SpeechToTextProvider {

        private final List<SpeechToTextRequest> requests = Collections.synchronizedList(new ArrayList<>());

        @Override
        public SpeechToTextResult transcribe(SpeechToTextRequest request) {
            requests.add(request);
            throw new SiliconFlowAsrException("SiliconFlow ASR request failed with HTTP 401", false, 401);
        }

        @Override
        public String providerName() {
            return "fake-asr";
        }
    }

    private static final class AudioLimitFailureSpeechToTextProvider implements SpeechToTextProvider {

        private final List<SpeechToTextRequest> requests = Collections.synchronizedList(new ArrayList<>());

        @Override
        public SpeechToTextResult transcribe(SpeechToTextRequest request) {
            requests.add(request);
            throw new SiliconFlowAsrException(
                "SiliconFlow ASR configuration is invalid: audio file exceeds configured limit",
                false
            );
        }

        @Override
        public String providerName() {
            return "fake-asr";
        }
    }

    private static final class StatusCodeFailingSpeechToTextProvider implements SpeechToTextProvider {

        private final int statusCode;
        private final List<SpeechToTextRequest> requests = Collections.synchronizedList(new ArrayList<>());

        private StatusCodeFailingSpeechToTextProvider(int statusCode) {
            this.statusCode = statusCode;
        }

        @Override
        public SpeechToTextResult transcribe(SpeechToTextRequest request) {
            requests.add(request);
            throw new SiliconFlowAsrException(
                "SiliconFlow ASR request failed with HTTP " + statusCode,
                false,
                statusCode
            );
        }

        @Override
        public String providerName() {
            return "fake-asr";
        }
    }

    private static SpeechToTextResult chunkResult(String name) {
        if (name.contains("001")) {
            return new SpeechToTextResult(
                "fake-asr",
                "en",
                "chunk one",
                List.of(new TranscribedSegment(7, 100, 700, "chunk one")),
                Duration.ofMillis(20),
                600L,
                Map.of()
            );
        }
        return new SpeechToTextResult(
            "fake-asr",
            "en",
            "chunk zero",
            List.of(new TranscribedSegment(3, 0, 500, "chunk zero")),
            Duration.ofMillis(10),
            500L,
            Map.of()
        );
    }

    private static final class PointTimestampSpeechToTextProvider implements SpeechToTextProvider {

        @Override
        public SpeechToTextResult transcribe(SpeechToTextRequest request) {
            String name = request.audioFile().getFileName().toString();
            String text = name.contains("001") ? "chunk one" : "chunk zero";
            return new SpeechToTextResult(
                "fake-asr",
                "en",
                text,
                List.of(new TranscribedSegment(0, 0, 0, text)),
                Duration.ofMillis(10),
                0L,
                Map.of()
            );
        }

        @Override
        public String providerName() {
            return "fake-asr";
        }
    }

    private static final class FullMinuteChunkSpeechToTextProvider implements SpeechToTextProvider {

        @Override
        public SpeechToTextResult transcribe(SpeechToTextRequest request) {
            return new SpeechToTextResult(
                "fake-asr",
                "en",
                "chunk",
                List.of(new TranscribedSegment(4, 0L, 60_000L, "chunk")),
                Duration.ofMillis(10),
                60_000L,
                Map.of()
            );
        }

        @Override
        public String providerName() {
            return "fake-asr";
        }
    }

    private static final class FakeAudioChunker implements AudioChunker {

        private Path outputDirectory;

        @Override
        public List<AudioChunk> split(Path audioFile, Path outputDirectory, Duration chunkDuration, int maxChunks) {
            this.outputDirectory = outputDirectory;
            try {
                Files.createDirectories(outputDirectory);
                Path first = Files.writeString(outputDirectory.resolve("chunk-000.wav"), "0");
                Path second = Files.writeString(outputDirectory.resolve("chunk-001.wav"), "1");
                return List.of(
                    new AudioChunk(0, 0L, first),
                    new AudioChunk(1, chunkDuration.toMillis(), second)
                );
            } catch (java.io.IOException exception) {
                throw new IllegalStateException(exception);
            }
        }
    }

    private static final class CoordinatedConcurrentSpeechToTextProvider implements SpeechToTextProvider {

        private final AtomicInteger active = new AtomicInteger();
        private final AtomicInteger maxActive = new AtomicInteger();
        private final CountDownLatch chunkZeroStarted = new CountDownLatch(1);
        private final CountDownLatch bothStarted = new CountDownLatch(2);
        private final CountDownLatch releaseChunkZero;
        private final List<Integer> startedChunkIndexes = new CopyOnWriteArrayList<>();

        private CoordinatedConcurrentSpeechToTextProvider(CountDownLatch releaseChunkZero) {
            this.releaseChunkZero = releaseChunkZero;
        }

        @Override
        public SpeechToTextResult transcribe(SpeechToTextRequest request) {
            int currentActive = active.incrementAndGet();
            maxActive.accumulateAndGet(currentActive, Math::max);
            String fileName = request.audioFile().getFileName().toString();
            int chunkIndex = fileName.contains("001") ? 1 : 0;
            try {
                if (chunkIndex == 1 && !chunkZeroStarted.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("chunk 000 did not start before chunk 001");
                }
                startedChunkIndexes.add(chunkIndex);
                if (chunkIndex == 0) {
                    chunkZeroStarted.countDown();
                }
                bothStarted.countDown();
                if (!bothStarted.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("both ASR chunk calls did not start concurrently");
                }
                if (chunkIndex == 1) {
                    return chunkResult(fileName);
                }
                if (!releaseChunkZero.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("chunk 001 was not collected before chunk 000");
                }
                return chunkResult(fileName);
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("interrupted");
            } finally {
                active.decrementAndGet();
            }
        }

        @Override
        public String providerName() {
            return "fake-asr";
        }
    }

    private static final class SensitiveFailingChunkSpeechToTextProvider implements SpeechToTextProvider {

        @Override
        public SpeechToTextResult transcribe(SpeechToTextRequest request) {
            throw new SiliconFlowAsrException(
                "HTTP 500 at " + syntheticWindowsPath() + " "
                    + sensitiveWord("object", "Key") + "=abc "
                    + sensitiveWord("to", "ken") + "=raw "
                    + sensitiveWord("api ", "key") + "=raw",
                true,
                500
            );
        }

        @Override
        public String providerName() {
            return "fake-asr";
        }
    }

    private static String syntheticWindowsPath() {
        return "C:" + "\\" + "redacted" + "\\" + "audio.wav";
    }

    private static String windowsDrivePrefix() {
        return "C:" + "\\";
    }

    private static String sensitiveWord(String left, String right) {
        return left + right;
    }

    private static final class ManyAudioChunksChunker implements AudioChunker {

        private final int chunkCount;

        private ManyAudioChunksChunker(int chunkCount) {
            this.chunkCount = chunkCount;
        }

        @Override
        public List<AudioChunk> split(Path audioFile, Path outputDirectory, Duration chunkDuration, int maxChunks) {
            try {
                Files.createDirectories(outputDirectory);
                List<AudioChunk> chunks = new ArrayList<>();
                for (int index = 0; index < chunkCount; index++) {
                    Path chunk = Files.writeString(outputDirectory.resolve("chunk-%03d.wav".formatted(index)), "0");
                    chunks.add(new AudioChunk(index, index * chunkDuration.toMillis(), chunk));
                }
                return chunks;
            } catch (java.io.IOException exception) {
                throw new IllegalStateException(exception);
            }
        }
    }

    private static final class OversizedAudioChunker implements AudioChunker {

        @Override
        public List<AudioChunk> split(Path audioFile, Path outputDirectory, Duration chunkDuration, int maxChunks) {
            try {
                Files.createDirectories(outputDirectory);
                Path chunk = Files.writeString(outputDirectory.resolve("chunk-000.wav"), "oversized");
                return List.of(new AudioChunk(0, 0L, chunk));
            } catch (java.io.IOException exception) {
                throw new IllegalStateException(exception);
            }
        }
    }

    private static final class GuardSpeechToTextProvider implements SpeechToTextProvider {

        @Override
        public SpeechToTextResult transcribe(SpeechToTextRequest request) {
            throw new AssertionError("provider must not receive full or invalid oversized audio");
        }

        @Override
        public String providerName() {
            return "guard-asr";
        }
    }

    private static final class FailingSpeechToTextProvider implements SpeechToTextProvider {

        @Override
        public SpeechToTextResult transcribe(SpeechToTextRequest request) {
            throw new IllegalStateException("Authorization Bearer token failed at C:\\secret\\audio.wav");
        }

        @Override
        public String providerName() {
            return "fake-asr";
        }
    }

    private static final class RecordingTaskProgressSnapshotService implements TaskProgressSnapshotService {

        private final List<TaskProgressSnapshot> snapshots = new CopyOnWriteArrayList<>();

        @Override
        public void save(TaskProgressSnapshot snapshot) {
            snapshots.add(snapshot);
        }

        @Override
        public Optional<TaskProgressSnapshot> find(String taskId) {
            return snapshots.stream()
                .filter(snapshot -> snapshot.taskId().equals(taskId))
                .reduce((ignored, next) -> next);
        }

        @Override
        public void delete(String taskId) {
            snapshots.removeIf(snapshot -> snapshot.taskId().equals(taskId));
        }
    }

    private static final class RecordingTaskClaimService implements TaskClaimService {

        private final List<String> refreshCalls = new CopyOnWriteArrayList<>();

        @Override
        public TaskClaimResult tryAcquire(String taskId, String requestId) {
            return TaskClaimResult.acquiredResult();
        }

        @Override
        public boolean refresh(String taskId, String requestId) {
            refreshCalls.add(taskId + ":" + requestId);
            return true;
        }

        @Override
        public void release(String taskId, String requestId) {
        }
    }
}
