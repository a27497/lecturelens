package com.example.courselingo.media;

import java.nio.file.Path;
import java.time.Duration;
import java.util.List;

public interface VideoSceneScanner {

    List<SceneDetectionPoint> scan(
        Path sourceVideo,
        Path workspaceDirectory,
        int detectionWidth,
        double sceneThreshold,
        Duration timeout
    );
}
