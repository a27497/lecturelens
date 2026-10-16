package com.example.courselingo.task.runner;

import com.example.courselingo.ai.asr.*;
import com.example.courselingo.media.*;
import com.example.courselingo.subtitle.pipeline.*;
import com.example.courselingo.systemmodel.SystemModelExecutionRef;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

class SilenceTranscribeStepTest {
    @TempDir Path directory;
    @org.junit.jupiter.params.ParameterizedTest
    @org.junit.jupiter.params.provider.ValueSource(booleans={false,true})
    @org.junit.jupiter.api.Timeout(5)
    void allClipsUseOnePinnedAdapterAndCarryClipOrASRIntervals(boolean withRetry) throws Exception {
        var ref=new SystemModelExecutionRef("snapshot",10,"task",9);
        var context=new PipelineAnalysisTaskStepContext(new AnalysisTaskExecutionContext("task","upload",9L,"en","zh-CN","req",ref));
        var input=directory.resolve("original.wav");Files.write(input,new byte[]{1});context.setAudioExtractionResult(new AudioExtractionResult(input,"wav",16000,1));
        var workspace=new PipelineRunnerWorkspace(new AnalysisTaskRunnerProperties(directory));var clips=workspace.asrChunksOutputDirectory(context);
        var plan=new SilenceAudioChunkPlanner.Plan(List.of(new AudioChunk(0,0,clips.resolve("first.wav"),30000,TranscriptTimingSource.SILENCE_SPLIT,null),
            new AudioChunk(1,40000,clips.resolve("second.wav"),70000,TranscriptTimingSource.AUDIO_CLIP,null)),"a".repeat(64),10000,4*1024*1024);
        var planner=mock(SilenceAudioChunkPlanner.class);when(planner.plan(eq(input),eq(70000L),eq(clips),any(),anyLong())).thenReturn(plan);
        doAnswer(call->{AudioChunk clip=call.getArgument(1);Files.createDirectories(clip.audioFile().getParent());Files.write(clip.audioFile(),new byte[100]);return null;})
            .when(planner).materialize(eq(input),any(),any(),anyLong());
        var root=mock(SpeechToTextProvider.class);var calls=new AtomicInteger();
        var pinned=new SpeechToTextProvider() {
            public String providerName(){return "pinned-original";}
            public Integer maxAttempts(){return withRetry?2:1;}
            public SpeechToTextResult transcribe(SpeechToTextRequest request) {
                assertThat(Files.exists(request.audioFile())).isTrue();int attempt=calls.incrementAndGet();
                if(withRetry && attempt==1) throw new AsrProviderException("Synthetic ASR rate limit",true,429);
                var atoms=request.audioFile().equals(plan.chunks().getFirst().audioFile())
                    ?List.of(new TranscribedSegment(0,0,0,"Complete first clip text"))
                    :List.of(new TranscribedSegment(0,1000,2222,"Second clip detail",TranscriptTimingSource.ASR,null));
                return new SpeechToTextResult("pinned-original","en",atoms.getFirst().text(),atoms,Duration.ofMillis(10),0,
                    Map.of("systemModelSnapshotId","snapshot","systemModelConfigVersion",10L));
            }
        };
        when(root.forExecution(ref)).thenReturn(pinned);
        var policies=mock(PipelinePolicyService.class);var settings=new PipelineTranslationProperties();
        var policy=settings.freezeWithSilence(Duration.ofSeconds(120),Duration.ofMinutes(15),1,1000,16000,1,1,4*1024*1024,2,List.of(0L));
        when(policies.find("task",9)).thenReturn(Optional.of(new PipelinePolicyService.Frozen(policy,"p",Instant.now().plusSeconds(1800),ref)));
        var mapper=mock(AnalysisTaskMapper.class);var task=new AnalysisTask();task.setId("task");task.setUserId(9L);task.setStatus("RUNNING");
        when(mapper.selectByIdAndUserId("task",9L)).thenReturn(task);
        var probe=mock(AudioDurationProbe.class);when(probe.probeDurationMillis(input)).thenReturn(70000L);
        var live=new AsrChunkingProperties();live.getChunkRetry().setMaxAttempts(1);live.getChunkRetry().setBackoff(List.of(Duration.ofSeconds(30)));
        new TranscribeAudioStep(root,null,live,workspace,mapper,probe).withSilencePlanning(policies,planner).execute(context);
        var output=context.speechToTextResult().orElseThrow();
        assertThat(calls.get()).isEqualTo(withRetry?3:2);verify(root,times(1)).forExecution(ref);verify(root,never()).transcribe(any());
        assertThat(output.segments()).hasSize(2);
        assertThat(output.segments().getFirst().startMillis()).isZero();assertThat(output.segments().getFirst().endMillis()).isEqualTo(30000);
        assertThat(output.segments().getFirst().timingSource()).isEqualTo(TranscriptTimingSource.SILENCE_SPLIT);
        assertThat(output.segments().getLast().startMillis()).isEqualTo(41000);assertThat(output.segments().getLast().endMillis()).isEqualTo(42222);
        assertThat(output.segments().getLast().timingSource()).isEqualTo(TranscriptTimingSource.ASR);
        assertThat(output.metadata().get("asrPhysicalAttempts")).isEqualTo(withRetry?3:2);assertThat(output.metadata().get("silenceClipCount")).isEqualTo(2);
        assertThat(Files.exists(clips)).isFalse();assertThat(Files.exists(input)).isTrue();
    }
}
