package com.example.courselingo.vision.ocr;

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

class ProcessBuilderOcrProcessExecutor implements OcrProcessExecutor {

    private static final int STREAM_CAPTURE_LIMIT_BYTES = 16 * 1024;

    @Override
    public OcrProcessResult execute(List<String> command, Duration timeout) throws IOException, InterruptedException {
        Process process = new ProcessBuilder(List.copyOf(command))
            .redirectErrorStream(false)
            .start();
        ExecutorService streamReaders = Executors.newFixedThreadPool(2);
        Future<String> stdout = streamReaders.submit(readStream(process.getInputStream()));
        Future<String> stderr = streamReaders.submit(readStream(process.getErrorStream()));
        try {
            boolean finished = process.waitFor(timeout.toMillis(), TimeUnit.MILLISECONDS);
            if (!finished) {
                process.destroyForcibly();
                return new OcrProcessResult(-1, futureText(stdout), futureText(stderr), true);
            }
            return new OcrProcessResult(process.exitValue(), futureText(stdout), futureText(stderr), false);
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
}
