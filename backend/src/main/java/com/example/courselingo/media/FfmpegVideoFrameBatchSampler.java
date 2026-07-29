package com.example.courselingo.media;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import org.springframework.stereotype.Service;

/** Uses one FFmpeg process for a bounded group of independent exact timestamp seeks. */
@Service
public class FfmpegVideoFrameBatchSampler implements VideoFrameBatchSampler {

    static final int HARD_MAX_BATCH_SIZE = 64;

    private final FfmpegProperties properties;
    private final FfmpegProcessExecutor processExecutor;

    FfmpegVideoFrameBatchSampler(FfmpegProperties properties, FfmpegProcessExecutor processExecutor) {
        this.properties = properties;
        this.processExecutor = processExecutor;
    }

    @Override
    public VideoFrameBatchResult sample(
        Path sourceVideo,
        List<VideoFrameSampleRequest> requests,
        int maxWidth,
        Duration timeout
    ) {
        Path source = requireSource(sourceVideo);
        List<VideoFrameSampleRequest> batch = validateRequests(requests);
        if (batch.isEmpty()) {
            return new VideoFrameBatchResult(0, List.of(), 0, 0);
        }
        prepareOutputs(batch);
        Duration effectiveTimeout = timeout == null || timeout.isZero() || timeout.isNegative()
            ? Duration.ofSeconds(45)
            : timeout;
        try {
            FfmpegProcessResult result = processExecutor.execute(command(source, batch, maxWidth), effectiveTimeout);
            if (result.timedOut()) {
                deleteOutputs(batch);
                throw new BusinessException(ErrorCode.MEDIA_FFMPEG_TIMEOUT, "FFmpeg batch frame sampling timed out");
            }
            List<VideoFrameSample> succeeded = existingOutputs(batch);
            return new VideoFrameBatchResult(
                batch.size(),
                succeeded,
                batch.size() - succeeded.size(),
                1
            );
        } catch (InterruptedException exception) {
            deleteOutputs(batch);
            Thread.currentThread().interrupt();
            throw new BusinessException(ErrorCode.MEDIA_FFMPEG_FAILED, "FFmpeg batch frame sampling was interrupted", exception);
        } catch (IOException exception) {
            deleteOutputs(batch);
            throw new BusinessException(ErrorCode.MEDIA_FFMPEG_FAILED, "FFmpeg batch frame sampling could not start", exception);
        }
    }

    List<String> command(Path source, List<VideoFrameSampleRequest> requests, int maxWidth) {
        int width = Math.clamp(maxWidth, 320, 3840);
        List<String> command = new ArrayList<>();
        command.addAll(List.of(properties.executable(), "-y", "-hide_banner", "-nostats", "-v", "warning"));
        for (VideoFrameSampleRequest request : requests) {
            command.addAll(List.of(
                "-ss",
                String.format(Locale.ROOT, "%.3f", request.timestampMillis() / 1000.0d),
                "-i",
                source.toString()
            ));
        }
        for (int index = 0; index < requests.size(); index++) {
            command.addAll(List.of(
                "-map", index + ":v:0",
                "-frames:v", "1",
                "-vf", "scale='min(" + width + ",iw)':-2",
                "-compression_level", "3",
                requests.get(index).outputImage().toAbsolutePath().normalize().toString()
            ));
        }
        return List.copyOf(command);
    }

    private static List<VideoFrameSampleRequest> validateRequests(List<VideoFrameSampleRequest> requests) {
        List<VideoFrameSampleRequest> batch = requests == null ? List.of() : List.copyOf(requests);
        if (batch.size() > HARD_MAX_BATCH_SIZE || batch.stream().anyMatch(java.util.Objects::isNull)) {
            throw new BusinessException(ErrorCode.MEDIA_OUTPUT_INVALID, "Frame batch is invalid or too large");
        }
        return batch;
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

    private static void prepareOutputs(List<VideoFrameSampleRequest> requests) {
        try {
            for (VideoFrameSampleRequest request : requests) {
                Path output = request.outputImage().toAbsolutePath().normalize();
                if (output.getParent() == null) {
                    throw new IOException("Frame output has no parent");
                }
                Files.createDirectories(output.getParent());
                Files.deleteIfExists(output);
            }
        } catch (IOException exception) {
            deleteOutputs(requests);
            throw new BusinessException(ErrorCode.MEDIA_OUTPUT_INVALID, "Frame batch output is unavailable", exception);
        }
    }

    private static List<VideoFrameSample> existingOutputs(List<VideoFrameSampleRequest> requests) {
        return requests.stream()
            .filter(request -> Files.isRegularFile(request.outputImage().toAbsolutePath().normalize()))
            .map(request -> new VideoFrameSample(
                request.timestampMillis(),
                request.outputImage().toAbsolutePath().normalize()
            ))
            .toList();
    }

    private static void deleteOutputs(List<VideoFrameSampleRequest> requests) {
        for (VideoFrameSampleRequest request : requests) {
            if (request == null) {
                continue;
            }
            try {
                Files.deleteIfExists(request.outputImage().toAbsolutePath().normalize());
            } catch (IOException ignored) {
                // The caller-owned task workspace provides the final cleanup boundary.
            }
        }
    }
}
