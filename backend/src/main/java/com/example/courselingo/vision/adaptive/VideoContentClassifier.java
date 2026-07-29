package com.example.courselingo.vision.adaptive;

import java.util.HashSet;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Pattern;

/** Deterministic content classification from OCR and existing image/scene signals. */
public final class VideoContentClassifier {

    private static final Pattern CODE_WORD = Pattern.compile(
        "(?i)\\b(class|interface|public|private|protected|static|void|return|import|package|function|const|let|var|if|else|for|while|try|catch|select|insert|update|delete|error|exception|build|test)\\b"
    );
    private static final Pattern TERMINAL_PROMPT = Pattern.compile(
        "(?m)(^|\\n)\\s*(?:[$#>]|PS>|[A-Za-z]:\\\\)|(?:error|warning|failed|success|passed)\\b",
        Pattern.CASE_INSENSITIVE
    );

    public record Config(
        int slideMinimumTextCharacters,
        int lowInformationMaximumTextCharacters,
        double codeSymbolRatioThreshold,
        double visualEdgeDensityThreshold,
        double visualSceneScoreThreshold
    ) {

        public Config {
            if (slideMinimumTextCharacters < 1 || lowInformationMaximumTextCharacters < 0) {
                throw new IllegalArgumentException("content text thresholds are invalid");
            }
            requireUnit(codeSymbolRatioThreshold, "codeSymbolRatioThreshold");
            requireUnit(visualEdgeDensityThreshold, "visualEdgeDensityThreshold");
            requireUnit(visualSceneScoreThreshold, "visualSceneScoreThreshold");
        }

        public static Config defaults() {
            return new Config(24, 12, 0.08d, 0.035d, 0.45d);
        }

        private static void requireUnit(double value, String name) {
            if (!Double.isFinite(value) || value < 0.0d || value > 1.0d) {
                throw new IllegalArgumentException(name + " must be between 0 and 1");
            }
        }
    }

    private final Config config;

    public VideoContentClassifier() {
        this(Config.defaults());
    }

    public VideoContentClassifier(Config config) {
        this.config = config == null ? Config.defaults() : config;
    }

    public VideoContentType classify(String ocrText, double edgeDensity, double sceneScore, String screenType) {
        String normalizedScreenType = clean(screenType).toUpperCase(Locale.ROOT);
        if (normalizedScreenType.contains("CODE") || normalizedScreenType.contains("TERMINAL")) {
            return VideoContentType.CODE_OR_TERMINAL;
        }
        if (normalizedScreenType.contains("SLIDE") || normalizedScreenType.contains("DOCUMENT")) {
            return VideoContentType.SLIDE;
        }
        if (normalizedScreenType.contains("DEMO") || normalizedScreenType.contains("DIAGRAM")
            || normalizedScreenType.contains("CHART")) {
            return VideoContentType.VISUAL_DEMO;
        }

        String text = clean(ocrText);
        int characters = nonWhitespaceCharacters(text);
        double symbolRatio = symbolRatio(text);
        boolean codeSyntax = CODE_WORD.matcher(text).find()
            || TERMINAL_PROMPT.matcher(text).find()
            || containsCodePunctuation(text);
        if (characters >= config.lowInformationMaximumTextCharacters()
            && (symbolRatio >= config.codeSymbolRatioThreshold() || codeSyntax)) {
            return VideoContentType.CODE_OR_TERMINAL;
        }
        if (characters >= config.slideMinimumTextCharacters()) {
            return VideoContentType.SLIDE;
        }
        if (edgeDensity >= config.visualEdgeDensityThreshold() || sceneScore >= config.visualSceneScoreThreshold()) {
            return VideoContentType.VISUAL_DEMO;
        }
        if (characters <= config.lowInformationMaximumTextCharacters()
            && edgeDensity < config.visualEdgeDensityThreshold() * 0.6d) {
            return VideoContentType.TALKING_OR_LOW_INFORMATION;
        }
        return VideoContentType.UNKNOWN;
    }

    public static double textChangeRatio(String left, String right) {
        Set<String> leftTokens = tokens(left);
        Set<String> rightTokens = tokens(right);
        if (leftTokens.isEmpty() && rightTokens.isEmpty()) {
            return 0.0d;
        }
        if (leftTokens.isEmpty() || rightTokens.isEmpty()) {
            return 1.0d;
        }
        Set<String> intersection = new HashSet<>(leftTokens);
        intersection.retainAll(rightTokens);
        Set<String> union = new HashSet<>(leftTokens);
        union.addAll(rightTokens);
        return 1.0d - intersection.size() / (double) union.size();
    }

    private static Set<String> tokens(String value) {
        String text = clean(value).toLowerCase(Locale.ROOT);
        if (text.isBlank()) {
            return Set.of();
        }
        Set<String> tokens = new HashSet<>();
        for (String token : text.split("(?U)[^\\p{L}\\p{N}_$#./:\\\\-]+")) {
            if (!token.isBlank()) {
                tokens.add(token);
            }
        }
        return tokens;
    }

    private static boolean containsCodePunctuation(String text) {
        return text.contains("{") || text.contains("}") || text.contains(";")
            || text.contains("=>") || text.contains("::") || text.contains("</")
            || text.contains("===") || text.contains("Traceback");
    }

    private static double symbolRatio(String text) {
        int nonWhitespace = 0;
        int symbols = 0;
        for (int index = 0; index < text.length(); index++) {
            char value = text.charAt(index);
            if (Character.isWhitespace(value)) {
                continue;
            }
            nonWhitespace++;
            if (!Character.isLetterOrDigit(value)) {
                symbols++;
            }
        }
        return nonWhitespace == 0 ? 0.0d : symbols / (double) nonWhitespace;
    }

    private static int nonWhitespaceCharacters(String text) {
        int count = 0;
        for (int index = 0; index < text.length(); index++) {
            if (!Character.isWhitespace(text.charAt(index))) {
                count++;
            }
        }
        return count;
    }

    private static String clean(String value) {
        return value == null ? "" : value.replaceAll("\\s+", " ").strip();
    }
}
