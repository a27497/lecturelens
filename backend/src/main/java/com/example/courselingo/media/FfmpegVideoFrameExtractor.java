package com.example.courselingo.media;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.logging.SafeLogSanitizer;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Comparator;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class FfmpegVideoFrameExtractor implements VideoFrameExtractor {

    private final FfmpegProperties ffmpegProperties;
    private final FfmpegProcessExecutor processExecutor;

    public FfmpegVideoFrameExtractor(FfmpegProperties ffmpegProperties, FfmpegProcessExecutor processExecutor) {
        this.ffmpegProperties = ffmpegProperties;
        this.processExecutor = processExecutor;
    }

    @Override
    public List<ExtractedVideoFrame> extract(VideoFrameExtractionRequest request) {
        ffmpegProperties.validate();
        Path inputVideo = validateInputVideo(request);
        Path outputDirectory = ensureOutputDirectory(request);
        int intervalSeconds = Math.max(1, request.scanIntervalSeconds());
        int width = Math.max(64, request.thumbnailWidth());
        int maxFrames = Math.max(1, request.maxFrames());
        String outputFormat = normalizeFormat(request.outputFormat());
        Path outputPattern = outputDirectory.resolve("frame-%06d." + outputFormat).toAbsolutePath().normalize();
        if (!outputPattern.startsWith(outputDirectory)) {
            throw new BusinessException(ErrorCode.MEDIA_OUTPUT_INVALID);
        }

        FfmpegProcessResult result = execute(buildCommand(inputVideo, outputPattern, intervalSeconds, width, maxFrames),
            request.timeout());
        if (result.timedOut()) {
            throw new BusinessException(ErrorCode.MEDIA_FFMPEG_TIMEOUT, "FFmpeg frame extraction timed out");
        }
        if (result.exitCode() != 0) {
            throw new BusinessException(
                ErrorCode.MEDIA_FFMPEG_FAILED,
                "FFmpeg frame extraction failed. " + SafeLogSanitizer.sanitizeAndLimit(result.stderr())
            );
        }
        return listFrames(outputDirectory, outputFormat, intervalSeconds);
    }

    private Path validateInputVideo(VideoFrameExtractionRequest request) {
        if (request == null || request.inputVideo() == null) {
            throw new BusinessException(ErrorCode.MEDIA_INPUT_INVALID);
        }
        Path inputVideo = request.inputVideo().toAbsolutePath().normalize();
        if (!Files.exists(inputVideo) || !Files.isRegularFile(inputVideo)) {
            throw new BusinessException(ErrorCode.MEDIA_INPUT_INVALID);
        }
        return inputVideo;
    }

    private Path ensureOutputDirectory(VideoFrameExtractionRequest request) {
        if (request == null || request.outputDirectory() == null) {
            throw new BusinessException(ErrorCode.MEDIA_OUTPUT_INVALID);
        }
        Path outputDirectory = request.outputDirectory().toAbsolutePath().normalize();
        try {
            Files.createDirectories(outputDirectory);
        } catch (IOException ex) {
            throw new BusinessException(ErrorCode.MEDIA_OUTPUT_INVALID, "Keyframe output directory is invalid", ex);
        }
        return outputDirectory;
    }

    private List<String> buildCommand(Path inputVideo, Path outputPattern, int intervalSeconds, int width, int maxFrames) {
        return List.of(
            ffmpegProperties.executable(),
            "-y",
            "-i",
            inputVideo.toString(),
            "-vf",
            "fps=1/" + intervalSeconds + ",scale=" + width + ":-1",
            "-frames:v",
            String.valueOf(maxFrames),
            "-q:v",
            "3",
            outputPattern.toString()
        );
    }

    private FfmpegProcessResult execute(List<String> command, Duration timeout) {
        try {
            return processExecutor.execute(command, timeout == null ? Duration.ofSeconds(600) : timeout);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new BusinessException(ErrorCode.MEDIA_FFMPEG_FAILED, "FFmpeg frame extraction was interrupted", ex);
        } catch (IOException ex) {
            throw new BusinessException(ErrorCode.MEDIA_FFMPEG_FAILED, "FFmpeg frame extraction could not start", ex);
        }
    }

    private List<ExtractedVideoFrame> listFrames(Path outputDirectory, String outputFormat, int intervalSeconds) {
        try (var paths = Files.list(outputDirectory)) {
            List<Path> frames = paths
                .filter(Files::isRegularFile)
                .filter(path -> path.getFileName().toString().endsWith("." + outputFormat))
                .sorted(Comparator.comparing(path -> path.getFileName().toString()))
                .toList();
            return java.util.stream.IntStream.range(0, frames.size())
                .mapToObj(index -> new ExtractedVideoFrame(
                    index,
                    (long) index * intervalSeconds * 1_000L,
                    frames.get(index).toAbsolutePath().normalize()
                ))
                .toList();
        } catch (IOException ex) {
            throw new BusinessException(ErrorCode.MEDIA_OUTPUT_INVALID, "Keyframe output listing failed", ex);
        }
    }

    private static String normalizeFormat(String outputFormat) {
        if (outputFormat == null || outputFormat.isBlank()) {
            return "jpg";
        }
        String normalized = outputFormat.strip().toLowerCase();
        if (!"jpg".equals(normalized) && !"jpeg".equals(normalized)) {
            throw new BusinessException(ErrorCode.MEDIA_CONFIGURATION_INVALID, "Keyframe output format is invalid");
        }
        return "jpg";
    }
}
