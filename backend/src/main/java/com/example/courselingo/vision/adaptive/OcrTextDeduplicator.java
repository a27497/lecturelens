package com.example.courselingo.vision.adaptive;

import java.text.Normalizer;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/** OCR deduplication requires temporal, visual, and textual agreement at the same time. */
public final class OcrTextDeduplicator {

    public record OcrFrame(double timestampSeconds, long perceptualHash, String text) {

        public OcrFrame {
            if (!Double.isFinite(timestampSeconds) || timestampSeconds < 0.0) {
                throw new IllegalArgumentException("timestampSeconds must be finite and non-negative");
            }
            text = text == null ? "" : text;
        }
    }

    public record Config(
        int maximumHashDistance,
        double minimumTextSimilarity,
        double maximumTimeDistanceSeconds,
        int meaningfulAdditionCharacters
    ) {

        public Config {
            if (maximumHashDistance < 0 || maximumHashDistance > 64) {
                throw new IllegalArgumentException("maximumHashDistance must be between 0 and 64");
            }
            if (!Double.isFinite(minimumTextSimilarity) || minimumTextSimilarity < 0.0
                || minimumTextSimilarity > 1.0) {
                throw new IllegalArgumentException("minimumTextSimilarity must be between 0 and 1");
            }
            if (!Double.isFinite(maximumTimeDistanceSeconds) || maximumTimeDistanceSeconds < 0.0) {
                throw new IllegalArgumentException("maximumTimeDistanceSeconds must be non-negative");
            }
            if (meaningfulAdditionCharacters < 1 || meaningfulAdditionCharacters > 1_000) {
                throw new IllegalArgumentException("meaningfulAdditionCharacters is out of range");
            }
        }

        public static Config defaults() {
            return new Config(6, 0.92, 120.0, 4);
        }
    }

    private final Config config;

    public OcrTextDeduplicator() {
        this(Config.defaults());
    }

    public OcrTextDeduplicator(Config config) {
        this.config = java.util.Objects.requireNonNull(config, "config");
    }

    public boolean isDuplicate(OcrFrame previous, OcrFrame candidate) {
        if (previous == null || candidate == null) {
            return false;
        }
        if (Math.abs(candidate.timestampSeconds() - previous.timestampSeconds())
            > config.maximumTimeDistanceSeconds()) {
            return false;
        }
        if (PerceptualHashDeduplicator.hammingDistance(
            previous.perceptualHash(), candidate.perceptualHash()) > config.maximumHashDistance()) {
            return false;
        }
        String previousText = normalize(previous.text());
        String candidateText = normalize(candidate.text());
        if (previousText.isBlank() || candidateText.isBlank()) {
            return false;
        }
        if (textSimilarity(previousText, candidateText) < config.minimumTextSimilarity()) {
            return false;
        }
        return !hasMeaningfulAddition(previous.text(), candidate.text());
    }

    public boolean isDuplicate(
        String previousText,
        long previousHash,
        double previousTimestamp,
        String candidateText,
        long candidateHash,
        double candidateTimestamp
    ) {
        return isDuplicate(
            new OcrFrame(previousTimestamp, previousHash, previousText),
            new OcrFrame(candidateTimestamp, candidateHash, candidateText)
        );
    }

    public List<OcrFrame> deduplicate(List<OcrFrame> frames) {
        if (frames == null || frames.isEmpty()) {
            return List.of();
        }
        List<OcrFrame> kept = new ArrayList<>();
        for (OcrFrame candidate : frames) {
            if (candidate == null) {
                continue;
            }
            boolean duplicate = kept.stream().anyMatch(previous -> isDuplicate(previous, candidate));
            if (!duplicate) {
                kept.add(candidate);
            }
        }
        return List.copyOf(kept);
    }

    public static String normalize(String text) {
        if (text == null || text.isBlank()) {
            return "";
        }
        return Normalizer.normalize(text, Normalizer.Form.NFKC)
            .toLowerCase(Locale.ROOT)
            .replaceAll("\\s+", " ")
            .trim();
    }

    public static double textSimilarity(String first, String second) {
        String left = normalize(first);
        String right = normalize(second);
        if (left.equals(right)) {
            return 1.0;
        }
        if (left.isEmpty() || right.isEmpty()) {
            return 0.0;
        }
        int distance = levenshtein(left, right);
        return Math.max(0.0, 1.0 - distance / (double) Math.max(left.length(), right.length()));
    }

    public boolean hasMeaningfulAddition(String previousText, String candidateText) {
        String previous = normalize(previousText);
        String candidate = normalize(candidateText);
        if (candidate.length() >= previous.length() + config.meaningfulAdditionCharacters()
            && candidate.contains(previous)) {
            return true;
        }
        Set<String> previousLines = normalizedLines(previousText);
        for (String line : normalizedLines(candidateText)) {
            if (line.length() >= config.meaningfulAdditionCharacters() && !previousLines.contains(line)) {
                String novel = line;
                if (previousLines.stream().noneMatch(existing -> textSimilarity(existing, novel) >= 0.96)) {
                    return true;
                }
            }
        }
        return false;
    }

    private static Set<String> normalizedLines(String text) {
        Set<String> lines = new LinkedHashSet<>();
        if (text == null) {
            return lines;
        }
        for (String line : Normalizer.normalize(text, Normalizer.Form.NFKC).split("\\R")) {
            String normalized = normalize(line);
            if (!normalized.isBlank()) {
                lines.add(normalized);
            }
        }
        return lines;
    }

    private static int levenshtein(String first, String second) {
        if (first.length() > second.length()) {
            return levenshtein(second, first);
        }
        int[] previous = new int[first.length() + 1];
        int[] current = new int[first.length() + 1];
        for (int index = 0; index <= first.length(); index++) {
            previous[index] = index;
        }
        for (int right = 1; right <= second.length(); right++) {
            current[0] = right;
            for (int left = 1; left <= first.length(); left++) {
                int substitution = previous[left - 1]
                    + (first.charAt(left - 1) == second.charAt(right - 1) ? 0 : 1);
                current[left] = Math.min(Math.min(current[left - 1] + 1, previous[left] + 1), substitution);
            }
            int[] swap = previous;
            previous = current;
            current = swap;
        }
        return previous[first.length()];
    }
}
