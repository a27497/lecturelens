package com.example.courselingo.vision.adaptive;

import java.nio.file.Path;

/** Keeps the untouched analysis image and a separate enhanced PNG. */
public record OcrPreprocessingResult(
    Path originalImage,
    Path enhancedImage,
    boolean binarized,
    int width,
    int height
) {
}
