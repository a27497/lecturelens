package com.example.courselingo.vision.adaptive;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.logging.SafeLogSanitizer;
import com.example.courselingo.vision.ocr.OcrProvider;
import com.example.courselingo.vision.ocr.OcrRequest;
import com.example.courselingo.vision.ocr.OcrResult;
import com.example.courselingo.vision.ocr.OcrStatus;
import com.example.courselingo.vision.ocr.VisionOcrProperties;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletionService;
import java.util.concurrent.ExecutorCompletionService;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

/** Runs local OCR with explicit concurrency, queue, cancellation, and ordering bounds. */
public final class BoundedOcrExecutor {

    public record Job<T>(T payload, long timestampMillis, Path sourceImage, Path workDirectory) {

        public Job {
            Objects.requireNonNull(payload, "payload");
            Objects.requireNonNull(sourceImage, "sourceImage");
            Objects.requireNonNull(workDirectory, "workDirectory");
            timestampMillis = Math.max(0L, timestampMillis);
        }
    }

    public record Outcome<T>(T payload, long timestampMillis, OcrResult ocrResult) {
    }

    public record Execution<T>(List<Outcome<T>> outcomes, int attemptedCount) {

        public Execution {
            outcomes = outcomes == null ? List.of() : List.copyOf(outcomes);
            attemptedCount = Math.max(0, attemptedCount);
        }
    }

