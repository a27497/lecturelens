package com.example.courselingo.media;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.logging.SafeLogSanitizer;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.Locale;
import org.springframework.stereotype.Service;

@Service
public class FfmpegVideoFrameSampler implements VideoFrameSampler {

    private final FfmpegProperties properties;
    private final FfmpegProcessExecutor processExecutor;

    FfmpegVideoFrameSampler(FfmpegProperties properties, FfmpegProcessExecutor processExecutor) {
        this.properties = properties;
        this.processExecutor = processExecutor;
    }

    @Override
    public Path sample(Path sourceVideo, long timestampMillis, Path outputImage, int maxWidth, Duration timeout) {
        Path source = requireSource(sourceVideo);
        Path output = requireOutput(outputImage);
        try {
            FfmpegProcessResult result = processExecutor.execute(
                command(source, timestampMillis, output, maxWidth),
                timeout == null || timeout.isZero() || timeout.isNegative() ? Duration.ofSeconds(30) : timeout
            );
            if (result.timedOut()) {
                throw new BusinessException(ErrorCode.MEDIA_FFMPEG_TIMEOUT, "FFmpeg frame sampling timed out");
            }
            if (result.exitCode() != 0 || !Files.isRegularFile(output)) {
                throw new BusinessException(
                    ErrorCode.MEDIA_FFMPEG_FAILED,
                    "FFmpeg frame sampling failed. " + SafeLogSanitizer.sanitizeAndLimit(result.stderr())
                );
            }
            return output;
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new BusinessException(ErrorCode.MEDIA_FFMPEG_FAILED, "FFmpeg frame sampling was interrupted", exception);
        } catch (IOException exception) {
            throw new BusinessException(ErrorCode.MEDIA_FFMPEG_FAILED, "FFmpeg frame sampling could not start", exception);
        }
    }

    List<String> command(Path source, long timestampMillis, Path output, int maxWidth) {
        String timestamp = String.format(Locale.ROOT, "%.3f", Math.max(0L, timestampMillis) / 1000.0d);
        int width = Math.clamp(maxWidth, 320, 3840);
        return List.of(
            properties.executable(), "-y", "-hide_banner", "-nostats", "-v", "warning",
            "-ss", timestamp,
            "-i", source.toString(),
            "-map", "0:v:0", "-frames:v", "1",
            "-vf", "scale='min(" + width + ",iw)':-2",
            "-compression_level", "3",
            output.toString()
        );
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

    private static Path requireOutput(Path outputImage) {
        if (outputImage == null || outputImage.getParent() == null) {
            throw new BusinessException(ErrorCode.MEDIA_OUTPUT_INVALID);
        }
        Path output = outputImage.toAbsolutePath().normalize();
        try {
            Files.createDirectories(output.getParent());
            Files.deleteIfExists(output);
        } catch (IOException exception) {
            throw new BusinessException(ErrorCode.MEDIA_OUTPUT_INVALID, "Frame output is unavailable", exception);
        }
        return output;
    }
}
