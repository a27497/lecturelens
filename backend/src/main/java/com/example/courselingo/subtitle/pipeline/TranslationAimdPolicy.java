package com.example.courselingo.subtitle.pipeline;

public record TranslationAimdPolicy(int inputTokenBudget,int minimum,int initial,int maximum,int successStreak,int processMaximum) {
    public TranslationAimdPolicy {
        if(inputTokenBudget<256 || inputTokenBudget>32768 || minimum!=1 || initial<minimum || initial>maximum
            || maximum<1 || maximum>16 || successStreak<1 || successStreak>20 || processMaximum<1 || processMaximum>16)
            throw new IllegalArgumentException("Invalid translation concurrency policy");
    }
}
