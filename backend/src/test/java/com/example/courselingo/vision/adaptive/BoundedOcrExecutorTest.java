package com.example.courselingo.vision.adaptive;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.courselingo.vision.ocr.OcrProvider;
import com.example.courselingo.vision.ocr.OcrResult;
import com.example.courselingo.vision.ocr.OcrStatus;
import com.example.courselingo.vision.ocr.VisionOcrProperties;
import java.awt.Color;
import java.awt.image.BufferedImage;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import javax.imageio.ImageIO;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class BoundedOcrExecutorTest {

    @TempDir
    private Path tempDir;

    @Test
    void emptyInputDoesNotInvokeProvider() {
        VisionOcrProperties properties = properties(2, 2);
        AtomicInteger calls = new AtomicInteger();
        OcrProvider provider = request -> {
            calls.incrementAndGet();
            return succeeded("unexpected");
        };

        BoundedOcrExecutor.Execution<Integer> result = new BoundedOcrExecutor().execute(
            List.of(), provider, properties, Duration.ofSeconds(1)
        );

        assertThat(result.outcomes()).isEmpty();
        assertThat(result.attemptedCount()).isZero();
        assertThat(calls.get()).isZero();
    }

    @Test
    void disabledOcrPreservesTimestampOrderWithoutReadingImages() {
        VisionOcrProperties properties = properties(2, 2);
        properties.setEnabled(false);
        List<BoundedOcrExecutor.Job<Integer>> jobs = List.of(
            new BoundedOcrExecutor.Job<>(2, 2_000L, tempDir.resolve("missing-2.png"), tempDir.resolve("disabled-2")),
            new BoundedOcrExecutor.Job<>(1, 1_000L, tempDir.resolve("missing-1.png"), tempDir.resolve("disabled-1"))
        );

        BoundedOcrExecutor.Execution<Integer> result = new BoundedOcrExecutor().execute(
            jobs, null, properties, Duration.ofSeconds(1)
        );

        assertThat(result.attemptedCount()).isZero();
        assertThat(result.outcomes()).extracting(BoundedOcrExecutor.Outcome::timestampMillis)
            .containsExactly(1_000L, 2_000L);
        assertThat(result.outcomes()).allMatch(outcome -> outcome.ocrResult().status() == OcrStatus.DISABLED);
    }

    @Test
    void boundsConcurrencyAndRestoresDeterministicTimestampOrder() throws Exception {
        Path image = image(tempDir.resolve("source.png"));
        VisionOcrProperties properties = properties(2, 2);
        AtomicInteger active = new AtomicInteger();
        AtomicInteger maximum = new AtomicInteger();
        OcrProvider provider = request -> {
            int current = active.incrementAndGet();
            maximum.accumulateAndGet(current, Math::max);
            try {
                Thread.sleep(25L);
                return succeeded("text");
            } catch (InterruptedException interruption) {
                Thread.currentThread().interrupt();
                return failed("interrupted");
            } finally {
                active.decrementAndGet();
            }
        };
        List<BoundedOcrExecutor.Job<Integer>> jobs = new ArrayList<>();
        for (int index = 7; index >= 0; index--) {
            jobs.add(new BoundedOcrExecutor.Job<>(
                index,
                index * 1_000L,
                image,
                tempDir.resolve("ocr-" + index)
            ));
        }

        BoundedOcrExecutor.Execution<Integer> result = new BoundedOcrExecutor().execute(
            jobs,
            provider,
            properties,
            Duration.ofSeconds(10)
        );

        assertThat(maximum.get()).isEqualTo(2);
        assertThat(result.attemptedCount()).isEqualTo(8);
        assertThat(result.outcomes()).extracting(BoundedOcrExecutor.Outcome::timestampMillis)
            .containsExactly(0L, 1_000L, 2_000L, 3_000L, 4_000L, 5_000L, 6_000L, 7_000L);
        assertThat(Files.list(tempDir).map(path -> path.getFileName().toString()))
            .noneMatch(name -> name.startsWith("ocr-"));
    }

    @Test
    void callerInterruptionCancelsRunningOcrAndStopsNewSubmissions() throws Exception {
        Path image = image(tempDir.resolve("source.png"));
        VisionOcrProperties properties = properties(1, 1);
        CountDownLatch started = new CountDownLatch(1);
        AtomicBoolean providerInterrupted = new AtomicBoolean();
        AtomicInteger attempts = new AtomicInteger();
        OcrProvider provider = request -> {
            attempts.incrementAndGet();
            started.countDown();
            try {
                Thread.sleep(30_000L);
                return succeeded("late");
            } catch (InterruptedException interruption) {
                providerInterrupted.set(true);
                Thread.currentThread().interrupt();
                return failed("interrupted");
            }
        };
        List<BoundedOcrExecutor.Job<Integer>> jobs = java.util.stream.IntStream.range(0, 8)
            .mapToObj(index -> new BoundedOcrExecutor.Job<>(
                index,
                index * 1_000L,
                image,
                tempDir.resolve("cancel-" + index)
            )).toList();
        AtomicReference<Throwable> failure = new AtomicReference<>();
        Thread caller = new Thread(() -> {
            try {
                new BoundedOcrExecutor().execute(jobs, provider, properties, Duration.ofMinutes(1));
            } catch (Throwable thrown) {
                failure.set(thrown);
            }
        });

        caller.start();
        assertThat(started.await(5, TimeUnit.SECONDS)).isTrue();
        caller.interrupt();
        caller.join(5_000L);

        assertThat(caller.isAlive()).isFalse();
        assertThat(failure.get()).isNotNull();
        assertThat(providerInterrupted.get()).isTrue();
        assertThat(attempts.get()).isLessThan(8);
    }

    @Test
    void oneFrameFailureDoesNotPreventLaterFrames() throws Exception {
        Path image = image(tempDir.resolve("source.png"));
        VisionOcrProperties properties = properties(2, 2);
        AtomicInteger calls = new AtomicInteger();
        OcrProvider provider = request -> {
            if (calls.getAndIncrement() == 1) {
                throw new IllegalStateException("one bad frame");
            }
            return succeeded("ok");
        };
        List<BoundedOcrExecutor.Job<Integer>> jobs = java.util.stream.IntStream.range(0, 3)
            .mapToObj(index -> new BoundedOcrExecutor.Job<>(
                index, index * 1_000L, image, tempDir.resolve("isolate-" + index)
            )).toList();

        BoundedOcrExecutor.Execution<Integer> result = new BoundedOcrExecutor().execute(
            jobs, provider, properties, Duration.ofSeconds(5)
        );

        assertThat(result.outcomes()).hasSize(3);
        assertThat(result.outcomes()).extracting(value -> value.ocrResult().status())
            .containsExactlyInAnyOrder(OcrStatus.SUCCEEDED, OcrStatus.SUCCEEDED, OcrStatus.FAILED);
    }

    @Test
    void overallTimeoutInterruptsRunningProvider() throws Exception {
        Path image = image(tempDir.resolve("source.png"));
        VisionOcrProperties properties = properties(1, 1);
        AtomicBoolean interrupted = new AtomicBoolean();
        OcrProvider provider = request -> {
            try {
                Thread.sleep(30_000L);
                return succeeded("late");
            } catch (InterruptedException failure) {
                interrupted.set(true);
                Thread.currentThread().interrupt();
                return failed("interrupted");
            }
        };

        assertThatThrownBy(() -> new BoundedOcrExecutor().execute(
            List.of(new BoundedOcrExecutor.Job<>(1, 0L, image, tempDir.resolve("timeout"))),
            provider,
            properties,
            Duration.ofMillis(50)
        )).isInstanceOf(com.example.courselingo.common.exception.BusinessException.class)
            .hasMessageContaining("timed out");
        assertThat(interrupted.get()).isTrue();
    }

    private static VisionOcrProperties properties(int concurrency, int queueCapacity) {
        VisionOcrProperties properties = new VisionOcrProperties();
        properties.setEnabled(true);
        properties.setConcurrency(concurrency);
        properties.setQueueCapacity(queueCapacity);
        properties.setPreprocessMaxWidth(640);
        return properties;
    }

    private static Path image(Path path) throws Exception {
        BufferedImage image = new BufferedImage(640, 360, BufferedImage.TYPE_INT_RGB);
        var graphics = image.createGraphics();
        graphics.setColor(Color.WHITE);
        graphics.fillRect(0, 0, image.getWidth(), image.getHeight());
        graphics.setColor(Color.BLACK);
        graphics.drawString("bounded OCR", 40, 80);
        graphics.dispose();
        ImageIO.write(image, "png", path.toFile());
        return path;
    }

    private static OcrResult succeeded(String text) {
        return new OcrResult(OcrStatus.SUCCEEDED, text, 0.9d, "fake", "eng", 1L, null, null);
    }

    private static OcrResult failed(String message) {
        return new OcrResult(OcrStatus.FAILED, "", null, "fake", "eng", 1L, "FAILED", message);
    }
}
