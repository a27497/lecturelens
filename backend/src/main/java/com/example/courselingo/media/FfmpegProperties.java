package com.example.courselingo.media;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "courselingo.media.ffmpeg")
public record FfmpegProperties(
    String executable,
    String audioFormat,
    int sampleRate,
    int channels,
    long timeoutSeconds
) {

    private static final String SAFE_FORMAT_PATTERN = "[A-Za-z0-9][A-Za-z0-9_-]{0,15}";

    public FfmpegProperties() {
        this("ffmpeg", "wav", 16000, 1, 300);
    }

    public void validate() {
        if (isBlank(executable)
            || isBlank(audioFormat)
            || !audioFormat.matches(SAFE_FORMAT_PATTERN)
            || sampleRate <= 0
            || channels <= 0
            || timeoutSeconds <= 0) {
            throw new BusinessException(ErrorCode.MEDIA_CONFIGURATION_INVALID);
        }
    }

    Duration timeout() {
        return Duration.ofSeconds(timeoutSeconds);
    }

    String normalizedAudioFormat() {
        return audioFormat.toLowerCase();
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }
}
