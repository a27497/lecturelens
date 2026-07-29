package com.example.courselingo.media;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.logging.SafeLogSanitizer;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.stereotype.Service;

@Service
public class FfmpegVideoSceneScanner implements VideoSceneScanner {

    private static final Pattern FRAME_LINE = Pattern.compile("pts_time:([0-9]+(?:\\.[0-9]+)?)");
    private static final Pattern SCORE_LINE = Pattern.compile("lavfi\\.scene_score=([0-9]+(?:\\.[0-9]+)?)");

    private final FfmpegProperties properties;
    private final FfmpegProcessExecutor processExecutor;

    FfmpegVideoSceneScanner(FfmpegProperties properties, FfmpegProcessExecutor processExecutor) {
        this.properties = properties;
        this.processExecutor = processExecutor;
    }

    @Override
    public List<SceneDetectionPoint> scan(
        Path sourceVideo,
        Path workspaceDirectory,
        int detectionWidth,
        double sceneThreshold,
        Duration timeout
    ) {
        Path source = requireSource(sourceVideo);
        Path workspace = requireWorkspace(workspaceDirectory);
        Path metadataLog = workspace.resolve("scene-metadata.log").toAbsolutePath().normalize();
        if (!metadataLog.startsWith(workspace)) {
            throw new BusinessException(ErrorCode.MEDIA_OUTPUT_INVALID);
        }
        try {
            Files.deleteIfExists(metadataLog);
            FfmpegProcessResult result = processExecutor.execute(
                command(source, metadataLog, detectionWidth, sceneThreshold),
                effectiveTimeout(timeout)
            );
            if (result.timedOut()) {
                throw new BusinessException(ErrorCode.MEDIA_FFMPEG_TIMEOUT, "FFmpeg scene scan timed out");
            }
            if (result.exitCode() != 0) {
                throw new BusinessException(
                    ErrorCode.MEDIA_FFMPEG_FAILED,
                    "FFmpeg scene scan failed. " + SafeLogSanitizer.sanitizeAndLimit(result.stderr())
                );
            }
            return parseMetadata(Files.exists(metadataLog) ? Files.readString(metadataLog, StandardCharsets.UTF_8) : "");
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new BusinessException(ErrorCode.MEDIA_FFMPEG_FAILED, "FFmpeg scene scan was interrupted", exception);
        } catch (IOException exception) {
            throw new BusinessException(ErrorCode.MEDIA_FFMPEG_FAILED, "FFmpeg scene scan failed", exception);
        } finally {
            try {
                Files.deleteIfExists(metadataLog);
            } catch (IOException ignored) {
                // The caller owns the task workspace and performs a second guarded cleanup pass.
            }
        }
    }

    static List<SceneDetectionPoint> parseMetadata(String content) {
        if (content == null || content.isBlank()) {
            return List.of();
        }
        List<SceneDetectionPoint> points = new ArrayList<>();
        Long timestamp = null;
        for (String line : content.split("\\R")) {
            Matcher frameMatcher = FRAME_LINE.matcher(line);
            if (frameMatcher.find()) {
                timestamp = Math.round(Double.parseDouble(frameMatcher.group(1)) * 1000.0d);
                continue;
            }
            Matcher scoreMatcher = SCORE_LINE.matcher(line);
            if (timestamp != null && scoreMatcher.find()) {
                points.add(new SceneDetectionPoint(timestamp, Double.parseDouble(scoreMatcher.group(1))));
                timestamp = null;
            }
        }
        return List.copyOf(points);
    }

    List<String> command(Path source, Path metadataLog, int detectionWidth, double sceneThreshold) {
        int width = Math.clamp(detectionWidth, 160, 1920);
        double threshold = Math.max(0.001d, Math.min(0.99d, sceneThreshold));
        String filter = "scale=" + width + ":-2,select='gt(scene," + String.format(Locale.ROOT, "%.4f", threshold)
            + ")',metadata=print:file='" + filterPath(metadataLog) + "'";
        return List.of(
            properties.executable(),
            "-hide_banner", "-nostats", "-v", "warning",
            "-i", source.toString(),
            "-map", "0:v:0", "-an", "-sn", "-dn",
            "-vf", filter,
            "-fps_mode", "vfr",
            "-f", "null",
            isWindows() ? "NUL" : "-"
        );
    }

    private Duration effectiveTimeout(Duration timeout) {
        return timeout == null || timeout.isZero() || timeout.isNegative()
            ? Duration.ofSeconds(Math.max(1L, properties.timeoutSeconds()))
            : timeout;
    }

    private static Path requireSource(Path sourceVideo) {
        if (sourceVideo == null) {
            throw new BusinessException(ErrorCode.MEDIA_INPUT_INVALID);
        }
        Path source = sourceVideo.toAbsolutePath().normalize();
        if (!Files.isRegularFile(source)) {
            throw new BusinessException(ErrorCode.MEDIA_INPUT_INVALID);
        }
        return source;
    }

    private static Path requireWorkspace(Path workspaceDirectory) {
        if (workspaceDirectory == null) {
            throw new BusinessException(ErrorCode.MEDIA_OUTPUT_INVALID);
        }
        Path workspace = workspaceDirectory.toAbsolutePath().normalize();
        try {
            Files.createDirectories(workspace);
        } catch (IOException exception) {
            throw new BusinessException(ErrorCode.MEDIA_OUTPUT_INVALID, "Scene scan workspace is unavailable", exception);
        }
        return workspace;
    }

    private static String filterPath(Path path) {
        return path.toAbsolutePath().normalize().toString().replace('\\', '/').replace(":", "\\:");
    }

    private static boolean isWindows() {
        return System.getProperty("os.name", "").toLowerCase(Locale.ROOT).contains("win");
    }
}
