package com.example.courselingo.task.runner;

import com.example.courselingo.ai.asr.*;
import com.example.courselingo.media.*;
import com.example.courselingo.systemmodel.SystemModelExecutionRef;

import org.springframework.util.unit.DataSize;

import java.nio.file.*;
import java.time.Duration;
import java.util.List;

/** Runs the production chunk/retry/merge path with two deterministic, one-second WAV chunks. */
public final class AsrPipelineTestHarness {
    public static SpeechToTextResult runFrozenSilence(SpeechToTextProvider provider,SystemModelExecutionRef ref,
            com.example.courselingo.mq.AnalysisTaskMessage message,Path input,Path root,
            com.example.courselingo.subtitle.pipeline.PipelinePolicyService policies,
            com.example.courselingo.task.service.AsrExecutionStore store,
            com.example.courselingo.task.service.PipelineSourceCheckpointStore checkpoints,
            com.example.courselingo.task.mapper.AnalysisTaskMapper mapper,SilenceAudioChunkPlanner planner,long duration) {
        var context=new PipelineAnalysisTaskStepContext(new AnalysisTaskExecutionContext(ref.taskId(),ref.taskId(),ref.userId(),"en","zh-CN",
            message.requestId(),ref,2,message.executionEpoch()));
        context.setAudioExtractionResult(new AudioExtractionResult(input,"wav",16000,1));
        new TranscribeAudioStep(provider,null,new AsrChunkingProperties(),
            new PipelineRunnerWorkspace(new AnalysisTaskRunnerProperties(root)),mapper,ignored->duration)
            .withSilencePlanning(policies,planner).withCheckpoints(checkpoints).withAsrStore(store).execute(context);
        return context.requireSpeechToTextResult();
    }
    public static SpeechToTextResult run(
            SpeechToTextProvider provider,
            SystemModelExecutionRef ref,
            Path workspaceRoot,
            Path wav)
            throws Exception {
        var context =
                new PipelineAnalysisTaskStepContext(
                        new AnalysisTaskExecutionContext(
                                ref.taskId(),
                                ref.taskId(),
                                ref.userId(),
                                "en",
                                "zh-CN",
                                "asr-test",
                                ref));
        Files.createDirectories(workspaceRoot);
        Path largeAudio = Files.write(workspaceRoot.resolve("full.wav"), new byte[100000]);
        context.setAudioExtractionResult(new AudioExtractionResult(largeAudio, "wav", 16000, 1));
        var properties = new AsrChunkingProperties();
        properties.setMaxAudioFileSize(DataSize.ofBytes(50000));
        properties.setMaxChunkFileSize(DataSize.ofMegabytes(1));
        properties.getChunkRetry().setBackoff(List.of(Duration.ZERO));
        properties.setConcurrency(2);
        AudioChunker chunker =
                (source, directory, duration, maxChunks) -> {
                    try {
                        Files.createDirectories(directory);
                        return List.of(
                                new AudioChunk(0, 0, Files.copy(wav, directory.resolve("1.wav"))),
                                new AudioChunk(
                                        1, 1000, Files.copy(wav, directory.resolve("2.wav"))));
                    } catch (java.io.IOException failure) {
                        throw new IllegalStateException(failure);
                    }
                };
        new TranscribeAudioStep(
                        provider,
                        chunker,
                        properties,
                        new PipelineRunnerWorkspace(
                                new AnalysisTaskRunnerProperties(workspaceRoot)),
                        null,
                        ignored -> 2000L)
                .execute(context);
        return context.requireSpeechToTextResult();
    }
}
