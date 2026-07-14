package com.example.courselingo.vision.keyframe;

import java.io.InputStream;

public record VideoKeyframeImage(
    String fileName,
    String contentType,
    long sizeBytes,
    InputStream inputStream
) {
}
