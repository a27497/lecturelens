package com.example.courselingo.media;

import com.example.courselingo.ai.asr.AsrPipelinePolicy;

/** Frozen adjacent-clip merge bounds; independent of adaptive ASR scheduling. */
public record AudioClipMergePolicy(long minMillis, long targetMillis, long maxMillis) {
    public AudioClipMergePolicy {
        if (minMillis < 1000 || targetMillis < minMillis || maxMillis < targetMillis || maxMillis > 120000)
            throw new IllegalArgumentException("Invalid audio clip merge policy");
    }

    public static AudioClipMergePolicy from(AsrPipelinePolicy asr) {
        if (asr == null || !asr.mergeEnabled()) return null;
        return new AudioClipMergePolicy(asr.mergeMinMillis(), asr.mergeTargetMillis(), asr.mergeMaxMillis());
    }
}
