package com.example.courselingo.media;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Comparator;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class FfmpegAudioChunker implements AudioChunker {

    private static final String ASR_CHUNK_LIMIT_MESSAGE =
        "视频语音转写分片数量超过当前上限，请提高 ASR_CHUNK_MAX_CHUNKS 或使用更短视频后重试";

    private final FfmpegProperties properties;
    private final FfmpegProcessExecutor processExecutor;

    public FfmpegAudioChunker(FfmpegProperties properties, FfmpegProcessExecutor processExecutor) {
        this.properties = properties;
        this.processExecutor = processExecutor;
    }

    @Override
    public List<AudioChunk> split(Path audioFile, Path outputDirectory, Duration chunkDuration, int maxChunks) {
        validate(audioFile, outputDirectory, chunkDuration, maxChunks);
        properties.validate();
        Path normalizedInput = audioFile.toAbsolutePath().normalize();
        Path normalizedOutput = outputDirectory.toAbsolutePath().normalize();
        try {
            Files.createDirectories(normalizedOutput);
        } catch (IOException exception) {
            throw new BusinessException(ErrorCode.MEDIA_OUTPUT_INVALID, "ASR chunk workspace is not available", exception);
        }

        Path pattern = normalizedOutput.resolve("chunk-%03d." + properties.normalizedAudioFormat());
        List<String> command = List.of(
            properties.executable(),
            "-y",
            "-i",
            normalizedInput.toString(),
            "-vn",
            "-f",
            "segment",
            "-segment_time",
            String.valueOf(chunkDuration.toSeconds()),
            "-reset_timestamps",
            "1",
            "-ar",
            String.valueOf(properties.sampleRate()),
            "-ac",
            String.valueOf(properties.channels()),
            pattern.toString()
        );
        FfmpegProcessResult result = execute(command);
        if (result.timedOut()) {
            throw new BusinessException(ErrorCode.MEDIA_FFMPEG_TIMEOUT, "FFmpeg ASR chunking timed out");
        }
        if (result.exitCode() != 0) {
            throw new BusinessException(ErrorCode.MEDIA_FFMPEG_FAILED, "FFmpeg ASR chunking failed");
        }
        return listChunks(normalizedOutput, chunkDuration, maxChunks);
    }

    private FfmpegProcessResult execute(List<String> command) {
        try {
            return processExecutor.execute(command, properties.timeout());
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new BusinessException(ErrorCode.MEDIA_FFMPEG_FAILED, "FFmpeg ASR chunking was interrupted", exception);
        } catch (IOException exception) {
            throw new BusinessException(ErrorCode.MEDIA_FFMPEG_FAILED, "FFmpeg ASR chunking could not start", exception);
        }
    }

    private static List<AudioChunk> listChunks(Path outputDirectory, Duration chunkDuration, int maxChunks) {
        try (var paths = Files.list(outputDirectory)) {
            List<Path> files = paths
                .filter(Files::isRegularFile)
                .filter(path -> path.getFileName().toString().startsWith("chunk-"))
                .sorted(Comparator.comparing(path -> path.getFileName().toString()))
                .toList();
            if (files.isEmpty()) {
                throw new BusinessException(ErrorCode.MEDIA_FFMPEG_FAILED, "FFmpeg ASR chunking produced no chunks");
            }
            if (files.size() > maxChunks) {
                throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, ASR_CHUNK_LIMIT_MESSAGE);
            }
            long chunkMillis = chunkDuration.toMillis();
            return java.util.stream.IntStream.range(0, files.size())
                .mapToObj(index -> new AudioChunk(index, index * chunkMillis, files.get(index)))
                .toList();
        } catch (IOException exception) {
            throw new BusinessException(ErrorCode.MEDIA_OUTPUT_INVALID, "ASR chunk workspace cannot be read", exception);
        }
    }

    private static void validate(Path audioFile, Path outputDirectory, Duration chunkDuration, int maxChunks) {
        if (audioFile == null || !Files.isRegularFile(audioFile)) {
            throw new BusinessException(ErrorCode.MEDIA_INPUT_INVALID);
        }
        if (outputDirectory == null) {
            throw new BusinessException(ErrorCode.MEDIA_OUTPUT_INVALID);
        }
        if (chunkDuration == null || chunkDuration.isZero() || chunkDuration.isNegative()) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, "ASR chunk duration must be positive");
        }
        if (maxChunks <= 0) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, "ASR max chunk count must be positive");
        }
    }
}