    public <T> Execution<T> execute(
        List<Job<T>> input,
        OcrProvider provider,
        VisionOcrProperties properties,
        Duration overallTimeout
    ) {
        List<Job<T>> jobs = input == null
            ? List.of()
            : input.stream().filter(Objects::nonNull).sorted(Comparator.comparingLong(Job::timestampMillis)).toList();
        if (jobs.isEmpty()) {
            return new Execution<>(List.of(), 0);
        }
        if (provider == null || properties == null || !properties.isEnabled()) {
            return new Execution<>(jobs.stream().map(job -> new Outcome<>(
                job.payload(), job.timestampMillis(), disabled(properties)
            )).toList(), 0);
        }

        int concurrency = properties.getConcurrency();
        int queueCapacity = properties.getQueueCapacity();
        AtomicInteger threadSequence = new AtomicInteger();
        ThreadFactory threadFactory = runnable -> {
            Thread thread = new Thread(runnable, "courselingo-ocr-" + threadSequence.incrementAndGet());
            thread.setDaemon(true);
            return thread;
        };
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
            concurrency,
            concurrency,
            0L,
            TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<>(queueCapacity),
            threadFactory,
            new ThreadPoolExecutor.AbortPolicy()
        );
        CompletionService<Outcome<T>> completion = new ExecutorCompletionService<>(executor);
        Map<Future<Outcome<T>>, Job<T>> active = new HashMap<>();
        Map<T, Integer> originalOrder = new HashMap<>();
        for (int index = 0; index < jobs.size(); index++) {
            originalOrder.put(jobs.get(index).payload(), index);
        }
        int inFlightLimit = concurrency + queueCapacity;
        int submitted = 0;
        int completed = 0;
        AtomicInteger attempted = new AtomicInteger();
        List<Outcome<T>> outcomes = new ArrayList<>(jobs.size());
        long timeoutNanos = effectiveTimeout(overallTimeout).toNanos();
        long deadline = System.nanoTime() + timeoutNanos;
        try {
            while (completed < jobs.size()) {
                ensureNotInterrupted();
                while (submitted < jobs.size() && active.size() < inFlightLimit) {
                    Job<T> job = jobs.get(submitted++);
                    Future<Outcome<T>> future = completion.submit(() -> recognize(job, provider, properties, attempted));
                    active.put(future, job);
                }
                long remaining = deadline - System.nanoTime();
                if (remaining <= 0L) {
                    throw new BusinessException(ErrorCode.TASK_EXECUTOR_TIMEOUT, "OCR frame budget timed out");
                }
                Future<Outcome<T>> future = completion.poll(remaining, TimeUnit.NANOSECONDS);
                if (future == null) {
                    throw new BusinessException(ErrorCode.TASK_EXECUTOR_TIMEOUT, "OCR frame budget timed out");
                }
                Job<T> completedJob = active.remove(future);
                try {
                    outcomes.add(future.get());
                } catch (java.util.concurrent.ExecutionException failure) {
                    Throwable cause = failure.getCause();
                    if (cause instanceof Error error) {
                        throw error;
                    }
                    outcomes.add(new Outcome<>(
                        completedJob.payload(),
                        completedJob.timestampMillis(),
                        failed(properties, cause)
                    ));
                }
                completed++;
            }
            outcomes.sort(Comparator.comparingInt(value -> originalOrder.getOrDefault(value.payload(), Integer.MAX_VALUE)));
            return new Execution<>(outcomes, attempted.get());
        } catch (InterruptedException interruption) {
            Thread.currentThread().interrupt();
            throw new BusinessException(ErrorCode.MEDIA_FFMPEG_FAILED, "OCR frame processing was interrupted", interruption);
        } finally {
            active.keySet().forEach(future -> future.cancel(true));
            executor.shutdownNow();
            try {
                executor.awaitTermination(2, TimeUnit.SECONDS);
            } catch (InterruptedException interruption) {
                Thread.currentThread().interrupt();
            }
        }
    }

    private static <T> Outcome<T> recognize(
        Job<T> job,
        OcrProvider provider,
        VisionOcrProperties properties,
        AtomicInteger attempted
    ) {
        attempted.incrementAndGet();
        OcrImagePreprocessor preprocessor = new OcrImagePreprocessor();
        try {
            if (Thread.currentThread().isInterrupted()) {
                return new Outcome<>(job.payload(), job.timestampMillis(), interrupted(properties));
            }
            OcrPreprocessingResult images = preprocessor.preprocess(
                job.sourceImage(),
                job.workDirectory(),
                new OcrImagePreprocessor.Options(
                    properties.getPreprocessMaxWidth(),
                    1.5d,
                    1.25d,
                    0.18d,
                    properties.isBinarizationEnabled()
                )
            );
            OcrResult result = provider.recognize(new OcrRequest(images.enhancedImage()));
            return new Outcome<>(job.payload(), job.timestampMillis(), result == null ? failed(properties, null) : result);
        } catch (RuntimeException failure) {
            return new Outcome<>(job.payload(), job.timestampMillis(), failed(properties, failure));
        } finally {
            deleteDirectoryBestEffort(job.workDirectory());
        }
    }

    private static Duration effectiveTimeout(Duration timeout) {
        return timeout == null || timeout.isZero() || timeout.isNegative() ? Duration.ofMinutes(30) : timeout;
    }

    private static void ensureNotInterrupted() throws InterruptedException {
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedException("OCR work was cancelled");
        }
    }

    private static OcrResult disabled(VisionOcrProperties properties) {
        return new OcrResult(
            OcrStatus.DISABLED,
            "",
            null,
            properties == null ? "disabled" : properties.getProvider(),
            properties == null ? "" : properties.getLanguage(),
            0L,
            null,
            null
        );
    }

    private static OcrResult interrupted(VisionOcrProperties properties) {
        return new OcrResult(
            OcrStatus.FAILED,
            "",
            null,
            properties.getProvider(),
            properties.getLanguage(),
            null,
            "OCR_INTERRUPTED",
            "OCR frame processing was interrupted"
        );
    }

    private static OcrResult failed(VisionOcrProperties properties, Throwable failure) {
        return new OcrResult(
            OcrStatus.FAILED,
            "",
            null,
            properties.getProvider(),
            properties.getLanguage(),
            null,
            "OCR_FRAME_FAILED",
            failure == null ? "OCR returned no result" : SafeLogSanitizer.sanitizeAndLimit(failure.getMessage())
        );
    }

    private static boolean deleteDirectoryBestEffort(Path directory) {
        if (directory == null || !Files.exists(directory)) {
            return true;
        }
        boolean[] success = {true};
        try (var paths = Files.walk(directory)) {
            paths.sorted(Comparator.reverseOrder()).forEach(path -> {
                try {
                    Files.deleteIfExists(path);
                } catch (IOException ignored) {
                    success[0] = false;
                }
            });
        } catch (IOException ignored) {
            return false;
        }
        return success[0];
    }
}
