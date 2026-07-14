package com.example.courselingo.task.runner;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.example.courselingo.media.AudioExtractionResult;
import com.example.courselingo.storage.StorageService;
import com.example.courselingo.upload.entity.UploadSession;
import com.example.courselingo.upload.mapper.UploadSessionMapper;
import com.example.courselingo.upload.service.ChunkStagingPathResolver;
import com.example.courselingo.upload.service.ChunkStagingProperties;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class PipelineF2ExecutionOrderTest {

    @TempDir
    private Path tempDir;

    @Test
    void pipelineExecutesValidateResolveAndExtractAudioInOrder() throws Exception {
        UploadSessionMapper mapper = mock(UploadSessionMapper.class);
        ChunkStagingPathResolver pathResolver = new ChunkStagingPathResolver(
            new ChunkStagingProperties(tempDir.resolve("chunks"))
        );
        Path assembled = pathResolver.resolveAssembledFile(7L, "up_1", "mp4");
        Files.createDirectories(assembled.getParent());
        Files.writeString(assembled, "video", StandardCharsets.UTF_8);
        when(mapper.selectById("up_1")).thenReturn(uploadedSession());
        AtomicBoolean extractorCalled = new AtomicBoolean(false);

        PipelineAnalysisTaskWorkExecutor executor = new PipelineAnalysisTaskWorkExecutor(List.of(
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.VALIDATE_TASK),
            new ResolveUploadedSourceStep(mapper, pathResolver, mock(StorageService.class)),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.EXTRACT_KEYFRAMES),
            new ExtractAudioStep(request -> {
                extractorCalled.set(true);
                assertThat(request.inputVideo()).isEqualTo(assembled);
                return new AudioExtractionResult(request.outputDirectory().resolve(request.outputFileName()), "wav", 16000, 1);
            }, new PipelineRunnerWorkspace(new AnalysisTaskRunnerProperties(tempDir.resolve("runner")))),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.TRANSCRIBE),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.PERSIST_SUBTITLES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.TRANSLATE_SUBTITLES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.GENERATE_LEARNING_PACKAGE),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.GENERATE_ARTIFACTS),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.OCR_KEYFRAMES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.ANALYZE_KEYFRAMES),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.FUSE_VIDEO_SEGMENTS),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.WRITE_AI_CALL_RECORD),
            new NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName.UPDATE_TASK_PROGRESS_STATUS)
        ));

        AnalysisTaskWorkResult result = executor.execute(
            new AnalysisTaskExecutionContext("task_1", "up_1", 7L, "zh-CN", "req_1")
        );

        assertThat(result.success()).isTrue();
        assertThat(extractorCalled).isTrue();
    }

    private static UploadSession uploadedSession() {
        UploadSession session = new UploadSession();
        session.setId("up_1");
        session.setUserId(7L);
        session.setStatus("UPLOADED");
        session.setExt("mp4");
        session.setObjectKey("raw/7/up_1/source.mp4");
        return session;
    }
}
