package com.example.courselingo.media;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import javax.sound.sampled.AudioFormat;
import javax.sound.sampled.AudioInputStream;
import javax.sound.sampled.AudioSystem;
import javax.sound.sampled.UnsupportedAudioFileException;
import org.springframework.stereotype.Component;

@Component
public class JavaSoundAudioDurationProbe implements AudioDurationProbe {

    @Override
    public long probeDurationMillis(Path audioFile) {
        if (audioFile == null || !Files.isRegularFile(audioFile)) {
            throw invalidAudio(null);
        }
        try (AudioInputStream input = AudioSystem.getAudioInputStream(audioFile.toFile())) {
            long frameLength = input.getFrameLength();
            AudioFormat format = input.getFormat();
            float frameRate = format == null ? Float.NaN : format.getFrameRate();
            if (frameLength <= 0L || !Float.isFinite(frameRate) || frameRate <= 0.0f) {
                throw invalidAudio(null);
            }
            long durationMillis = Math.round(frameLength * 1000.0d / frameRate);
            if (durationMillis <= 0L) {
                throw invalidAudio(null);
            }
            return durationMillis;
        } catch (UnsupportedAudioFileException | IOException | IllegalArgumentException exception) {
            throw invalidAudio(exception);
        }
    }

    private static BusinessException invalidAudio(Throwable cause) {
        String message = "Extracted audio duration cannot be read";
        return cause == null
            ? new BusinessException(ErrorCode.MEDIA_INPUT_INVALID, message)
            : new BusinessException(ErrorCode.MEDIA_INPUT_INVALID, message, cause);
    }
}
