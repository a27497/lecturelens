package com.example.courselingo.systemmodel;

public enum SystemModelFeature {
    TRANSLATION_FULL_TEXT(true),
    SUBTITLE_TRANSLATION(true),
    LEARNING_PACKAGE(true),
    COURSE_QA(true),
    COURSE_CHAPTER(true),
    VISION_FRAME_ANALYSIS(true),
    ASR_TRANSCRIPTION(true),
    FUSION_SUMMARY(false);

    private final boolean connected;

    SystemModelFeature(boolean connected) {
        this.connected = connected;
    }

    public boolean connected() {
        return connected;
    }
}
