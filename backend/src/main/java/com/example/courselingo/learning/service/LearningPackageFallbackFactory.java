package com.example.courselingo.learning.service;

import com.example.courselingo.learning.dto.GlossaryItem;
import com.example.courselingo.learning.dto.KeyPointItem;
import com.example.courselingo.learning.dto.QaItem;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

final class LearningPackageFallbackFactory {
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final Pattern TERM = Pattern.compile("[A-Za-z][A-Za-z0-9_+.#/-]{2,}");

    private LearningPackageFallbackFactory() { }

    static LearningPackageResponseParser.ParsedLearningPackage build(
        String evidenceText,
        String targetLanguage,
        LearningPackageQualityProfile profile
    ) {
        boolean chinese = targetLanguage != null && targetLanguage.toLowerCase(Locale.ROOT).startsWith("zh");
        List<String> sentences = sentences(evidenceText);
        String title = chinese ? "课程学习资料" : "Learning Package";
        String summary = buildSummary(sentences, profile, chinese);
        List<String> selected = distributed(
            sentences,
            profile.sparseEvidence() ? 3 : Math.max(profile.keyPointsMin(), profile.qaMin())
        );
        List<KeyPointItem> keyPoints = new ArrayList<>();
        for (int index = 0; index < Math.min(profile.keyPointsMax(), selected.size()); index++) {
            keyPoints.add(new KeyPointItem(index + 1, limit(selected.get(index), 180)));
        }
        List<GlossaryItem> glossary = profile.glossaryMin() == 0 ? List.of() : glossary(sentences, profile, chinese);
        List<QaItem> qa = new ArrayList<>();
        int qaCount = profile.qaMin() == 0 ? 0 : Math.min(profile.qaMax(), selected.size());
        for (int index = 0; index < qaCount; index++) {
            String point = limit(selected.get(index), 220);
            qa.add(new QaItem(
                chinese ? "课程第 " + (index + 1) + " 个所选证据片段说明了什么？"
                    : "What does selected course evidence section " + (index + 1) + " explain?",
                point
            ));
        }
        return new LearningPackageResponseParser.ParsedLearningPackage(
            title, summary, json(keyPoints), json(glossary), json(qa)
        );
    }

    private static String buildSummary(List<String> sentences, LearningPackageQualityProfile profile, boolean chinese) {
        if (sentences.isEmpty()) {
            return chinese ? "课程证据不足，当前资料仅保留可验证内容。" : "The course evidence is sparse; only verifiable content is retained.";
        }
        StringBuilder summary = new StringBuilder();
        List<String> candidates = new ArrayList<>(distributed(sentences, Math.min(3, sentences.size())));
        for (String sentence : distributed(sentences, Math.min(24, Math.max(6, sentences.size())))) {
            if (!candidates.contains(sentence)) candidates.add(sentence);
        }
        int appended = 0;
        for (String sentence : candidates) {
            if (summary.length() > 0) summary.append(' ');
            summary.append(sentence);
            appended++;
            if (appended >= Math.min(3, sentences.size()) && effective(summary.toString()) >= profile.summaryMin()) break;
        }
        String value = summary.toString().replaceAll("\\s+", " ").strip();
        return limit(value, profile.summaryMax());
    }

    private static List<GlossaryItem> glossary(
        List<String> sentences,
        LearningPackageQualityProfile profile,
        boolean chinese
    ) {
        Map<String, String> terms = new LinkedHashMap<>();
        for (String sentence : sentences) {
            var matcher = TERM.matcher(sentence);
            while (matcher.find() && terms.size() < profile.glossaryMax()) {
                String term = matcher.group();
                terms.putIfAbsent(term.toLowerCase(Locale.ROOT), term);
            }
        }
        if (terms.size() < profile.glossaryMin()) {
            for (String sentence : distributed(sentences, profile.glossaryMin())) {
                String phrase = limit(sentence.replaceAll("[，。！？,.!?]", "").strip(), 24);
                if (!phrase.isBlank()) terms.putIfAbsent(phrase.toLowerCase(Locale.ROOT), phrase);
                if (terms.size() >= profile.glossaryMin()) break;
            }
        }
        List<GlossaryItem> result = new ArrayList<>();
        for (String term : terms.values()) {
            String evidence = sentences.stream().filter(sentence -> sentence.contains(term)).findFirst()
                .orElse(sentences.isEmpty() ? term : sentences.getFirst());
            String definition = chinese ? "课程证据中的相关说明：" + limit(evidence, 160) : limit(evidence, 180);
            result.add(new GlossaryItem(term, definition, ""));
            if (result.size() >= profile.glossaryMax()) break;
        }
        return result;
    }

    private static List<String> sentences(String text) {
        if (text == null || text.isBlank()) return List.of();
        List<String> values = new ArrayList<>();
        Set<String> seen = new LinkedHashSet<>();
        for (String part : text.strip().split("(?<=[.!?。！？])\\s*|[\\r\\n]+")) {
            String value = part.replaceAll("\\s+", " ").strip();
            if (effective(value) >= 8 && seen.add(value.toLowerCase(Locale.ROOT))) values.add(value);
        }
        if (values.isEmpty()) values.add(limit(text, 400));
        return values;
    }

    private static List<String> distributed(List<String> values, int desired) {
        if (values.isEmpty() || desired <= 0) return List.of();
        int count = Math.min(desired, values.size());
        List<String> result = new ArrayList<>();
        for (int index = 0; index < count; index++) {
            int sourceIndex = count == 1 ? 0 : (int) Math.round(index * (values.size() - 1.0d) / (count - 1.0d));
            result.add(values.get(sourceIndex));
        }
        return result;
    }

    private static int effective(String value) {
        return value == null ? 0 : (int) value.codePoints().filter(Character::isLetterOrDigit).count();
    }

    private static String limit(String value, int max) {
        String safe = value == null ? "" : value.replaceAll("\\s+", " ").strip();
        if (safe.length() <= max) return safe;
        return safe.substring(0, max).strip();
    }

    private static String json(Object value) {
        try {
            return MAPPER.writeValueAsString(value);
        } catch (Exception exception) {
            return "[]";
        }
    }
}
