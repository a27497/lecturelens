package com.example.courselingo.task.runner;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

import com.example.courselingo.ai.record.service.AiCallRecordService;
import com.example.courselingo.artifact.service.JsonArtifactService;
import com.example.courselingo.artifact.service.MarkdownArtifactService;
import com.example.courselingo.artifact.service.SrtArtifactService;
import com.example.courselingo.artifact.service.VttArtifactService;
import com.example.courselingo.fusion.VideoSegmentFusionService;
import com.example.courselingo.ai.asr.SpeechToTextProvider;
import com.example.courselingo.ai.asr.SpeechToTextResult;
import com.example.courselingo.learning.service.LearningPackageService;
import com.example.courselingo.media.AudioExtractionResult;
import com.example.courselingo.media.AudioChunker;
import com.example.courselingo.media.AudioDurationProbe;
import com.example.courselingo.media.FfmpegAudioExtractor;
import com.example.courselingo.subtitle.service.SubtitleSegmentPersistenceService;
import com.example.courselingo.subtitle.service.SubtitleTranslationService;
import com.example.courselingo.storage.StorageService;
import com.example.courselingo.task.claim.NoopTaskClaimService;
import com.example.courselingo.task.claim.TaskClaimService;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.task.mapper.TaskLogMapper;
import com.example.courselingo.task.progress.NoopTaskProgressSnapshotService;
import com.example.courselingo.task.progress.TaskProgressSnapshotService;
import com.example.courselingo.upload.mapper.UploadSessionMapper;
import com.example.courselingo.upload.service.ChunkStagingPathResolver;
import com.example.courselingo.upload.service.ChunkStagingProperties;
import com.example.courselingo.vision.keyframe.VideoKeyframeScanService;
import com.example.courselingo.vision.analysis.VisionAnalysisService;
import com.example.courselingo.vision.ocr.VideoKeyframeOcrScanService;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class AnalysisTaskWorkExecutorConfigurationTest {

    private final ApplicationContextRunner contextRunner = new ApplicationContextRunner()
        .withUserConfiguration(AnalysisTaskWorkExecutorConfiguration.class);

    @Test
    void defaultExecutorRemainsNoop() {
        contextRunner.run(context -> {
            assertThat(context).hasSingleBean(AnalysisTaskWorkExecutor.class);
            assertThat(context.getBean(AnalysisTaskWorkExecutor.class))
                .isInstanceOf(NoopAnalysisTaskWorkExecutor.class);
            assertThat(context).doesNotHaveBean(PipelineAnalysisTaskWorkExecutor.class);
            assertThat(context).doesNotHaveBean(ResolveUploadedSourceStep.class);
            assertThat(context).doesNotHaveBean(ExtractAudioStep.class);
        });
    }

    @Test
    void pipelineExecutorIsEnabledOnlyByExplicitProperty() {
        contextRunner
            .withPropertyValues("courselingo.task.runner.pipeline.enabled=true")
            .withBean(AnalysisTaskMapper.class, () -> mock(AnalysisTaskMapper.class))
            .withBean(TaskLogMapper.class, () -> mock(TaskLogMapper.class))
            .withBean(UploadSessionMapper.class, () -> mock(UploadSessionMapper.class))
            .withBean(StorageService.class, () -> mock(StorageService.class))
            .withBean(VideoKeyframeScanService.class, () -> mock(VideoKeyframeScanService.class))
            .withBean(VideoKeyframeOcrScanService.class, () -> mock(VideoKeyframeOcrScanService.class))
            .withBean(VisionAnalysisService.class, () -> mock(VisionAnalysisService.class))
            .withBean(VideoSegmentFusionService.class, () -> mock(VideoSegmentFusionService.class))
            .withBean(ChunkStagingPathResolver.class, () ->
                new ChunkStagingPathResolver(new ChunkStagingProperties(Path.of("build/test-chunks"))))
            .withBean(FfmpegAudioExtractor.class, () -> request ->
                new AudioExtractionResult(request.outputDirectory().resolve(request.outputFileName()), "wav", 16000, 1))
            .withBean(AudioChunker.class, () -> mock(AudioChunker.class))
            .withBean(AudioDurationProbe.class, () -> ignored -> 1_000L)
            .withBean(SpeechToTextProvider.class, () -> mock(SpeechToTextProvider.class))
            .withBean(SubtitleSegmentPersistenceService.class, () -> mock(SubtitleSegmentPersistenceService.class))
            .withBean(SubtitleTranslationService.class, () -> mock(SubtitleTranslationService.class))
            .withBean(LearningPackageService.class, () -> mock(LearningPackageService.class))
            .withBean(AiCallRecordService.class, () -> mock(AiCallRecordService.class))
            .withBean(SrtArtifactService.class, () -> mock(SrtArtifactService.class))
            .withBean(VttArtifactService.class, () -> mock(VttArtifactService.class))
            .withBean(MarkdownArtifactService.class, () -> mock(MarkdownArtifactService.class))
            .withBean(JsonArtifactService.class, () -> mock(JsonArtifactService.class))
            .withBean(TaskClaimService.class, NoopTaskClaimService::new)
            .withBean(TaskProgressSnapshotService.class, NoopTaskProgressSnapshotService::new)
            .run(context -> {
                assertThat(context).hasSingleBean(AnalysisTaskWorkExecutor.class);
                assertThat(context).hasSingleBean(PipelineAnalysisTaskWorkExecutor.class);
                assertThat(context.getBean(AnalysisTaskWorkExecutor.class))
                    .isInstanceOf(PipelineAnalysisTaskWorkExecutor.class);
                PipelineAnalysisTaskWorkExecutor executor = context.getBean(PipelineAnalysisTaskWorkExecutor.class);
                assertThat(executor.stepNames())
                    .containsExactlyElementsOf(PipelineAnalysisTaskStepName.ordered());
            });
    }

    @Test
    void asrChunkingPropertiesBindDefaultsAndOverrides() {
        contextRunner.run(context -> {
            AsrChunkingProperties properties = context.getBean(AsrChunkingProperties.class);
            assertThat(properties.isEnabled()).isTrue();
            assertThat(properties.getChunkDuration()).hasSeconds(60);
            assertThat(properties.getMaxChunks()).isEqualTo(180);
        });

        contextRunner
            .withPropertyValues(
                "courselingo.ai.asr.chunking.enabled=false",
                "courselingo.ai.asr.chunking.chunk-duration=300s",
                "courselingo.ai.asr.chunking.max-chunks=12"
            )
            .run(context -> {
                AsrChunkingProperties properties = context.getBean(AsrChunkingProperties.class);
                assertThat(properties.isEnabled()).isFalse();
                assertThat(properties.getChunkDuration()).hasSeconds(300);
                assertThat(properties.getMaxChunks()).isEqualTo(12);
            });
    }
}
