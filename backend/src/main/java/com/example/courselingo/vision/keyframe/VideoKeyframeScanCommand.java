package com.example.courselingo.vision.keyframe;

import java.nio.file.Path;

public record VideoKeyframeScanCommand(
    String taskId,
    Long userId,
    Path sourceVideo,
    Path outputDirectory
) {
}
