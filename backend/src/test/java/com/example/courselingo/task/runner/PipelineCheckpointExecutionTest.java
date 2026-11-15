package com.example.courselingo.task.runner;

import com.example.courselingo.ai.asr.SpeechToTextResult;
import com.example.courselingo.task.service.*;
import com.example.courselingo.vision.keyframe.VideoKeyframeEvidenceLifecycleService;
import java.util.*;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

class PipelineCheckpointExecutionTest {
    @Test void committedSourceAndFramesSkipTheirPhysicalWorkAndClearTheExecutionScope() {
        var store=mock(PipelineSourceCheckpointStore.class);
        when(store.restore("t",9,"event",2)).thenReturn(Optional.of(new SpeechToTextResult("mock","en","text",List.of(),Duration.ZERO,1000,Map.of())));
        when(store.captureReady("t",9,"event",2)).thenReturn(true);
        var executed=new ArrayList<PipelineAnalysisTaskStepName>();
        List<PipelineAnalysisTaskStep> steps=PipelineAnalysisTaskStepName.ordered().stream().map(name->new PipelineAnalysisTaskStep(){
            public PipelineAnalysisTaskStepName name(){return name;}
            public void execute(PipelineAnalysisTaskStepContext context){
                assertThat(PipelineExecutionScope.current().epoch()).isEqualTo(2);
                if(name==PipelineAnalysisTaskStepName.TRANSLATE_SUBTITLES)assertThat(context.requireSpeechToTextResult().fullText()).isEqualTo("text");
                executed.add(name);
            }
        }).map(PipelineAnalysisTaskStep.class::cast).toList();
        var executor=new PipelineAnalysisTaskWorkExecutor(steps).withCheckpoints(store);
        assertThat(executor.execute(new AnalysisTaskExecutionContext("t","u",9L,"en","zh-CN","event",null,2,2)).success()).isTrue();
        assertThat(executed).doesNotContain(PipelineAnalysisTaskStepName.EXTRACT_AUDIO,PipelineAnalysisTaskStepName.TRANSCRIBE,
            PipelineAnalysisTaskStepName.PERSIST_SUBTITLES,PipelineAnalysisTaskStepName.EXTRACT_KEYFRAMES);
        assertThat(PipelineExecutionScope.current()).isNull();
    }
    @Test void recoverableFailureRetainsEvidenceWhileWorkspaceScopeIsAlwaysCleared() {
        var store=mock(PipelineSourceCheckpointStore.class);
        when(store.restore("t",9,"event",2)).thenReturn(Optional.empty());
        var cleanup=mock(VideoKeyframeEvidenceLifecycleService.class);
        List<PipelineAnalysisTaskStep> steps=PipelineAnalysisTaskStepName.ordered().stream().map(name->new PipelineAnalysisTaskStep(){
            public PipelineAnalysisTaskStepName name(){return name;}
            public void execute(PipelineAnalysisTaskStepContext context){if(name==PipelineAnalysisTaskStepName.GENERATE_ARTIFACTS)throw new IllegalStateException("Synthetic failure");}
        }).map(PipelineAnalysisTaskStep.class::cast).toList();
        var executor=new PipelineAnalysisTaskWorkExecutor(steps,null,null,cleanup).withCheckpoints(store);
        assertThatThrownBy(()->executor.execute(new AnalysisTaskExecutionContext("t","u",9L,"en","zh-CN","event",null,2,2)))
            .isInstanceOf(PipelineAnalysisTaskStepException.class);
        verifyNoInteractions(cleanup);assertThat(PipelineExecutionScope.current()).isNull();
    }
}
