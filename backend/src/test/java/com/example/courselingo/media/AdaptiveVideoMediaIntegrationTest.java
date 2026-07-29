package com.example.courselingo.media;

import static org.assertj.core.api.Assertions.assertThat;

import java.awt.image.BufferedImage;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeUnit;
import javax.imageio.ImageIO;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class AdaptiveVideoMediaIntegrationTest {

    @TempDir
    private Path tempDir;

    @Test
    void probesScansAndSamplesSyntheticVideoWithRealFfmpeg() throws Exception {
        Assumptions.assumeTrue(commandAvailable("ffmpeg"), "FFmpeg is not installed");
        Assumptions.assumeTrue(commandAvailable("ffprobe"), "FFprobe is not installed");
        Path video = tempDir.resolve("two-scenes.mp4");
        Process create = new ProcessBuilder(List.of(
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=red:s=640x360:r=12:d=2",
            "-f", "lavfi", "-i", "color=c=blue:s=640x360:r=12:d=2",
            "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0,format=yuv420p",
            "-c:v", "mpeg4", video.toString()
        )).redirectErrorStream(true).start();
        assertThat(create.waitFor(30, TimeUnit.SECONDS)).isTrue();
        assertThat(create.exitValue()).isZero();
        assertThat(video).isNotEmptyFile();

        FfmpegProperties properties = new FfmpegProperties();
        ProcessBuilderFfmpegProcessExecutor executor = new ProcessBuilderFfmpegProcessExecutor();
        VideoMetadata metadata = new FfprobeVideoMetadataProbe(properties, executor)
            .probe(video, Duration.ofSeconds(20));
        Path scanWorkspace = tempDir.resolve("scan");
        List<SceneDetectionPoint> scenes = new FfmpegVideoSceneScanner(properties, executor)
            .scan(video, scanWorkspace, 480, 0.20d, Duration.ofSeconds(30));
        Path frame = new FfmpegVideoFrameSampler(properties, executor)
            .sample(video, 2_500L, tempDir.resolve("sample.png"), 480, Duration.ofSeconds(20));
        BufferedImage image = ImageIO.read(frame.toFile());

        assertThat(metadata.hasVideoStream()).isTrue();
        assertThat(metadata.durationMillis()).isBetween(3_900L, 4_100L);
        assertThat(metadata.width()).isEqualTo(640);
        assertThat(metadata.height()).isEqualTo(360);
        assertThat(metadata.framesPerSecond()).isBetween(11.5d, 12.5d);
        assertThat(scenes).anyMatch(point -> point.timestampMillis() >= 1_800L && point.timestampMillis() <= 2_200L);
        assertThat(image).isNotNull();
        assertThat(image.getWidth()).isEqualTo(480);
        assertThat(Files.exists(scanWorkspace.resolve("scene-metadata.log"))).isFalse();
    }

    @Test
    void honorsRotationMetadataAndDoesNotUpscalePortraitDisplayWidth() throws Exception {
        Assumptions.assumeTrue(commandAvailable("ffmpeg"), "FFmpeg is not installed");
        Assumptions.assumeTrue(commandAvailable("ffprobe"), "FFprobe is not installed");
        Path base = tempDir.resolve("landscape.mp4");
        Path rotated = tempDir.resolve("rotated.mp4");
        Process create = new ProcessBuilder(List.of(
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=s=640x360:r=12:d=1",
            "-c:v", "mpeg4", base.toString()
        )).redirectErrorStream(true).start();
        assertThat(create.waitFor(30, TimeUnit.SECONDS)).isTrue();
        assertThat(create.exitValue()).isZero();
        Process rotate = new ProcessBuilder(List.of(
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-display_rotation:v:0", "90", "-i", base.toString(), "-c", "copy", rotated.toString()
        )).redirectErrorStream(true).start();
        assertThat(rotate.waitFor(30, TimeUnit.SECONDS)).isTrue();
        assertThat(rotate.exitValue()).isZero();

        FfmpegProperties properties = new FfmpegProperties();
        ProcessBuilderFfmpegProcessExecutor executor = new ProcessBuilderFfmpegProcessExecutor();
        VideoMetadata metadata = new FfprobeVideoMetadataProbe(properties, executor)
            .probe(rotated, Duration.ofSeconds(20));
        Path frame = new FfmpegVideoFrameSampler(properties, executor)
            .sample(rotated, 250L, tempDir.resolve("rotated.png"), 480, Duration.ofSeconds(20));
        BufferedImage image = ImageIO.read(frame.toFile());

        assertThat(metadata.rotationDegrees()).isIn(90, 270);
        assertThat(metadata.displayWidth()).isEqualTo(360);
        assertThat(metadata.displayHeight()).isEqualTo(640);
        assertThat(image.getWidth()).isEqualTo(360);
        assertThat(image.getHeight()).isEqualTo(640);
    }

    private static boolean commandAvailable(String command) {
        try {
            Process process = new ProcessBuilder(command, "-version").redirectErrorStream(true).start();
            return process.waitFor(10, TimeUnit.SECONDS) && process.exitValue() == 0;
        } catch (Exception ignored) {
            return false;
        }
    }
}
