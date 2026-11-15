package com.example.courselingo.subtitle.pipeline;

public record TranslationRecoveryPolicy(int maxRecoveries) {
    public TranslationRecoveryPolicy {if(maxRecoveries<0 || maxRecoveries>3)throw new IllegalArgumentException("Invalid recovery limit");}
}
