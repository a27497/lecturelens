package com.example.courselingo.modelrouting;

import java.util.EnumSet;
import java.util.Set;

public enum AiModelStage {
    TRANSLATION_FULL_TEXT(EnumSet.of(ModelCapability.TEXT_CHAT, ModelCapability.JSON_OUTPUT), true),
    SUBTITLE_TRANSLATION(EnumSet.of(ModelCapability.TEXT_CHAT, ModelCapability.JSON_OUTPUT), true),
    LEARNING_PACKAGE(EnumSet.of(ModelCapability.TEXT_CHAT, ModelCapability.JSON_OUTPUT), true),
    VISION_FRAME_ANALYSIS(EnumSet.of(ModelCapability.VISION, ModelCapability.JSON_OUTPUT), false),
    VISION_OCR(EnumSet.of(ModelCapability.OCR), false),
    FUSION_SUMMARY(EnumSet.of(ModelCapability.TEXT_CHAT, ModelCapability.JSON_OUTPUT), false),
    COURSE_QA(EnumSet.of(ModelCapability.TEXT_CHAT, ModelCapability.JSON_OUTPUT), true),
    COURSE_CHAPTER(EnumSet.of(ModelCapability.TEXT_CHAT, ModelCapability.JSON_OUTPUT), true),
    EMBEDDING(EnumSet.of(ModelCapability.EMBEDDING), false);

    private final Set<ModelCapability> requiredCapabilities;
    private final boolean active;

    AiModelStage(Set<ModelCapability> requiredCapabilities, boolean active) {
        this.requiredCapabilities = Set.copyOf(requiredCapabilities);
        this.active = active;
    }

    public Set<ModelCapability> requiredCapabilities() {
        return requiredCapabilities;
    }

    public boolean active() {
        return active;
    }

    public static Set<AiModelStage> activeStages() {
        return EnumSet.allOf(AiModelStage.class).stream()
            .filter(AiModelStage::active)
            .collect(java.util.stream.Collectors.toCollection(() -> EnumSet.noneOf(AiModelStage.class)));
    }
}
