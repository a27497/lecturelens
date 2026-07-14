package com.example.courselingo.vision.keyframe;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;

@Service
public class KeyframeSelectionService {

    public List<SelectedKeyframe> select(List<KeyframeCandidate> candidates, VideoKeyframeProperties properties) {
        if (candidates == null || candidates.isEmpty()) {
            return List.of();
        }
        VideoKeyframeProperties effective = properties == null ? new VideoKeyframeProperties() : properties;
        List<SelectedKeyframe> selected = new ArrayList<>();
        Map<Long, Integer> selectedPerMinute = new HashMap<>();
        long minGapMillis = effective.getMinKeyframeGapSeconds() * 1_000L;
        long periodicAnchorMillis = effective.getPeriodicAnchorSeconds() * 1_000L;
        long lastSelectedAt = Long.MIN_VALUE / 2;
        long lastAnchorAt = Long.MIN_VALUE / 2;

        for (KeyframeCandidate candidate : candidates) {
            if (candidate == null || candidate.imageFile() == null) {
                continue;
            }
            KeyframeSelectionReason reason = reason(candidate, selected.isEmpty(), lastAnchorAt, periodicAnchorMillis,
                effective);
            if (reason == null) {
                continue;
            }
            if (!selected.isEmpty() && candidate.timestampMillis() - lastSelectedAt < minGapMillis) {
                continue;
            }
            long minute = Math.max(0L, candidate.timestampMillis() / 60_000L);
            int minuteCount = selectedPerMinute.getOrDefault(minute, 0);
            if (minuteCount >= effective.getMaxKeyframesPerMinute()) {
                continue;
            }
            selected.add(new SelectedKeyframe(
                candidate.frameIndex(),
                candidate.timestampMillis(),
                candidate.imageFile(),
                candidate.changeScore() == null ? 0.0 : candidate.changeScore().normalizedScore(),
                reason
            ));
            selectedPerMinute.put(minute, minuteCount + 1);
            lastSelectedAt = candidate.timestampMillis();
            if (reason == KeyframeSelectionReason.FIRST_FRAME || reason == KeyframeSelectionReason.PERIODIC_ANCHOR) {
                lastAnchorAt = candidate.timestampMillis();
            }
            if (selected.size() >= effective.getMaxKeyframesTotal()) {
                break;
            }
        }
        return List.copyOf(selected);
    }

    private static KeyframeSelectionReason reason(
        KeyframeCandidate candidate,
        boolean first,
        long lastAnchorAt,
        long periodicAnchorMillis,
        VideoKeyframeProperties properties
    ) {
        if (first) {
            return KeyframeSelectionReason.FIRST_FRAME;
        }
        if (candidate.timestampMillis() - lastAnchorAt >= periodicAnchorMillis) {
            return KeyframeSelectionReason.PERIODIC_ANCHOR;
        }
        FrameChangeScore score = candidate.changeScore() == null ? FrameChangeScore.none() : candidate.changeScore();
        if (score.changedPixelRatio() >= properties.getSceneChangeThreshold()) {
            return KeyframeSelectionReason.SCENE_CHANGE;
        }
        if (score.averagePixelDelta() >= properties.getPixelDiffThreshold()) {
            return KeyframeSelectionReason.CONTENT_CHANGE;
        }
        return null;
    }
}
