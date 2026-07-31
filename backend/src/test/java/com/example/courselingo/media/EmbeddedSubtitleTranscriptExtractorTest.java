package com.example.courselingo.media;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.courselingo.ai.asr.TranscribedSegment;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class EmbeddedSubtitleTranscriptExtractorTest {

    @TempDir
    private Path tempDir;

    @Test
    void parsesUtf8BomAndCrLfWebVttCues() {
        List<TranscribedSegment> segments = EmbeddedSubtitleTranscriptExtractor.parseWebVtt(
            "\uFEFFWEBVTT\r\n\r\n00:00:00.000 --> 00:00:02.000\r\nSpring Boot\r\n\r\n"
                + "00:00:02.000 --> 00:00:04.500 align:start\r\nAPI Gateway\r\n",
            "en"
        );

        assertThat(segments).hasSize(2);
        assertThat(segments).extracting(TranscribedSegment::text)
            .containsExactly("Spring Boot", "API Gateway");
        assertThat(segments.get(1).startMillis()).isEqualTo(2000L);
        assertThat(segments.get(1).endMillis()).isEqualTo(4500L);
    }

    @Test
    void selectsMatchingLanguageFromMultipleStreamsAndCleansTemporaryFile() throws Exception {
        Path video = Files.writeString(tempDir.resolve("sample.mp4"), "video");
        RecordingExecutor executor = new RecordingExecutor(false);
        EmbeddedSubtitleTranscriptExtractor extractor = extractor(executor);

        EmbeddedSubtitleTranscript transcript = extractor.extract(video, "en-US", 10_000L).orElseThrow();

        assertThat(transcript.streamIndex()).isEqualTo(3);
        assertThat(transcript.language()).isEqualTo("en-US");
        assertThat(transcript.coverage()).isGreaterThanOrEqualTo(0.8d);
        assertThat(executor.commands.get(1)).contains("-map", "0:3", "-c:s", "webvtt", "-f", "webvtt");
        assertThat(Files.exists(executor.outputPath)).isFalse();
    }

    @Test
    void conversionFailureFallsBackAndStillCleansTemporaryFile() throws Exception {
        Path video = Files.writeString(tempDir.resolve("sample.mp4"), "video");
        RecordingExecutor executor = new RecordingExecutor(true);

        assertThat(extractor(executor).extract(video, "en", 10_000L)).isEmpty();
        assertThat(Files.exists(executor.outputPath)).isFalse();
    }

    @Test
    void compactsLongCueTimelineIntoStableCourseSegments() {
        List<TranscribedSegment> compacted = EmbeddedSubtitleTranscriptExtractor.compactTimeline(
            List.of(
                new TranscribedSegment(0, 1_000L, 2_000L, "Spring Boot"),
                new TranscribedSegment(1, 8_000L, 9_000L, "API Gateway"),
                new TranscribedSegment(2, 61_000L, 62_000L, "Docker Compose"),
                new TranscribedSegment(3, 121_000L, 122_000L, "HTTP request")
            ),
            Duration.ofSeconds(60),
            "en"
        );

        assertThat(compacted).hasSize(3);
        assertThat(compacted).extracting(TranscribedSegment::text)
            .containsExactly("Spring Boot API Gateway", "Docker Compose", "HTTP request");
        assertThat(compacted).extracting(TranscribedSegment::index)
            .containsExactly(0, 1, 2);
    }

    @Test
    void coverageUsesClippedUnionInsteadOfFirstToLastSpan() {
        List<TranscribedSegment> sparse = List.of(
            new TranscribedSegment(0, 0L, 2_000L, "first"),
            new TranscribedSegment(1, 1_000L, 3_000L, "overlap"),
            new TranscribedSegment(2, 9_000L, 12_000L, "last"),
            new TranscribedSegment(3, 15_000L, 16_000L, "outside"),
            new TranscribedSegment(4, 4_000L, 4_000L, "empty")
        );

        assertThat(EmbeddedSubtitleTranscriptExtractor.coverage(sparse, 10_000L)).isEqualTo(0.4d);
        assertThat(EmbeddedSubtitleTranscriptExtractor.clipToMediaTimeline(sparse, 10_000L))
            .extracting(TranscribedSegment::index)
            .containsExactly(0, 1, 2);
    }

    @Test
    void coverageRejectsEmptyOrInvalidMediaTimeline() {
        assertThat(EmbeddedSubtitleTranscriptExtractor.coverage(List.of(), 10_000L)).isZero();
        assertThat(EmbeddedSubtitleTranscriptExtractor.coverage(
            List.of(new TranscribedSegment(0, 0L, 1_000L, "cue")),
            0L
        )).isZero();
    }

    private EmbeddedSubtitleTranscriptExtractor extractor(FfmpegProcessExecutor executor) {
        EmbeddedSubtitleTranscriptProperties properties = new EmbeddedSubtitleTranscriptProperties();
        properties.setMinimumCoverage(0.8d);
        properties.setMinimumCues(2);
        return new EmbeddedSubtitleTranscriptExtractor(
            new FfmpegProperties(), executor, properties, new ObjectMapper()
        );
    }

    private static final class RecordingExecutor implements FfmpegProcessExecutor {
        private final boolean failConversion;
        private final List<List<String>> commands = new ArrayList<>();
        private Path outputPath;

        private RecordingExecutor(boolean failConversion) {
            this.failConversion = failConversion;
        }

        @Override
        public FfmpegProcessResult execute(List<String> command, Duration timeout) throws IOException {
            commands.add(List.copyOf(command));
            if (command.getFirst().contains("ffprobe")) {
                return FfmpegProcessResult.success("""
                    {"streams":[
                      {"index":2,"codec_type":"subtitle","codec_name":"subrip","tags":{"language":"zho"}},
                      {"index":3,"codec_type":"subtitle","codec_name":"mov_text","tags":{"language":"eng"}}
                    ]}
                    """, "");
            }
            outputPath = Path.of(command.getLast());
            if (failConversion) {
                Files.writeString(outputPath, "partial", StandardCharsets.UTF_8);
                return new FfmpegProcessResult(1, "", "conversion failed", false);
            }
            Files.writeString(outputPath, """
                WEBVTT

                00:00:00.000 --> 00:00:04.000
                Spring Boot

                00:00:04.000 --> 00:00:09.000
                API Gateway
                """, StandardCharsets.UTF_8);
            return FfmpegProcessResult.success("", "");
        }
    }
}
