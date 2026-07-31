package com.example.courselingo.ai.asr;

import java.text.Normalizer;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class AsrTextNormalizer {

    private static final Pattern SPECIAL_TOKEN = Pattern.compile(
        "(?i)<\\|(?:en|zh|auto|speech|nospeech|neutral|happy|sad|angry|event_[^|]{0,32})\\|>|</?s>"
    );
    private static final Pattern REPEATED_PUNCTUATION = Pattern.compile("([!?;,，。！？；])\\1{1,}");
    private static final Pattern ISOLATED_CJK = Pattern.compile("(?<![\\p{IsHan}])(?<!\\S)[\\p{IsHan}](?!\\S)(?![\\p{IsHan}])");
    private static final List<Replacement> ENGLISH_TECHNICAL_JOINS = List.of(
        new Replacement("(?i)\\bSpringBoot\\b", "Spring Boot"),
        new Replacement("(?i)\\bAPIGateway\\b", "API Gateway"),
        new Replacement("(?i)\\bDockerCompose\\b", "Docker Compose"),
        new Replacement("(?i)\\bJavabackend\\b", "Java backend"),
        new Replacement("(?i)\\bHTTPrequest\\b", "HTTP request")
    );

    private AsrTextNormalizer() {
    }

    public static String normalize(String value, String language) {
        String text = Normalizer.normalize(value == null ? "" : value, Normalizer.Form.NFKC);
        text = SPECIAL_TOKEN.matcher(text).replaceAll(" ");
        StringBuilder cleaned = new StringBuilder(text.length());
        text.codePoints().forEach(codePoint -> {
            int type = Character.getType(codePoint);
            boolean forbidden = Character.isISOControl(codePoint)
                || type == Character.PRIVATE_USE
                || type == Character.SURROGATE
                || isMeaninglessEmoji(codePoint, type);
            if (!forbidden) {
                cleaned.appendCodePoint(codePoint);
            }
        });
        text = REPEATED_PUNCTUATION.matcher(cleaned).replaceAll("$1");
        if (isEnglish(language)) {
            for (Replacement replacement : ENGLISH_TECHNICAL_JOINS) {
                text = text.replaceAll(replacement.pattern(), replacement.value());
            }
            if (cjkRatio(text) < 0.02d) {
                text = ISOLATED_CJK.matcher(text).replaceAll(" ");
            }
        }
        return text.replaceAll("[\\t\\x0B\\f\\r ]+", " ")
            .replaceAll(" *\\n+ *", "\n")
            .strip();
    }

    public static List<TranscribedSegment> normalizeAndDeduplicate(
        List<TranscribedSegment> segments,
        String language
    ) {
        List<TranscribedSegment> result = new ArrayList<>();
        String previous = "";
        for (TranscribedSegment segment : segments == null ? List.<TranscribedSegment>of() : segments) {
            String current = normalize(segment.text(), language);
            current = removeBoundaryOverlap(previous, current);
            if (current.isBlank()) {
                continue;
            }
            result.add(new TranscribedSegment(
                result.size(), segment.startMillis(), segment.endMillis(), current
            ));
            previous = current;
        }
        return List.copyOf(result);
    }

    static String removeBoundaryOverlap(String previous, String current) {
        String left = previous == null ? "" : previous.strip();
        String right = current == null ? "" : current.strip();
        if (left.isBlank() || right.isBlank()) {
            return right;
        }
        String[] leftTokens = left.split("\\s+");
        String[] rightTokens = right.split("\\s+");
        int max = Math.min(12, Math.min(leftTokens.length, rightTokens.length));
        for (int size = max; size >= 2; size--) {
            boolean equal = true;
            for (int i = 0; i < size; i++) {
                if (!token(leftTokens[leftTokens.length - size + i]).equals(token(rightTokens[i]))) {
                    equal = false;
                    break;
                }
            }
            if (equal) {
                return String.join(" ", java.util.Arrays.copyOfRange(rightTokens, size, rightTokens.length)).strip();
            }
        }
        return right;
    }

    private static String token(String value) {
        return value.toLowerCase(Locale.ROOT).replaceAll("^[\\p{Punct}]+|[\\p{Punct}]+$", "");
    }

    private static boolean isEnglish(String language) {
        String normalized = language == null ? "" : language.replace('_', '-').toLowerCase(Locale.ROOT);
        return normalized.equals("en") || normalized.startsWith("en-");
    }

    private static double cjkRatio(String value) {
        long letters = value.codePoints().filter(Character::isLetter).count();
        long cjk = value.codePoints().filter(AsrTextNormalizer::isHan).count();
        return letters == 0L ? 0.0d : cjk / (double) letters;
    }

    private static boolean isHan(int codePoint) {
        return Character.UnicodeScript.of(codePoint) == Character.UnicodeScript.HAN;
    }

    private static boolean isMeaninglessEmoji(int codePoint, int type) {
        if (type != Character.OTHER_SYMBOL) {
            return false;
        }
        return codePoint >= 0x1F000 || codePoint == 0xFE0F || codePoint == 0x200D;
    }

    private record Replacement(String pattern, String value) {
    }
}
