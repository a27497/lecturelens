package com.example.courselingo.task.runner;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.media.AudioExtractionRequest;
import com.example.courselingo.media.AudioExtractionResult;
import com.example.courselingo.media.FfmpegAudioExtractor;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class ExtractAudioStep implements PipelineAnalysisTaskStep {

    private static final String AUDIO_OUTPUT_FILE_NAME = "audio.wav";

    private final FfmpegAudioExtractor ffmpegAudioExtractor;
    private final PipelineRunnerWorkspace workspace;

    public ExtractAudioStep(
        FfmpegAudioExtractor ffmpegAudioExtractor,
        PipelineRunnerWorkspace workspace
    ) {
        this.ffmpegAudioExtractor = ffmpegAudioExtractor;
        this.workspace = workspace;
    }

    @Override
    public PipelineAnalysisTaskStepName name() {
        return PipelineAnalysisTaskStepName.EXTRACT_AUDIO;
    }

    @Override
    public void execute(PipelineAnalysisTaskStepContext context) {
        Path sourcePath = context.requireUploadedSourcePath();
        Path outputDirectory = workspace.audioOutputDirectory(context);
        ensureOutputDirectory(outputDirectory);
        AudioExtractionResult result = ffmpegAudioExtractor.extract(new AudioExtractionRequest(
            sourcePath,
            outputDirectory,
            AUDIO_OUTPUT_FILE_NAME
        ));
        context.setAudioExtractionResult(result);
    }

    private static void ensureOutputDirectory(Path outputDirectory) {
        try {
            Files.createDirectories(outputDirectory);
        } catch (IOException exception) {
            throw new BusinessException(
                ErrorCode.MEDIA_OUTPUT_INVALID,
                "Pipeline audio workspace is not available",
                exception
            );
        }
    }
}
