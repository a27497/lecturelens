package com.example.courselingo.media;

public record VideoMetadata(
    long durationMillis,
    int width,
    int height,
    double framesPerSecond,
    String codec,
    boolean hasVideoStream,
    int rotationDegrees
) {

    public VideoMetadata {
        durationMillis = Math.max(0L, durationMillis);
        width = Math.max(0, width);
        height = Math.max(0, height);
        framesPerSecond = Math.max(0.0d, framesPerSecond);
        codec = codec == null ? "" : codec.strip();
        rotationDegrees = normalizeRotation(rotationDegrees);
    }

    private static int normalizeRotation(int value) {
        int normalized = value % 360;
        return normalized < 0 ? normalized + 360 : normalized;
    }

    public int displayWidth() {
        return rotationDegrees == 90 || rotationDegrees == 270 ? height : width;
    }

    public int displayHeight() {
        return rotationDegrees == 90 || rotationDegrees == 270 ? width : height;
    }
}
