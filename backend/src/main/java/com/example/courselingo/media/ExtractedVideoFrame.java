package com.example.courselingo.media;

import java.nio.file.Path;

public record ExtractedVideoFrame(
    int frameIndex,
    long timestampMillis,
    Path imageFile
) {
}
