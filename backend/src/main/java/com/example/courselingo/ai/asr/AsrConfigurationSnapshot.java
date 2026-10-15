package com.example.courselingo.ai.asr;

import java.util.Map;

/** Nonsecret deployment options frozen alongside a task's resolved ASR route. */
public record AsrConfigurationSnapshot(
        long bailianConnectMillis,
        long bailianMaxAudioBytes,
        boolean languageHintEnabled,
        String context,
        Map<String, Integer> vocabulary,
        long siliconFlowConnectMillis,
        long siliconFlowMaxAudioBytes,
        String mockLanguage,
        String mockText,
        long mockSegmentMillis) {
    public AsrConfigurationSnapshot {
        vocabulary = java.util.Collections.unmodifiableMap(new java.util.TreeMap<>(vocabulary));
    }

    public static AsrConfigurationSnapshot capture(
            BailianAsrProperties bailian,
            SiliconFlowAsrProperties silicon,
            MockAsrProperties mock) {
        return new AsrConfigurationSnapshot(
                bailian.getConnectTimeout().toMillis(),
                bailian.getMaxAudioFileSize().toBytes(),
                bailian.isLanguageHintEnabled(),
                bailian.getContext(),
                bailian.getVocabulary(),
                silicon.getConnectTimeout().toMillis(),
                silicon.getMaxAudioFileSize().toBytes(),
                mock.getDefaultLanguage(),
                mock.getDefaultText(),
                mock.getSegmentDurationMillis());
    }
}
