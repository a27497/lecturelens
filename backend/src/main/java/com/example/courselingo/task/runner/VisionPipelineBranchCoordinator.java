package com.example.courselingo.task.runner;

import com.example.courselingo.common.tracing.TracingContextHolder;
import java.time.Duration;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.Callable;
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.FutureTask;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

final class VisionPipelineBranchCoordinator implements AutoCloseable {

    private static final Duration DEFAULT_SHUTDOWN_TIMEOUT = Duration.ofSeconds(30);

    private final ThreadPoolExecutor executor;

    VisionPipelineBranchCoordinator(int concurrency, int queueCapacity) {
        if (concurrency <= 0 || queueCapacity <= 0) {
            throw new IllegalArgumentException("vision branch pool bounds must be positive");
        }
        this.executor = new ThreadPoolExecutor(
            concurrency,
            concurrency,
            0L,
            TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<>(queueCapacity),
            new VisionBranchThreadFactory(),
            new ThreadPoolExecutor.AbortPolicy()
        );
        this.executor.allowCoreThreadTimeOut(false);
    }

    VisionPipelineBranchHandle submit(Callable<?> branch, Duration timeout) {
        Objects.requireNonNull(branch, "vision branch is required");
        Duration effectiveTimeout = requirePositive(timeout);
        Callable<VisionPipelineBranchResult> traced = TracingContextHolder.wrapCurrent(() -> {
            branch.call();
            return VisionPipelineBranchResult.succeeded();
        });
        BranchFutureTask future = new BranchFutureTask(traced, executor);
        VisionPipelineBranchHandle handle = new VisionPipelineBranchHandle(
            future,
            deadlineAfter(effectiveTimeout)
        );
        try {
            executor.execute(future);
        } catch (RejectedExecutionException exception) {
            future.reject(exception);
        }
        return handle;
    }

    int maximumPoolSize() {
        return executor.getMaximumPoolSize();
    }

    int queueCapacity() {
        return executor.getQueue().size() + executor.getQueue().remainingCapacity();
    }

    @Override
    public void close() {
        executor.shutdown();
        try {
            if (executor.awaitTermination(DEFAULT_SHUTDOWN_TIMEOUT.toSeconds(), TimeUnit.SECONDS)) {
                return;
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
        }
        List<Runnable> neverStarted = executor.shutdownNow();
        neverStarted.forEach(runnable -> {
            if (runnable instanceof BranchFutureTask future) {
                future.cancelNeverStarted();
            }
        });
        try {
            executor.awaitTermination(DEFAULT_SHUTDOWN_TIMEOUT.toSeconds(), TimeUnit.SECONDS);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
        }
    }

    private static Duration requirePositive(Duration timeout) {
        if (timeout == null || timeout.isZero() || timeout.isNegative()) {
            throw new IllegalArgumentException("vision branch timeout must be positive");
        }
        return timeout;
    }

    private static long deadlineAfter(Duration timeout) {
        long now = System.nanoTime();
        long nanos;
        try {
            nanos = timeout.toNanos();
        } catch (ArithmeticException exception) {
            return Long.MAX_VALUE;
        }
        if (nanos > Long.MAX_VALUE - now) {
            return Long.MAX_VALUE;
        }
        return now + nanos;
    }

    static final class VisionPipelineBranchHandle {

        private final BranchFutureTask future;
        private final long deadlineNanos;

        private VisionPipelineBranchHandle(BranchFutureTask future, long deadlineNanos) {
            this.future = future;
            this.deadlineNanos = deadlineNanos;
        }

        VisionPipelineBranchResult await() throws InterruptedException {
            long remainingNanos = deadlineNanos - System.nanoTime();
            if (remainingNanos <= 0L) {
                TimeoutException timeout = new TimeoutException("vision preprocessing branch deadline exceeded");
                future.cancelAndAwaitExit();
                return VisionPipelineBranchResult.timedOut(timeout);
            }
            try {
                return future.get(remainingNanos, TimeUnit.NANOSECONDS);
            } catch (TimeoutException exception) {
                future.cancelAndAwaitExit();
                return VisionPipelineBranchResult.timedOut(exception);
            } catch (CancellationException exception) {
                future.awaitExitUninterruptibly();
                return VisionPipelineBranchResult.cancelled(exception);
            } catch (ExecutionException exception) {
                Throwable cause = exception.getCause() == null ? exception : exception.getCause();
                return VisionPipelineBranchResult.failed(cause);
            } catch (InterruptedException exception) {
                future.cancelAndAwaitExit();
                throw exception;
            }
        }

        void cancelAndAwaitExit() {
            future.cancelAndAwaitExit();
        }
    }

    private static final class BranchFutureTask extends FutureTask<VisionPipelineBranchResult> {

        private final ThreadPoolExecutor owner;
        private final CountDownLatch exited = new CountDownLatch(1);
        private final AtomicBoolean started = new AtomicBoolean(false);

        private BranchFutureTask(Callable<VisionPipelineBranchResult> callable, ThreadPoolExecutor owner) {
            super(callable);
            this.owner = owner;
        }

        @Override
        public void run() {
            started.set(true);
            try {
                super.run();
            } finally {
                exited.countDown();
            }
        }

        private void reject(RejectedExecutionException exception) {
            super.set(VisionPipelineBranchResult.failed(exception));
            exited.countDown();
        }

        private void cancelAndAwaitExit() {
            cancel(true);
            if (!started.get() && owner.remove(this)) {
                exited.countDown();
            }
            awaitExitUninterruptibly();
        }

        private void cancelNeverStarted() {
            cancel(true);
            exited.countDown();
        }

        private void awaitExitUninterruptibly() {
            boolean interrupted = false;
            while (true) {
                try {
                    exited.await();
                    break;
                } catch (InterruptedException exception) {
                    interrupted = true;
                }
            }
            if (interrupted) {
                Thread.currentThread().interrupt();
            }
        }
    }

    private static final class VisionBranchThreadFactory implements ThreadFactory {

        private final AtomicInteger nextIndex = new AtomicInteger(1);

        @Override
        public Thread newThread(Runnable runnable) {
            Thread thread = new Thread(runnable);
            thread.setName("courselingo-vision-branch-" + nextIndex.getAndIncrement());
            thread.setDaemon(false);
            return thread;
        }
    }
}
