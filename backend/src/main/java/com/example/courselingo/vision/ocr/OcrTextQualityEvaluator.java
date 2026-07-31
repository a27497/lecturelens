package com.example.courselingo.vision.ocr;

import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Arrays;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

public final class OcrTextQualityEvaluator {

    private static final double MIN_CONFIDENCE = 0.35d;
    private static final Pattern LATIN_WORD = Pattern.compile("[A-Za-z][A-Za-z0-9_+.#/-]{2,}");
    private static final Pattern CJK_RUN = Pattern.compile("[\\p{IsHan}]{2,}");
    private static final Pattern TECHNICAL = Pattern.compile(
        "(?i)(spring\\s*boot|api\\s*gateway|docker(?:\\s+compose)?|java|http|c\\+\\+|public\\s+static|"
            + "class\\s+\\w+|curl\\s+|npm\\s+|mvnw?|/[-a-z0-9_/]+|[-a-z0-9_]+\\.(?:java|yml|yaml|xml|json|ts|vue))"
    );

    private OcrTextQualityEvaluator() {
    }

    public static boolean isUseful(String text, Double confidence) {
        return evaluate(text, confidence, "", "").useful();
    }

    public static boolean isUseful(String text, Double confidence, String languageHint, String screenType) {
        return evaluate(text, confidence, languageHint, screenType).useful();
    }

    public static OcrTextQualityReport evaluate(
        String text,
        Double confidence,
        String languageHint,
        String screenType
    ) {
        String normalized = normalize(text);
        if (normalized.isBlank()) return rejected("empty", confidence, 0.0d, 0.0d, 0.0d);
        if (containsControlPrivateOrReplacement(normalized)) {
            return rejected("control_private_or_replacement_character", confidence, 0.0d, 1.0d, 0.0d);
        }
        if (confidence != null && (!Double.isFinite(confidence) || confidence < MIN_CONFIDENCE)) {
            return rejected("low_confidence", confidence, 0.0d, 0.0d, 0.0d);
        }

        int visible = 0;
        int lettersDigits = 0;
        int cjk = 0;
        int symbols = 0;
        int longestRepeatedRun = 1;
        int currentRun = 0;
        int previous = -1;
        for (int offset = 0; offset < normalized.length();) {
            int cp = normalized.codePointAt(offset);
            offset += Character.charCount(cp);
            if (Character.isWhitespace(cp)) continue;
            visible++;
            if (Character.isLetterOrDigit(cp)) lettersDigits++; else symbols++;
            if (Character.UnicodeScript.of(cp) == Character.UnicodeScript.HAN) cjk++;
            if (cp == previous) currentRun++; else currentRun = 1;
            longestRepeatedRun = Math.max(longestRepeatedRun, currentRun);
            previous = cp;
        }
        if (visible == 0) return rejected("empty", confidence, 0.0d, 0.0d, 0.0d);
        double textRatio = lettersDigits / (double) visible;
        double symbolRatio = symbols / (double) visible;

        String[] tokens = normalized.split("\\s+");
        int isolated = 0;
        int meaningful = 0;
        Map<String, Integer> tokenCounts = new HashMap<>();
        for (String token : tokens) {
            int length = token.codePointCount(0, token.length());
            long tokenTextChars = token.codePoints().filter(Character::isLetterOrDigit).count();
            if (length == 1 && tokenTextChars == 1) isolated++;
            if (LATIN_WORD.matcher(token).find() || CJK_RUN.matcher(token).find()) meaningful++;
            String key = token.toLowerCase(Locale.ROOT);
            tokenCounts.merge(key, 1, Integer::sum);
        }
        int duplicateTokens = tokenCounts.values().stream().mapToInt(count -> Math.max(0, count - 1)).sum();
        double isolatedRatio = tokens.length == 0 ? 0.0d : isolated / (double) tokens.length;
        double repeatedTokenRatio = tokens.length == 0 ? 0.0d : duplicateTokens / (double) tokens.length;
        boolean technical = TECHNICAL.matcher(normalized).find();
        int latinWords = countMatches(LATIN_WORD, normalized);
        int cjkRuns = countMatches(CJK_RUN, normalized);

        if (!technical && !Character.isLetterOrDigit(normalized.codePointAt(0))) {
            return rejected("symbol_prefixed_fragment", confidence, textRatio, symbolRatio, isolatedRatio);
        }

        if (longestRepeatedRun >= 6 || repeatedTokenRatio > 0.55d) {
            return rejected("repeated_noise", confidence, textRatio, symbolRatio, isolatedRatio);
        }
        if (!technical && isolated >= 3 && isolatedRatio > 0.30d && meaningful < 3) {
            return rejected("fragmented_single_character_tokens", confidence, textRatio, symbolRatio, isolatedRatio);
        }
        if (!technical && symbolRatio > 0.30d && meaningful < 3) {
            return rejected("symbol_heavy", confidence, textRatio, symbolRatio, isolatedRatio);
        }
        if (!technical && textRatio < 0.60d) {
            return rejected("insufficient_text_structure", confidence, textRatio, symbolRatio, isolatedRatio);
        }
        String hint = normalize(languageHint).toLowerCase(Locale.ROOT);
        boolean englishOnly = hint.matches("(?:eng|en)(?:[-_].*)?");
        if (englishOnly && cjk > Math.max(3, lettersDigits / 2) && latinWords < 2) {
            return rejected("language_hint_mismatch", confidence, textRatio, symbolRatio, isolatedRatio);
        }
        String screen = normalize(screenType).toUpperCase(Locale.ROOT);
        if ("OTHER".equals(screen) && confidence != null && confidence < 0.50d && !technical) {
            return rejected("low_information_scene", confidence, textRatio, symbolRatio, isolatedRatio);
        }
        if (technical && lettersDigits >= 6) {
            return accepted("technical_structure", confidence, textRatio, symbolRatio, isolatedRatio);
        }
        if ((latinWords >= 1 || cjkRuns >= 1) && lettersDigits >= 8 && meaningful >= 1) {
            return accepted("readable_text", confidence, textRatio, symbolRatio, isolatedRatio);
        }
        return rejected("insufficient_meaningful_text", confidence, textRatio, symbolRatio, isolatedRatio);
    }

