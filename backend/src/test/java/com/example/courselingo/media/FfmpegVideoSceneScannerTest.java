package com.example.courselingo.media;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;

class FfmpegVideoSceneScannerTest {

    @Test
    void parsesRealPtsTimeAndSceneScorePairs() {
        List<SceneDetectionPoint> points = FfmpegVideoSceneScanner.parseMetadata("""
            frame:0    pts:15360   pts_time:15.36
            lavfi.scene_score=0.421900
            frame:1    pts:93840   pts_time:93.84
            lavfi.scene_score=0.771200
            """);

        assertThat(points).containsExactly(
            new SceneDetectionPoint(15_360L, 0.4219d),
            new SceneDetectionPoint(93_840L, 0.7712d)
        );
    }

    @Test
    void scanCommandWritesOnlyMetadataAndHasNoFrameLimit() {
        FfmpegVideoSceneScanner scanner = new FfmpegVideoSceneScanner(
            new FfmpegProperties(),
            (command, timeout) -> FfmpegProcessResult.success("", "")
        );

        List<String> command = scanner.command(
            Path.of("C:/video/course.mp4"),
            Path.of("C:/workspace/scene.log"),
            480,
            0.30d
        );

        assertThat(command).contains("-f", "null");
        assertThat(command).noneMatch(value -> value.contains("frames:v") || value.equals("3000"));
        assertThat(String.join(" ", command)).contains("scale=480").contains("scene").contains("metadata=print");
    }

    @Test
    void scanCommandRetainsConfiguredSubtleContentThreshold() {
        FfmpegVideoSceneScanner scanner = new FfmpegVideoSceneScanner(
            new FfmpegProperties(),
            (command, timeout) -> FfmpegProcessResult.success("", "")
        );

        String command = String.join(" ", scanner.command(
            Path.of("C:/video/course.mp4"),
            Path.of("C:/workspace/scene.log"),
            480,
            0.005d
        ));

        assertThat(command).contains("gt(scene,0.0050)");
    }
}
