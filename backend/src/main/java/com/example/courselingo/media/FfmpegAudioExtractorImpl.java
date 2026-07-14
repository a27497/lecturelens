package com.example.courselingo.media;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.regex.Pattern;
import org.springframework.stereotype.Service;

@Service
public class FfmpegAudioExtractorImpl implements FfmpegAudioExtractor {

    private static final int DIAGNOSTIC_LIMIT = 512;
    private static final Pattern WINDOWS_PATH = Pattern.compile("[A-Za-z]:\\\\[^\\s]+");
    private static final Pattern UNIX_SENSITIVE_PATH = Pattern.compile("(/Users|/home)/[^\\s]+");
    private static final Pattern SENSITIVE_KEY_VALUE = Pattern.compile(
        "(?i)\\b(?:token|secret|api[_-]?key|api\\s+key)\\b\\s*[:=]\\s*\\S+"
    );
    private static final Pattern SENSITIVE_WORD = Pattern.compile("(?i)\\b(?:token|secret|api[_-]?key|api\\s+key)\\b");

    private final FfmpegProperties properties;
    private final FfmpegProcessExecutor processExecutor;

    public FfmpegAudioExtractorImpl(FfmpegProperties properties, FfmpegProcessExecutor processExecutor) {
        this.properties = properties;
        this.processExecutor = processExecutor;
    }

    @Override
    public AudioExtractionResult extract(AudioExtractionRequest request) {
        properties.validate();
        Path inputVideo = validateInputVideo(request);
        Path outputDirectory = ensureOutputDirectory(request);
        Path outputFile = resolveOutputFile(inputVideo, outputDirectory, request.outputFileName());
        List<String> command = buildCommand(inputVideo, outputFile);

        FfmpegProcessResult result = execute(command);
        if (result.timedOut()) {
            throw new BusinessException(
                ErrorCode.MEDIA_FFMPEG_TIMEOUT,
                "FFmpeg audio extraction timed out. " + safeDiagnostics(result)
            );
        }
        if (result.exitCode() != 0) {
            throw new BusinessException(
                ErrorCode.MEDIA_FFMPEG_FAILED,
                "FFmpeg audio extraction failed. " + safeDiagnostics(result)
            );
        }
        return new AudioExtractionResult(
            outputFile,
            properties.normalizedAudioFormat(),
            properties.sampleRate(),
            properties.channels()
        );
    }

    private Path validateInputVideo(AudioExtractionRequest request) {
        if (request == null || request.inputVideo() == null) {
            throw new BusinessException(ErrorCode.MEDIA_INPUT_INVALID);
        }
        Path inputVideo = request.inputVideo().toAbsolutePath().normalize();
        if (!Files.exists(inputVideo) || !Files.isRegularFile(inputVideo)) {
            throw new BusinessException(ErrorCode.MEDIA_INPUT_INVALID);
        }
        return inputVideo;
    }

    private Path ensureOutputDirectory(AudioExtractionRequest request) {
        if (request == null || request.outputDirectory() == null) {
            throw new BusinessException(ErrorCode.MEDIA_OUTPUT_INVALID);
        }
        Path outputDirectory = request.outputDirectory().toAbsolutePath().normalize();
        try {
            Files.createDirectories(outputDirectory);
        } catch (IOException ex) {
            throw new BusinessException(ErrorCode.MEDIA_OUTPUT_INVALID, "Audio output directory is invalid", ex);
        }
        if (!Files.isDirectory(outputDirectory)) {
            throw new BusinessException(ErrorCode.MEDIA_OUTPUT_INVALID);
        }
        return outputDirectory;
    }

    private Path resolveOutputFile(Path inputVideo, Path outputDirectory, String requestedFileName) {
        String fileName = requestedFileName;
        if (fileName == null || fileName.isBlank()) {
            fileName = defaultOutputFileName(inputVideo);
        }
        Path requestedPath = Path.of(fileName);
        if (requestedPath.isAbsolute()
            || requestedPath.getNameCount() != 1
            || fileName.contains("/")
            || fileName.contains("\\")) {
            throw new BusinessException(ErrorCode.MEDIA_OUTPUT_INVALID);
        }
        Path outputFile = outputDirectory.resolve(fileName).toAbsolutePath().normalize();
        if (!outputFile.startsWith(outputDirectory)) {
            throw new BusinessException(ErrorCode.MEDIA_OUTPUT_INVALID);
        }
        return outputFile;
    }

    private String defaultOutputFileName(Path inputVideo) {
        String fileName = inputVideo.getFileName().toString();
        int lastDot = fileName.lastIndexOf('.');
        String baseName = lastDot > 0 ? fileName.substring(0, lastDot) : fileName;
        return baseName + "." + properties.normalizedAudioFormat();
    }

    private List<String> buildCommand(Path inputVideo, Path outputFile) {
        return List.of(
            properties.executable(),
            "-y",
            "-i",
            inputVideo.toString(),
            "-vn",
            "-ar",
            String.valueOf(properties.sampleRate()),
            "-ac",
            String.valueOf(properties.channels()),
            "-f",
            properties.normalizedAudioFormat(),
            outputFile.toString()
        );
    }

    private FfmpegProcessResult execute(List<String> command) {
        try {
            return processExecutor.execute(command, properties.timeout());
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new BusinessException(ErrorCode.MEDIA_FFMPEG_FAILED, "FFmpeg audio extraction was interrupted", ex);
        } catch (IOException ex) {
            throw new BusinessException(ErrorCode.MEDIA_FFMPEG_FAILED, "FFmpeg audio extraction could not start", ex);
        }
    }

    private String safeDiagnostics(FfmpegProcessResult result) {
        String diagnostics = result.stderr();
        if (diagnostics == null || diagnostics.isBlank()) {
            diagnostics = result.stdout();
        }
        if (diagnostics == null || diagnostics.isBlank()) {
            return "";
        }
        String sanitized = diagnostics.replace('\r', ' ').replace('\n', ' ');
        sanitized = SENSITIVE_KEY_VALUE.matcher(sanitized).replaceAll("[redacted]");
        sanitized = SENSITIVE_WORD.matcher(sanitized).replaceAll("[redacted]");
        sanitized = WINDOWS_PATH.matcher(sanitized).replaceAll("[local-path]");
        sanitized = UNIX_SENSITIVE_PATH.matcher(sanitized).replaceAll("[local-path]");
        sanitized = sanitized.trim();
        if (sanitized.length() > DIAGNOSTIC_LIMIT) {
            return sanitized.substring(0, DIAGNOSTIC_LIMIT).trim() + "...";
        }
        return sanitized;
    }
}