    public static String withoutOcrEvidenceClause(String summary) {
        if (summary == null || summary.isBlank()) return "";
        return Arrays.stream(summary.split("；"))
            .map(String::strip)
            .filter(part -> !part.startsWith("画面文字包括："))
            .filter(part -> !part.isBlank())
            .collect(Collectors.joining("；"));
    }

    private static boolean containsControlPrivateOrReplacement(String text) {
        return text.codePoints().anyMatch(cp -> cp == 0xFFFD
            || Character.getType(cp) == Character.PRIVATE_USE
            || (Character.isISOControl(cp) && !Character.isWhitespace(cp)));
    }

    private static int countMatches(Pattern pattern, String text) {
        int count = 0;
        var matcher = pattern.matcher(text);
        while (matcher.find()) count++;
        return count;
    }

    private static OcrTextQualityReport accepted(
        String reason, Double confidence, double textRatio, double symbolRatio, double isolatedRatio
    ) {
        return new OcrTextQualityReport(true, reason, confidence, textRatio, symbolRatio, isolatedRatio);
    }

    private static OcrTextQualityReport rejected(
        String reason, Double confidence, double textRatio, double symbolRatio, double isolatedRatio
    ) {
        return new OcrTextQualityReport(false, reason, confidence, textRatio, symbolRatio, isolatedRatio);
    }

    private static String normalize(String value) {
        return value == null ? "" : value.replaceAll("\\s+", " ").strip();
    }

    public record OcrTextQualityReport(
        boolean useful,
        String reason,
        Double confidence,
        double textCharacterRatio,
        double symbolRatio,
        double isolatedTokenRatio
    ) {
    }
}
