package com.example.courselingo.ai.asr;

/** An interval's provenance, not a claim of word-level timestamp accuracy. */
public enum TranscriptTimingSource { ASR, SILENCE_SPLIT, AUDIO_CLIP, EMBEDDED_SUBTITLE, ESTIMATED }
