package com.example.courselingo.media;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class FfprobeVideoMetadataProbeTest {

    @Test
    void parsesDurationDimensionsFpsCodecAndRotation() {
        VideoMetadata metadata = FfprobeVideoMetadataProbe.parse("""
            codec_name=h264
            width=1920
            height=1080
            avg_frame_rate=30000/1001
            TAG:rotate=90
            duration=10800.125
            """);

        assertThat(metadata.durationMillis()).isEqualTo(10_800_125L);
        assertThat(metadata.width()).isEqualTo(1920);
        assertThat(metadata.height()).isEqualTo(1080);
        assertThat(metadata.framesPerSecond()).isBetween(29.96d, 29.98d);
        assertThat(metadata.codec()).isEqualTo("h264");
        assertThat(metadata.hasVideoStream()).isTrue();
        assertThat(metadata.rotationDegrees()).isEqualTo(90);
        assertThat(metadata.displayWidth()).isEqualTo(1080);
        assertThat(metadata.displayHeight()).isEqualTo(1920);
    }

    @Test
    void missingVideoStreamIsReportedWithoutGuessingDurationFromFrames() {
        VideoMetadata metadata = FfprobeVideoMetadataProbe.parse("duration=42.5");

        assertThat(metadata.durationMillis()).isEqualTo(42_500L);
        assertThat(metadata.hasVideoStream()).isFalse();
        assertThat(metadata.width()).isZero();
        assertThat(metadata.height()).isZero();
    }
}
