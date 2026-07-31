package com.example.courselingo.media;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class MovTextEmbeddedSubtitleIntegrationTest {

    @TempDir
    private Path tempDir;

    @Test
    void realFfmpegCreatesListsLoadsAndCompactsEnglishMovTextCues() throws Exception {
        Path srt = tempDir.resolve("captions.srt");
        Path video = tempDir.resolve("with-mov-text.mp4");
        Files.writeString(srt, """
            1
            00:00:00,000 --> 00:00:04,000
            Spring Boot

            2
            00:00:04,000 --> 00:00:09,500
            API Gateway
            """, StandardCharsets.UTF_8);
        ProcessBuilderFfmpegProcessExecutor executor = new ProcessBuilderFfmpegProcessExecutor();
        FfmpegProcessResult created = executor.execute(List.of(
            "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=10",
            "-i", srt.toString(), "-t", "10", "-c:v", "mpeg4", "-c:s", "mov_text",
            "-metadata:s:s:0", "language=eng", video.toString()
        ), Duration.ofSeconds(30));
        assertThat(created.exitCode()).as(created.stderr()).isZero();

        EmbeddedSubtitleTranscriptProperties properties = new EmbeddedSubtitleTranscriptProperties();
        properties.setMinimumCues(2);
        EmbeddedSubtitleTranscriptExtractor extractor = new EmbeddedSubtitleTranscriptExtractor(
            new FfmpegProperties(), executor, properties, new ObjectMapper()
        );

        EmbeddedSubtitleTranscript transcript = extractor.extract(video, "en", 10_000L).orElseThrow();

        assertThat(transcript.streamIndex()).isPositive();
        assertThat(transcript.segments()).extracting(segment -> segment.text())
            .containsExactly("Spring Boot API Gateway");
        assertThat(transcript.segments().getFirst().startMillis()).isZero();
        assertThat(transcript.segments().getLast().endMillis()).isEqualTo(9500L);
    }
}
