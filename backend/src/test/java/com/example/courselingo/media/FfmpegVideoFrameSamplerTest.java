package com.example.courselingo.media;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;

class FfmpegVideoFrameSamplerTest {

    @Test
    void analysisSampleKeepsAspectRatioAndNeverUsesLegacy320Width() {
        FfmpegVideoFrameSampler sampler = new FfmpegVideoFrameSampler(
            new FfmpegProperties(),
            (command, timeout) -> FfmpegProcessResult.success("", "")
        );

        List<String> command = sampler.command(
            Path.of("C:/video/course.mp4"),
            15_300L,
            Path.of("C:/workspace/sample.png"),
            1600
        );

        assertThat(command).contains("-ss", "15.300", "-frames:v", "1");
        assertThat(command).contains("scale='min(1600,iw)':-2");
        assertThat(command).doesNotContain("scale=320:-1");
    }
}
