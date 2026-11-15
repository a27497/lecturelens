package com.example.courselingo.subtitle.pipeline;

/** This candidate qualifies source-only material input; overlap needs a separately qualified protocol. */
public record PreparationFlowPolicy(boolean sourceOnly,boolean streamingTranslation,boolean materialsParallel) {
    public PreparationFlowPolicy {
        if(streamingTranslation || materialsParallel)
            throw new IllegalArgumentException("C/E overlap is not qualified for this candidate");
    }
}
