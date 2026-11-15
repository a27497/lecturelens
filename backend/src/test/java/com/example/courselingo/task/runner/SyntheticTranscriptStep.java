package com.example.courselingo.task.runner;

import com.example.courselingo.ai.asr.SpeechToTextResult;
import com.example.courselingo.ai.asr.TranscribedSegment;
import java.time.Duration;
import java.util.List;
import java.util.Map;

/** Test boundary: supplies synthetic ASR observations without media or supplier access. */
public final class SyntheticTranscriptStep implements PipelineAnalysisTaskStep {
    private final String source;
    public SyntheticTranscriptStep(String source) { this.source = source; }
    public PipelineAnalysisTaskStepName name() { return PipelineAnalysisTaskStepName.TRANSCRIBE; }
    public void execute(PipelineAnalysisTaskStepContext context) {
        context.setSpeechToTextResult(new SpeechToTextResult("mock", "en", source,
            List.of(new TranscribedSegment(0, 0L, 30000L, source)), Duration.ZERO, 30000L, Map.of()));
    }
}
