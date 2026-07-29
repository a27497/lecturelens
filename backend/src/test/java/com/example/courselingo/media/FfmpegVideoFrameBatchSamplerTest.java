package com.example.courselingo.media;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.courselingo.common.exception.BusinessException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class FfmpegVideoFrameBatchSamplerTest {

    @TempDir
    private Path tempDir;

    @Test
    void emptyBatchDoesNotLaunchFfmpeg() throws Exception {
        Path source = Files.writeString(tempDir.resolve("course.mp4"), "video");
        AtomicInteger executions = new AtomicInteger();
        FfmpegVideoFrameBatchSampler sampler = new FfmpegVideoFrameBatchSampler(
            new FfmpegProperties(),
            (command, timeout) -> {
                executions.incrementAndGet();
                return FfmpegProcessResult.success("", "");
            }
        );

        VideoFrameBatchResult result = sampler.sample(source, List.of(), 960, Duration.ofSeconds(2));

        assertThat(result.requestedCount()).isZero();
        assertThat(result.ffmpegProcessCount()).isZero();
        assertThat(executions.get()).isZero();
    }

    @Test
    void hardBatchLimitIsRejectedBeforeLaunchingFfmpeg() throws Exception {
        Path source = Files.writeString(tempDir.resolve("course.mp4"), "video");
        AtomicInteger executions = new AtomicInteger();
        FfmpegVideoFrameBatchSampler sampler = new FfmpegVideoFrameBatchSampler(
            new FfmpegProperties(),
            (command, timeout) -> {
                executions.incrementAndGet();
                return FfmpegProcessResult.success("", "");
            }
        );
        List<VideoFrameSampleRequest> requests = new ArrayList<>();
        for (int index = 0; index <= FfmpegVideoFrameBatchSampler.HARD_MAX_BATCH_SIZE; index++) {
            requests.add(new VideoFrameSampleRequest(index, tempDir.resolve("frames/" + index + ".png")));
        }

        assertThatThrownBy(() -> sampler.sample(source, requests, 960, Duration.ofSeconds(2)))
            .isInstanceOf(BusinessException.class)
            .hasMessageContaining("too large");
        assertThat(executions.get()).isZero();
    }

    @Test
    void staleOutputIsDeletedBeforeAFailedSampleAttempt() throws Exception {
        Path source = Files.writeString(tempDir.resolve("course.mp4"), "video");
        Path output = Files.writeString(tempDir.resolve("stale.png"), "stale");
        FfmpegVideoFrameBatchSampler sampler = new FfmpegVideoFrameBatchSampler(
            new FfmpegProperties(),
            (command, timeout) -> new FfmpegProcessResult(1, "", "failed", false)
        );

        VideoFrameBatchResult result = sampler.sample(
            source,
            List.of(new VideoFrameSampleRequest(1_000L, output)),
            960,
            Duration.ofSeconds(2)
        );

        assertThat(result.succeededCount()).isZero();
        assertThat(result.failedCount()).isOne();
        assertThat(output).doesNotExist();
    }

    @Test
    void oneCommandCarriesAllExactMillisecondRequests() {
        FfmpegVideoFrameBatchSampler sampler = new FfmpegVideoFrameBatchSampler(
            new FfmpegProperties(),
            (command, timeout) -> FfmpegProcessResult.success("", "")
        );
        Path source = Path.of("course.mp4");
        List<VideoFrameSampleRequest> requests = List.of(
            new VideoFrameSampleRequest(1_234L, Path.of("work/a.png")),
            new VideoFrameSampleRequest(65_009L, Path.of("work/b.png"))
        );

        List<String> command = sampler.command(source, requests, 1600);

        assertThat(command).containsSubsequence("-ss", "1.234", "-i", source.toString());
        assertThat(command).containsSubsequence("-ss", "65.009", "-i", source.toString());
        assertThat(command.stream().filter("-map"::equals)).hasSize(2);
        assertThat(command).contains("0:v:0", "1:v:0", "scale='min(1600,iw)':-2");
    }

    @Test
    void nonZeroExitStillReturnsSuccessfulMembersOfPartialBatch() throws Exception {
        Path source = Files.writeString(tempDir.resolve("course.mp4"), "video");
        Path first = tempDir.resolve("frames/first.png");
        Path second = tempDir.resolve("frames/second.png");
        FfmpegVideoFrameBatchSampler sampler = new FfmpegVideoFrameBatchSampler(
            new FfmpegProperties(),
            (command, timeout) -> {
                Files.createDirectories(first.getParent());
                Files.writeString(first, "frame");
                return new FfmpegProcessResult(1, "", "second output failed", false);
            }
        );

        VideoFrameBatchResult result = sampler.sample(source, List.of(
            new VideoFrameSampleRequest(100L, first),
            new VideoFrameSampleRequest(200L, second)
        ), 960, Duration.ofSeconds(2));

        assertThat(result.ffmpegProcessCount()).isOne();
        assertThat(result.requestedCount()).isEqualTo(2);
        assertThat(result.succeededCount()).isOne();
        assertThat(result.failedCount()).isOne();
        assertThat(result.samples().getFirst().timestampMillis()).isEqualTo(100L);
    }

    @Test
    void timeoutDeletesPartialOutputs() throws Exception {
        Path source = Files.writeString(tempDir.resolve("course.mp4"), "video");
        Path output = tempDir.resolve("frames/partial.png");
        FfmpegVideoFrameBatchSampler sampler = new FfmpegVideoFrameBatchSampler(
            new FfmpegProperties(),
            (command, timeout) -> {
                Files.createDirectories(output.getParent());
                Files.writeString(output, "partial");
                return new FfmpegProcessResult(-1, "", "timeout", true);
            }
        );

        assertThatThrownBy(() -> sampler.sample(
            source,
            List.of(new VideoFrameSampleRequest(100L, output)),
            960,
            Duration.ofMillis(1)
        )).isInstanceOf(BusinessException.class).hasMessageContaining("timed out");
        assertThat(output).doesNotExist();
    }
}
