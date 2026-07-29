package com.example.courselingo.vision.adaptive;

/** A timestamp proposal with an auditable origin and score. */
public record SceneCandidate(double timestampSeconds, Source source, String reason, double score) {

    public enum Source {
        START,
        END,
        SCENE_CHANGE,
        CONTENT_CHANGE,
        PERIODIC_ANCHOR,
        WINDOW_COVERAGE
    }

    public SceneCandidate {
        if (!Double.isFinite(timestampSeconds) || timestampSeconds < 0.0) {
            throw new IllegalArgumentException("timestampSeconds must be finite and non-negative");
        }
        source = source == null ? Source.SCENE_CHANGE : source;
        reason = reason == null || reason.isBlank() ? source.name().toLowerCase(LocaleHolder.ROOT) : reason.trim();
        score = Double.isFinite(score) ? Math.max(0.0, Math.min(1.0, score)) : 0.0;
    }

    public static SceneCandidate sceneChange(double timestampSeconds, double score) {
        return new SceneCandidate(timestampSeconds, Source.SCENE_CHANGE, "scene-change", score);
    }

    public static SceneCandidate contentChange(double timestampSeconds, double score) {
        return new SceneCandidate(timestampSeconds, Source.CONTENT_CHANGE, "content-change", score);
    }

    private static final class LocaleHolder {
        private static final java.util.Locale ROOT = java.util.Locale.ROOT;
    }
}
