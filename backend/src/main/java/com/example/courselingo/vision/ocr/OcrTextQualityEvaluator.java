package com.example.courselingo.vision.ocr;

import java.util.regex.Pattern;

public final class OcrTextQualityEvaluator {

    private static final double MIN_CONFIDENCE = 0.35d;
    private static final Pattern CJK_PATTERN = Pattern.compile("[\\p{IsHan}]");
    private static final Pattern LATIN_WORD_PATTERN = Pattern.compile("[A-Za-z]{3,}");
    private static final Pattern REPLACEMENT_OR_NOISE_PATTERN = Pattern.compile("[?\\uFFFD…=]");

    private OcrTextQualityEvaluator() {
    }

    public static boolean isUseful(String text, Double confidence) {
        String normalized = normalize(text);
        if (normalized.isBlank()) {
            return false;
        }
        if (confidence != null && confidence < MIN_CONFIDENCE) {
            return false;
        }
        int cjkCount = countMatches(CJK_PATTERN, normalized);
        if (cjkCount >= 4) {
            return true;
        }
        int latinWordCount = countMatches(LATIN_WORD_PATTERN, normalized);
        int textChars = countTextChars(normalized);
        int visibleChars = countVisibleChars(normalized);
        if (visibleChars == 0) {
            return false;
        }
        double textRatio = textChars / (double) visibleChars;
        boolean hasNoiseMarker = REPLACEMENT_OR_NOISE_PATTERN.matcher(normalized).find();
        if (hasNoiseMarker && latinWordCount < 2 && cjkCount < 4) {
            return false;
        }
        if (startsWithSymbol(normalized) && latinWordCount < 3 && cjkCount < 4) {
            return false;
        }
        return latinWordCount >= 1 && textChars >= 8 && textRatio >= 0.65d;
    }

    private static String normalize(String text) {
        return text == null ? "" : text.replaceAll("\\s+", " ").strip();
    }

    private static int countMatches(Pattern pattern, String text) {
        int count = 0;
        var matcher = pattern.matcher(text);
        while (matcher.find()) {
            count++;
        }
        return count;
    }

    private static int countTextChars(String text) {
        int count = 0;
        for (int i = 0; i < text.length(); i++) {
            char ch = text.charAt(i);
            if (Character.isLetterOrDigit(ch)) {
                count++;
            }
        }
        return count;
    }

    private static int countVisibleChars(String text) {
        int count = 0;
        for (int i = 0; i < text.length(); i++) {
            if (!Character.isWhitespace(text.charAt(i))) {
                count++;
            }
        }
        return count;
    }

    private static boolean startsWithSymbol(String text) {
        if (text.isBlank()) {
            return false;
        }
        int first = text.codePointAt(0);
        return !Character.isLetterOrDigit(first);
    }
}
