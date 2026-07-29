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
        ExecutorService streamReaders = Executors.newFixedThreadPool(2, runnable -> {
            Thread thread = new Thread(runnable, "courselingo-ocr-stream-reader");
            thread.setDaemon(true);
            return thread;
        });
        Future<String> stdout = streamReaders.submit(readStream(process.getInputStream()));
        Future<String> stderr = streamReaders.submit(readStream(process.getErrorStream()));
        try {
            boolean finished = process.waitFor(timeout.toMillis(), TimeUnit.MILLISECONDS);
            if (!finished) {
                terminateProcessTree(process);
                return new OcrProcessResult(-1, futureText(stdout), futureText(stderr), true);
            }
            return new OcrProcessResult(process.exitValue(), futureText(stdout), futureText(stderr), false);
        } catch (InterruptedException exception) {
            terminateProcessTree(process);
            Thread.currentThread().interrupt();
            throw exception;
        } finally {
            shutdownStreamReaders(streamReaders, process);
        }
    }

    private static void shutdownStreamReaders(ExecutorService streamReaders, Process process) {
        streamReaders.shutdownNow();
        closeQuietly(process.getInputStream());
        closeQuietly(process.getErrorStream());
        try {
            streamReaders.awaitTermination(1, TimeUnit.SECONDS);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
        }
    }

    private static void closeQuietly(InputStream stream) {
        try {
            stream.close();
        } catch (IOException ignored) {
            // Process teardown is already complete; stream cleanup is best effort.
        }
    }

    private static void terminateProcessTree(Process process) {
        if (process == null) {
            return;
        }
        try {
            process.descendants()
                .sorted(java.util.Comparator.comparingLong(ProcessHandle::pid).reversed())
                .forEach(ProcessHandle::destroyForcibly);
        } catch (UnsupportedOperationException | SecurityException ignored) {
            // Custom/test Process implementations may not expose a ProcessHandle.
        }
        process.destroyForcibly();
        try {
            process.waitFor(2, TimeUnit.SECONDS);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
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
