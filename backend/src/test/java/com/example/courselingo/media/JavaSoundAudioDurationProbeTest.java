package com.example.courselingo.media;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.io.ByteArrayInputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import javax.sound.sampled.AudioFileFormat;
import javax.sound.sampled.AudioFormat;
import javax.sound.sampled.AudioInputStream;
import javax.sound.sampled.AudioSystem;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class JavaSoundAudioDurationProbeTest {

    @TempDir
    private Path tempDir;

    @Test
    void probesWavDurationFromFrameLengthAndFrameRate() throws Exception {
        Path wav = tempDir.resolve("one-second.wav");
        AudioFormat format = new AudioFormat(16_000.0f, 16, 1, true, false);
        byte[] pcm = new byte[32_000];
        try (AudioInputStream input = new AudioInputStream(
            new ByteArrayInputStream(pcm),
            format,
            16_000L
        )) {
            AudioSystem.write(input, AudioFileFormat.Type.WAVE, wav.toFile());
        }

        assertThat(new JavaSoundAudioDurationProbe().probeDurationMillis(wav)).isEqualTo(1_000L);
    }

    @Test
    void rejectsUnsupportedAudioWithoutExposingPath() throws Exception {
        Path invalid = Files.writeString(tempDir.resolve("invalid.wav"), "not a wav");

        assertThatThrownBy(() -> new JavaSoundAudioDurationProbe().probeDurationMillis(invalid))
            .isInstanceOf(BusinessException.class)
            .satisfies(error -> {
                assertThat(((BusinessException) error).errorCode()).isEqualTo(ErrorCode.MEDIA_INPUT_INVALID);
                assertThat(error.getMessage()).doesNotContain(invalid.toString());
            });
    }

    @Test
    void rejectsWavWithNoAudioFrames() throws Exception {
        Path wav = tempDir.resolve("empty.wav");
        AudioFormat format = new AudioFormat(16_000.0f, 16, 1, true, false);
        try (AudioInputStream input = new AudioInputStream(
            new ByteArrayInputStream(new byte[0]),
            format,
            0L
        )) {
            AudioSystem.write(input, AudioFileFormat.Type.WAVE, wav.toFile());
        }

        assertThatThrownBy(() -> new JavaSoundAudioDurationProbe().probeDurationMillis(wav))
            .isInstanceOf(BusinessException.class)
            .satisfies(error ->
                assertThat(((BusinessException) error).errorCode()).isEqualTo(ErrorCode.MEDIA_INPUT_INVALID)
            );
    }
}
