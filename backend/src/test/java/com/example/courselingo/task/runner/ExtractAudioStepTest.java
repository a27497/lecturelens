package com.example.courselingo.task.runner;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.courselingo.media.AudioExtractionRequest;
import com.example.courselingo.media.AudioExtractionResult;
import com.example.courselingo.media.FfmpegAudioExtractor;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ExtractAudioStepTest {

    @TempDir
    private Path tempDir;

    @Test
    void callsFfmpegExtractorAndStoresAudioResultInContext() throws Exception {
        Path source = tempDir.resolve("source.mp4");
        Files.writeString(source, "video", StandardCharsets.UTF_8);
        AtomicReference<AudioExtractionRequest> captured = new AtomicReference<>();
        FfmpegAudioExtractor extractor = request -> {
            captured.set(request);
            Path audioFile = request.outputDirectory().resolve(request.outputFileName());
            return new AudioExtractionResult(audioFile, "wav", 16000, 1);
        };
        PipelineAnalysisTaskStepContext context = contextWithSource(source);

        new ExtractAudioStep(extractor, workspace()).execute(context);

        assertThat(captured.get()).isNotNull();
        assertThat(captured.get().inputVideo()).isEqualTo(source);
        assertThat(captured.get().outputDirectory())
            .startsWith(tempDir.resolve("runner").toAbsolutePath().normalize());
        assertThat(captured.get().outputFileName()).isEqualTo("audio.wav");
        assertThat(context.audioExtractionResult())
            .contains(new AudioExtractionResult(captured.get().outputDirectory().resolve("audio.wav"), "wav", 16000, 1));
        assertThat(context.extractedAudioPath()).contains(captured.get().outputDirectory().resolve("audio.wav"));
        assertThat(context.toString())
            .doesNotContain(source.toString())
            .doesNotContain(captured.get().outputDirectory().toString());
    }

    @Test
    void sourceMustBeResolvedBeforeExtractingAudio() {
        FfmpegAudioExtractor extractor = request -> {
            throw new AssertionError("FFmpeg must not be called without source");
        };

        assertThatThrownBy(() -> new ExtractAudioStep(extractor, workspace()).execute(context()))
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("uploaded source");
    }

    private PipelineRunnerWorkspace workspace() {
        return new PipelineRunnerWorkspace(new AnalysisTaskRunnerProperties(tempDir.resolve("runner")));
    }

    private static PipelineAnalysisTaskStepContext contextWithSource(Path source) {
        PipelineAnalysisTaskStepContext context = context();
        context.setUploadedSourcePath(source);
        return context;
    }

    private static PipelineAnalysisTaskStepContext context() {
        return new PipelineAnalysisTaskStepContext(
            new AnalysisTaskExecutionContext("task_1", "up_1", 7L, "zh-CN", "req_1")
        );
    }
}
