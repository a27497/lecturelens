package com.example.courselingo.media;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

class ProcessBuilderFfmpegProcessExecutor implements FfmpegProcessExecutor {

    private static final int STREAM_CAPTURE_LIMIT_BYTES = 8 * 1024;
    private final ProcessStarter processStarter;

    ProcessBuilderFfmpegProcessExecutor() {
        this(command -> new ProcessBuilder(command)
            .redirectErrorStream(false)
            .start());
    }

    ProcessBuilderFfmpegProcessExecutor(ProcessStarter processStarter) {
        this.processStarter = processStarter;
    }

    @Override
    public FfmpegProcessResult execute(List<String> command, Duration timeout) throws IOException, InterruptedException {
        Process process = processStarter.start(List.copyOf(command));
        ExecutorService streamReaders = Executors.newFixedThreadPool(2);
        Future<String> stdout = streamReaders.submit(readStream(process.getInputStream()));
        Future<String> stderr = streamReaders.submit(readStream(process.getErrorStream()));
        try {
            boolean finished = process.waitFor(timeout.toMillis(), TimeUnit.MILLISECONDS);
            if (!finished) {
                process.destroyForcibly();
                return new FfmpegProcessResult(
                    -1,
                    futureText(stdout),
                    futureText(stderr),
                    true
                );
            }
            return new FfmpegProcessResult(
                process.exitValue(),
                futureText(stdout),
                futureText(stderr),
                false
            );
        } finally {
            streamReaders.shutdownNow();
        }
    }

    private Callable<String> readStream(InputStream stream) {
        return () -> {
            byte[] buffer = new byte[1024];
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            int read;
            while ((read = stream.read(buffer)) != -1) {
                int writable = Math.min(read, STREAM_CAPTURE_LIMIT_BYTES - output.size());
                if (writable > 0) {
                    output.write(buffer, 0, writable);
                }
            }
            return output.toString(StandardCharsets.UTF_8);
        };
    }

    private String futureText(Future<String> future) throws InterruptedException {
        try {
            return future.get(1, TimeUnit.SECONDS);
        } catch (ExecutionException | TimeoutException ex) {
            return "";
        }
    }

    @FunctionalInterface
    interface ProcessStarter {

        Process start(List<String> command) throws IOException;
    }
}
