package com.example.courselingo.task.runner;

import com.example.courselingo.artifact.service.GenerateJsonArtifactCommand;
import com.example.courselingo.artifact.service.GenerateMarkdownArtifactCommand;
import com.example.courselingo.artifact.service.GenerateSrtArtifactCommand;
import com.example.courselingo.artifact.service.GenerateVttArtifactCommand;
import com.example.courselingo.artifact.service.JsonArtifactService;
import com.example.courselingo.artifact.service.MarkdownArtifactService;
import com.example.courselingo.artifact.service.SrtArtifactService;
import com.example.courselingo.artifact.service.VttArtifactService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.logging.SafeLogSanitizer;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

final class GenerateArtifactsStep implements PipelineAnalysisTaskStep {

    private static final Logger LOGGER = LoggerFactory.getLogger(GenerateArtifactsStep.class);

    private final AnalysisTaskMapper analysisTaskMapper;
    private final SrtArtifactService srtArtifactService;
    private final VttArtifactService vttArtifactService;
    private final MarkdownArtifactService markdownArtifactService;
    private final JsonArtifactService jsonArtifactService;

    GenerateArtifactsStep(
        AnalysisTaskMapper analysisTaskMapper,
        SrtArtifactService srtArtifactService,
        VttArtifactService vttArtifactService,
        MarkdownArtifactService markdownArtifactService,
        JsonArtifactService jsonArtifactService
    ) {
        this.analysisTaskMapper = Objects.requireNonNull(
            analysisTaskMapper,
            "analysis task mapper is required"
        );
        this.srtArtifactService = Objects.requireNonNull(
            srtArtifactService,
            "SRT artifact service is required"
        );
        this.vttArtifactService = Objects.requireNonNull(
            vttArtifactService,
            "VTT artifact service is required"
        );
        this.markdownArtifactService = Objects.requireNonNull(
            markdownArtifactService,
            "Markdown artifact service is required"
        );
        this.jsonArtifactService = Objects.requireNonNull(
            jsonArtifactService,
            "JSON artifact service is required"
        );
    }

    @Override
    public PipelineAnalysisTaskStepName name() {
        return PipelineAnalysisTaskStepName.GENERATE_ARTIFACTS;
    }

    @Override
    public void execute(PipelineAnalysisTaskStepContext context) {
        if (analysisTaskMapper.selectByIdAndUserId(context.taskId(), context.userId()) == null) {
            throw new BusinessException(ErrorCode.TASK_NOT_FOUND);
        }
        String targetLanguage = context.targetLanguage();
        long startedNanos = System.nanoTime();
        List<String> generatedTypes = new ArrayList<>();
        LOGGER.info(
            "event=artifact_generation_started taskId={} targetLanguage={}",
            SafeLogSanitizer.sanitize(context.taskId()),
            SafeLogSanitizer.sanitize(targetLanguage)
        );
        srtArtifactService.generateSrtArtifact(new GenerateSrtArtifactCommand(
            context.taskId(),
            context.userId(),
            targetLanguage
        ));
        generatedTypes.add("SRT");
        vttArtifactService.generateVttArtifact(new GenerateVttArtifactCommand(
            context.taskId(),
            context.userId(),
            targetLanguage
        ));
        generatedTypes.add("VTT");
        markdownArtifactService.generateMarkdownArtifact(new GenerateMarkdownArtifactCommand(
            context.taskId(),
            context.userId(),
            targetLanguage
        ));
        generatedTypes.add("MARKDOWN");
        jsonArtifactService.generateJsonArtifact(new GenerateJsonArtifactCommand(
            context.taskId(),
            context.userId(),
            targetLanguage
        ));
        generatedTypes.add("JSON");
        LOGGER.info(
            "event=artifact_generation_completed taskId={} generatedTypes={} durationMillis={}",
            SafeLogSanitizer.sanitize(context.taskId()),
            generatedTypes,
            Duration.ofNanos(System.nanoTime() - startedNanos).toMillis()
        );
    }
}
