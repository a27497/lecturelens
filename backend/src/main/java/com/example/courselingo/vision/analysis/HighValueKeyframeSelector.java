package com.example.courselingo.vision.analysis;

import com.example.courselingo.vision.keyframe.KeyframeSelectionReason;
import com.example.courselingo.vision.keyframe.VideoKeyframe;
import com.example.courselingo.vision.ocr.OcrStatus;
import com.example.courselingo.vision.ocr.VideoKeyframeOcr;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class HighValueKeyframeSelector {

    public List<VideoKeyframe> select(
        List<VideoKeyframe> keyframes,
        Collection<VideoKeyframeOcr> ocrRows,
        VisionAnalysisProperties properties
    ) {
        if (keyframes == null || keyframes.isEmpty()) {
            return List.of();
        }
        VisionAnalysisProperties effective = properties == null ? new VisionAnalysisProperties() : properties;
        if (effective.getMaxFramesTotal() <= 0 || effective.getMaxFramesPerMinute() <= 0) {
            return List.of();
        }
        Map<Long, String> ocrByKeyframeId = ocrTextByKeyframeId(ocrRows);
        List<ScoredKeyframe> scored = keyframes.stream()
            .map(keyframe -> score(keyframe, ocrByKeyframeId.getOrDefault(keyframe.getId(), "")))
            .filter(item -> item.score() > 0)
            .sorted(Comparator.comparingInt(ScoredKeyframe::score).reversed()
                .thenComparing(item -> safeTimestamp(item.keyframe())))
            .toList();
        List<VideoKeyframe> selected = capped(scored, effective);
        if (selected.isEmpty()) {
            return keyframes.stream()
                .min(Comparator.comparingLong(HighValueKeyframeSelector::safeTimestamp))
                .map(List::of)
                .orElseGet(List::of);
        }
        return selected.stream()
            .sorted(Comparator.comparingLong(HighValueKeyframeSelector::safeTimestamp))
            .toList();
    }

    private static List<VideoKeyframe> capped(List<ScoredKeyframe> scored, VisionAnalysisProperties properties) {
        List<VideoKeyframe> selected = new ArrayList<>();
        Map<Long, Integer> perMinute = new HashMap<>();
        List<String> selectedOcrTexts = new ArrayList<>();
        long minGapMillis = properties.getMinGapSeconds() * 1_000L;
        for (ScoredKeyframe item : scored) {
            VideoKeyframe keyframe = item.keyframe();
            if (selected.stream().anyMatch(existing -> Math.abs(safeTimestamp(existing) - safeTimestamp(keyframe)) < minGapMillis)) {
                continue;
            }
            long minute = Math.max(0L, safeTimestamp(keyframe) / 60_000L);
            int minuteCount = perMinute.getOrDefault(minute, 0);
            if (minuteCount >= properties.getMaxFramesPerMinute()) {
                continue;
            }
            if (isDuplicateOcrOnlyCandidate(item, selectedOcrTexts, properties.getOcrTextChangeThreshold())) {
                continue;
            }
            selected.add(keyframe);
            if (item.hasOcrText()) {
                selectedOcrTexts.add(item.normalizedOcrText());
            }
            perMinute.put(minute, minuteCount + 1);
            if (selected.size() >= properties.getMaxFramesTotal()) {
                break;
            }
        }
        return selected;
    }

    private static ScoredKeyframe score(VideoKeyframe keyframe, String ocrText) {
        int score = 0;
        KeyframeSelectionReason reason = parseReason(keyframe.getSelectReason());
        if (reason == KeyframeSelectionReason.SCENE_CHANGE || reason == KeyframeSelectionReason.CONTENT_CHANGE) {
            score += 60;
        }
        if (ocrText != null && !ocrText.isBlank()) {
            score += 45;
        }
        if (reason == KeyframeSelectionReason.PERIODIC_ANCHOR) {
            score += 10;
        }
        return new ScoredKeyframe(keyframe, score, reason, normalizeOcr(ocrText));
    }

    private static boolean isDuplicateOcrOnlyCandidate(
        ScoredKeyframe candidate,
        List<String> selectedOcrTexts,
        double changeThreshold
    ) {
        if (candidate.reason() == KeyframeSelectionReason.SCENE_CHANGE
            || candidate.reason() == KeyframeSelectionReason.CONTENT_CHANGE
            || !candidate.hasOcrText()
            || selectedOcrTexts.isEmpty()) {
            return false;
        }
        double maxSimilarity = selectedOcrTexts.stream()
            .mapToDouble(existing -> jaccardSimilarity(existing, candidate.normalizedOcrText()))
            .max()
            .orElse(0.0d);
        return (1.0d - maxSimilarity) < changeThreshold;
    }

    private static double jaccardSimilarity(String left, String right) {
        Set<String> leftTokens = tokenSet(left);
        Set<String> rightTokens = tokenSet(right);
        if (leftTokens.isEmpty() || rightTokens.isEmpty()) {
            return 0.0d;
        }
        Set<String> intersection = new HashSet<>(leftTokens);
        intersection.retainAll(rightTokens);
        Set<String> union = new HashSet<>(leftTokens);
        union.addAll(rightTokens);
        return intersection.size() / (double) union.size();
    }

    private static Set<String> tokenSet(String text) {
        String normalized = normalizeOcr(text);
        if (normalized.isBlank()) {
            return Set.of();
        }
        Set<String> tokens = new HashSet<>();
        for (String token : normalized.split("\\s+")) {
            if (!token.isBlank()) {
                tokens.add(token);
            }
        }
        return tokens;
    }

    private static String normalizeOcr(String text) {
        return text == null ? "" : text.strip().toLowerCase(java.util.Locale.ROOT).replaceAll("\\s+", " ");
    }

    private static KeyframeSelectionReason parseReason(String value) {
        try {
            return KeyframeSelectionReason.valueOf(value);
        } catch (RuntimeException ex) {
            return null;
        }
    }

    private static Map<Long, String> ocrTextByKeyframeId(Collection<VideoKeyframeOcr> rows) {
        if (rows == null || rows.isEmpty()) {
            return Map.of();
        }
        Map<Long, String> result = new HashMap<>();
        for (VideoKeyframeOcr row : rows) {
            if (row == null || row.getKeyframeId() == null || !OcrStatus.SUCCEEDED.name().equals(row.getStatus())) {
                continue;
            }
            result.put(row.getKeyframeId(), row.getOcrText() == null ? "" : row.getOcrText().strip());
        }
        return result;
    }

    private static long safeTimestamp(VideoKeyframe keyframe) {
        return keyframe.getTimestampMillis() == null ? 0L : keyframe.getTimestampMillis();
    }

    private record ScoredKeyframe(
        VideoKeyframe keyframe,
        int score,
        KeyframeSelectionReason reason,
        String normalizedOcrText
    ) {

        private boolean hasOcrText() {
            return normalizedOcrText != null && !normalizedOcrText.isBlank();
        }
    }
}
