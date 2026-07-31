package com.example.courselingo.learning.service;

import com.example.courselingo.learning.dto.GlossaryItem;
import com.example.courselingo.learning.dto.KeyPointItem;
import com.example.courselingo.learning.dto.QaItem;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

final class LearningPackageQualityValidator {
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final TypeReference<List<KeyPointItem>> KEYS = new TypeReference<>() { };
    private static final TypeReference<List<GlossaryItem>> TERMS = new TypeReference<>() { };
    private static final TypeReference<List<QaItem>> QA = new TypeReference<>() { };

    private LearningPackageQualityValidator() { }

    static LearningPackageQualityReport validate(
        LearningPackageResponseParser.ParsedLearningPackage value,
        LearningPackageQualityProfile profile,
        String targetLanguage
    ) {
        List<String> deficits = new ArrayList<>();
        int summaryChars = effectiveCharacters(value.summary());
        List<KeyPointItem> keys = read(value.keyPointsJson(), KEYS);
        List<GlossaryItem> terms = read(value.glossaryJson(), TERMS);
        List<QaItem> qa = read(value.qaJson(), QA);
        countDeficit(deficits, "summary", summaryChars, profile.summaryMin(), profile.summaryMax());
        countDeficit(deficits, "keyPoints", distinct(keys.stream().map(KeyPointItem::text).toList()), profile.keyPointsMin(), profile.keyPointsMax());
        countDeficit(deficits, "glossary", distinct(terms.stream().map(GlossaryItem::term).toList()), profile.glossaryMin(), profile.glossaryMax());
        countDeficit(deficits, "qa", distinct(qa.stream().map(QaItem::question).toList()), profile.qaMin(), profile.qaMax());
        if (!profile.sparseEvidence() && isChinese(targetLanguage)) {
            if (!containsHan(value.title())) deficits.add("title is not in the target Chinese language");
            if (!containsHan(value.summary())) deficits.add("summary is not in the target Chinese language");
        }
        return new LearningPackageQualityReport(deficits.isEmpty(), deficits);
    }

    private static void countDeficit(List<String> deficits, String field, int actual, int min, int max) {
        if (actual < min) deficits.add(field + " has " + actual + ", requires at least " + min);
        if (actual > max) deficits.add(field + " has " + actual + ", allows at most " + max);
    }

    private static int distinct(List<String> values) {
        Set<String> normalized = new HashSet<>();
        for (String value : values) {
            if (value != null && !value.isBlank()) normalized.add(value.replaceAll("\\s+", " ").strip().toLowerCase(Locale.ROOT));
        }
        return normalized.size();
    }

    private static int effectiveCharacters(String value) {
        return value == null ? 0 : (int) value.codePoints().filter(Character::isLetterOrDigit).count();
    }

    private static boolean containsHan(String value) {
        return value != null && value.codePoints().anyMatch(cp -> Character.UnicodeScript.of(cp) == Character.UnicodeScript.HAN);
    }

    private static boolean isChinese(String language) {
        return language != null && language.toLowerCase(Locale.ROOT).startsWith("zh");
    }

    private static <T> List<T> read(String json, TypeReference<List<T>> type) {
        try {
            return json == null || json.isBlank() ? List.of() : MAPPER.readValue(json, type);
        } catch (Exception ignored) {
            return List.of();
        }
    }
}
