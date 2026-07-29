package com.example.courselingo.media;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.logging.SafeLogSanitizer;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import org.springframework.stereotype.Service;

@Service
public class FfprobeVideoMetadataProbe implements VideoMetadataProbe {

    private final FfmpegProperties properties;
    private final FfmpegProcessExecutor processExecutor;

    FfprobeVideoMetadataProbe(FfmpegProperties properties, FfmpegProcessExecutor processExecutor) {
        this.properties = properties;
        this.processExecutor = processExecutor;
    }

    @Override
    public VideoMetadata probe(Path sourceVideo, Duration timeout) {
        Path source = normalizedSource(sourceVideo);
        try {
            FfmpegProcessResult result = processExecutor.execute(command(source), effectiveTimeout(timeout));
            if (result.timedOut()) {
                throw new BusinessException(ErrorCode.MEDIA_FFMPEG_TIMEOUT, "FFprobe metadata probe timed out");
            }
            if (result.exitCode() != 0) {
                throw new BusinessException(
                    ErrorCode.MEDIA_FFMPEG_FAILED,
                    "FFprobe metadata probe failed. " + SafeLogSanitizer.sanitizeAndLimit(result.stderr())
                );
            }
            return parse(result.stdout());
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new BusinessException(ErrorCode.MEDIA_FFMPEG_FAILED, "FFprobe metadata probe was interrupted", exception);
        } catch (IOException exception) {
            throw new BusinessException(ErrorCode.MEDIA_FFMPEG_FAILED, "FFprobe metadata probe could not start", exception);
        }
    }

    static VideoMetadata parse(String output) {
        Map<String, String> values = new LinkedHashMap<>();
        if (output != null) {
            for (String line : output.split("\\R")) {
                int separator = line.indexOf('=');
                if (separator <= 0) {
                    continue;
                }
                String key = line.substring(0, separator).strip().toLowerCase(Locale.ROOT);
                String value = line.substring(separator + 1).strip();
                values.putIfAbsent(key, value);
            }
        }
        int width = integer(values.get("width"));
        int height = integer(values.get("height"));
        long durationMillis = Math.round(decimal(values.get("duration")) * 1000.0d);
        double fps = fraction(values.get("avg_frame_rate"));
        String codec = values.getOrDefault("codec_name", "");
        int rotation = integer(firstNonBlank(values.get("rotation"), values.get("tag:rotate")));
        return new VideoMetadata(durationMillis, width, height, fps, codec, width > 0 && height > 0, rotation);
    }

    private List<String> command(Path source) {
        return List.of(
            properties.ffprobeExecutable(),
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "format=duration:stream=width,height,avg_frame_rate,codec_name:stream_tags=rotate:stream_side_data=rotation",
            "-of", "default=noprint_wrappers=1:nokey=0",
            source.toString()
        );
    }

    private Duration effectiveTimeout(Duration timeout) {
        return timeout == null || timeout.isZero() || timeout.isNegative()
            ? Duration.ofSeconds(Math.min(60L, properties.timeoutSeconds()))
            : timeout;
    }

    private static Path normalizedSource(Path sourceVideo) {
        if (sourceVideo == null) {
            throw new BusinessException(ErrorCode.MEDIA_INPUT_INVALID);
        }
        Path source = sourceVideo.toAbsolutePath().normalize();
        if (!Files.isRegularFile(source)) {
            throw new BusinessException(ErrorCode.MEDIA_INPUT_INVALID);
        }
        return source;
    }

    private static int integer(String value) {
        try {
            return value == null ? 0 : (int) Math.round(Double.parseDouble(value));
        } catch (NumberFormatException ignored) {
            return 0;
        }
    }

    private static double decimal(String value) {
        try {
            return value == null ? 0.0d : Math.max(0.0d, Double.parseDouble(value));
        } catch (NumberFormatException ignored) {
            return 0.0d;
        }
    }

    private static double fraction(String value) {
        if (value == null || value.isBlank()) {
            return 0.0d;
        }
        String[] parts = value.split("/", -1);
        if (parts.length == 2) {
            double denominator = decimal(parts[1]);
            return denominator <= 0.0d ? 0.0d : decimal(parts[0]) / denominator;
        }
        return decimal(value);
    }

    private static String firstNonBlank(String first, String second) {
        return first == null || first.isBlank() ? second : first;
    }
}
