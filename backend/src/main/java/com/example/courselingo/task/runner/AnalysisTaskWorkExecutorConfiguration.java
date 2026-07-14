package com.example.courselingo.task.runner;

import com.example.courselingo.ai.asr.SpeechToTextProvider;
import com.example.courselingo.ai.record.service.AiCallRecordService;
import com.example.courselingo.artifact.service.JsonArtifactService;
import com.example.courselingo.artifact.service.MarkdownArtifactService;
import com.example.courselingo.artifact.service.SrtArtifactService;
import com.example.courselingo.artifact.service.VttArtifactService;
import com.example.courselingo.fusion.VideoSegmentFusionService;
import com.example.courselingo.fusion.VideoSegmentProperties;
import com.example.courselingo.learning.service.LearningPackageService;
import com.example.courselingo.media.AudioChunker;
import com.example.courselingo.media.AudioDurationProbe;
import com.example.courselingo.media.FfmpegAudioExtractor;
import com.example.courselingo.subtitle.service.SubtitleSegmentPersistenceService;
import com.example.courselingo.subtitle.service.SubtitleTranslationService;
import com.example.courselingo.storage.StorageService;
import com.example.courselingo.task.claim.TaskClaimService;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.task.mapper.TaskLogMapper;
import com.example.courselingo.task.progress.TaskProgressSnapshotService;
import com.example.courselingo.upload.mapper.UploadSessionMapper;
import com.example.courselingo.upload.service.ChunkStagingPathResolver;
import com.example.courselingo.vision.keyframe.VideoKeyframeProperties;
import com.example.courselingo.vision.keyframe.VideoKeyframeScanService;
import com.example.courselingo.vision.analysis.VisionAnalysisProperties;
import com.example.courselingo.vision.analysis.VisionAnalysisService;
import com.example.courselingo.vision.ocr.VideoKeyframeOcrScanService;
import com.example.courselingo.vision.ocr.VisionOcrProperties;
import java.nio.file.Path;
import java.time.Clock;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties({
    AnalysisTaskRunnerProperties.class,
    AsrChunkingProperties.class,
    VideoKeyframeProperties.class,
    VisionOcrProperties.class,
    VisionAnalysisProperties.class,
    VideoSegmentProperties.class
})
public class AnalysisTaskWorkExecutorConfiguration {

    private static final Logger LOGGER = LoggerFactory.getLogger(AnalysisTaskWorkExecutorConfiguration.class);

    @Bean
    ApplicationRunner asrChunkingConfigLogger(
        AsrChunkingProperties asrChunkingProperties,
        AnalysisTaskRunnerProperties runnerProperties
    ) {
        return args -> LOGGER.info(
            "CourseLingo ASR chunking config loaded: enabled={}, chunkDurationSeconds={}, maxChunks={}, concurrency={}, maxConcurrency={}, maxAudioFileSizeBytes={}, maxChunkFileSizeBytes={}, workspaceDir={}",
            asrChunkingProperties.isEnabled(),
            asrChunkingProperties.getChunkDuration().toSeconds(),
            asrChunkingProperties.getMaxChunks(),
            asrChunkingProperties.effectiveConcurrency(),
            asrChunkingProperties.getMaxConcurrency(),
            asrChunkingProperties.effectiveMaxAudioFileSizeBytes(),
            asrChunkingProperties.effectiveMaxChunkFileSizeBytes(),
            safeWorkspaceName(runnerProperties.normalizedWorkspaceDir())
        );
    }

    @Bean
    @ConditionalOnProperty(
        prefix = "courselingo.task.runner.pipeline",
        name = "enabled",
        havingValue = "true"
    )
    PipelineAnalysisTaskWorkExecutor pipelineAnalysisTaskWorkExecutor(
        AnalysisTaskMapper analysisTaskMapper,
        TaskLogMapper taskLogMapper,
        UploadSessionMapper uploadSessionMapper,
        ChunkStagingPathResolver chunkStagingPathResolver,
        StorageService storageService,
        VideoKeyframeScanService videoKeyframeScanService,
        VideoKeyframeProperties videoKeyframeProperties,
        VideoKeyframeOcrScanService videoKeyframeOcrScanService,
        VisionOcrProperties visionOcrProperties,
        VisionAnalysisService visionAnalysisService,
        VisionAnalysisProperties visionAnalysisProperties,
        VideoSegmentFusionService videoSegmentFusionService,
        VideoSegmentProperties videoSegmentProperties,
        FfmpegAudioExtractor ffmpegAudioExtractor,
        AudioChunker audioChunker,
        SpeechToTextProvider speechToTextProvider,
        SubtitleSegmentPersistenceService subtitleSegmentPersistenceService,
        SubtitleTranslationService subtitleTranslationService,
        LearningPackageService learningPackageService,
        SrtArtifactService srtArtifactService,
        VttArtifactService vttArtifactService,
        MarkdownArtifactService markdownArtifactService,
        JsonArtifactService jsonArtifactService,
        AiCallRecordService aiCallRecordService,
        AnalysisTaskRunnerProperties runnerProperties,
        AsrChunkingProperties asrChunkingProperties,
        AudioDurationProbe audioDurationProbe,
        TaskProgressSnapshotService progressSnapshotService,
        TaskClaimService taskClaimService
    ) {
        PipelineRunnerWorkspace workspace = new PipelineRunnerWorkspace(runnerProperties);
        return new PipelineAnalysisTaskWorkExecutor(List.of(
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.VALIDATE_TASK),
            new ResolveUploadedSourceStep(uploadSessionMapper, chunkStagingPathResolver, storageService),
            new ExtractKeyframesStep(
                videoKeyframeScanService,
                workspace,
                videoKeyframeProperties,
                taskLogMapper,
                Clock.systemUTC()
            ),
            new ExtractAudioStep(
                ffmpegAudioExtractor,
                workspace
            ),
            new TranscribeAudioStep(
                speechToTextProvider,
                audioChunker,
                asrChunkingProperties,
                workspace,
                analysisTaskMapper,
                progressSnapshotService,
                taskClaimService,
                ignored -> { },
                audioDurationProbe
            ),
            new PersistSubtitleSegmentsStep(analysisTaskMapper, subtitleSegmentPersistenceService),
            new TranslateSubtitleSegmentsStep(analysisTaskMapper, subtitleTranslationService),
            new GenerateLearningPackageStep(analysisTaskMapper, learningPackageService),
            new GenerateArtifactsStep(
                analysisTaskMapper,
                srtArtifactService,
                vttArtifactService,
                markdownArtifactService,
                jsonArtifactService
            ),
            new OcrKeyframesStep(
                videoKeyframeOcrScanService,
                visionOcrProperties,
                taskLogMapper,
                Clock.systemUTC()
            ),
            new AnalyzeKeyframesStep(
                visionAnalysisService,
                visionAnalysisProperties,
                taskLogMapper,
                Clock.systemUTC()
            ),
            new FuseVideoSegmentsStep(
                videoSegmentFusionService,
                videoSegmentProperties,
                taskLogMapper,
                Clock.systemUTC()
            ),
            new WriteAiCallRecordStep(analysisTaskMapper, aiCallRecordService),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.UPDATE_TASK_PROGRESS_STATUS)
        ), new DefaultPipelineTaskProgressReporter(
            analysisTaskMapper,
            progressSnapshotService,
            Clock.systemUTC()
        ));
    }

    @Bean
    @ConditionalOnProperty(
        prefix = "courselingo.task.runner.pipeline",
        name = "enabled",
        havingValue = "false",
        matchIfMissing = true
    )
    NoopAnalysisTaskWorkExecutor noopAnalysisTaskWorkExecutor() {
        return new NoopAnalysisTaskWorkExecutor();
    }

    private static String safeWorkspaceName(Path workspaceDir) {
        if (workspaceDir == null || workspaceDir.getFileName() == null) {
            return "unknown";
        }
        return workspaceDir.getFileName().toString();
    }
}
