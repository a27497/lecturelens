package com.example.courselingo.dispatch;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.tracing.TracingContextHolder;
import jakarta.annotation.PreDestroy;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.Callable;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;

@Component
public class ThreadPoolBoundedTaskExecutor implements BoundedTaskExecutor {

    private static final Pattern SENSITIVE_WORDS = Pattern.compile(
        "(?i)access\\s*token|refresh\\s*token|api\\s*key|secret\\s*key|token|secret"
    );
    private static final Pattern WINDOWS_PATH = Pattern.compile("[A-Za-z]:\\\\\\S*");
    private static final Pattern UNIX_HOME_PATH = Pattern.compile("/(?:home|Users)/\\S*");

    private final BoundedTaskExecutorProperties properties;
    private final ArrayBlockingQueue<Runnable> workQueue;
    private final ThreadPoolExecutor delegate;

    public ThreadPoolBoundedTaskExecutor(BoundedTaskExecutorProperties properties) {
        validate(properties);
        this.properties = properties;
        this.workQueue = new ArrayBlockingQueue<>(properties.queueCapacity());
        this.delegate = new ThreadPoolExecutor(
            properties.coreSize(),
            properties.maxSize(),
            properties.keepAliveSeconds(),
            TimeUnit.SECONDS,
            workQueue,
            new AnalysisWorkerThreadFactory(),
            new ThreadPoolExecutor.AbortPolicy()
        );
        this.delegate.allowCoreThreadTimeOut(false);
    }

    @Override
    public <T> T submitAndWait(String taskId, String requestId, Callable<T> callable) {
        validateTask(taskId, requestId, callable);
        if (delegate.isShutdown()) {
            throw new BusinessException(ErrorCode.TASK_EXECUTOR_SHUTDOWN);
        }

        Future<T> future;
        try {
            future = delegate.submit(TracingContextHolder.wrapCurrent(callable));
        } catch (RejectedExecutionException exception) {
            throw new BusinessException(ErrorCode.TASK_EXECUTOR_BUSY);
        }

        try {
            return future.get(properties.taskTimeoutSeconds(), TimeUnit.SECONDS);
        } catch (TimeoutException exception) {
            future.cancel(true);
            throw new BusinessException(ErrorCode.TASK_EXECUTOR_TIMEOUT);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new BusinessException(ErrorCode.TASK_EXECUTOR_FAILED);
        } catch (java.util.concurrent.ExecutionException exception) {
            throw wrapExecutionException(exception.getCause());
        }
    }

    @Override
    public void execute(String taskId, String requestId, Runnable runnable) {
        submitAndWait(taskId, requestId, () -> {
            runnable.run();
            return null;
        });
    }

    @PreDestroy
    public void shutdown() {
        delegate.shutdown();
        try {
            if (!delegate.awaitTermination(properties.shutdownTimeoutSeconds(), TimeUnit.SECONDS)) {
                delegate.shutdownNow();
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            delegate.shutdownNow();
        }
    }

    public boolean isShutdown() {
        return delegate.isShutdown();
    }

    public boolean isTerminated() {
        return delegate.isTerminated();
    }

    public int corePoolSize() {
        return delegate.getCorePoolSize();
    }

    public int maximumPoolSize() {
        return delegate.getMaximumPoolSize();
    }

    public int queueCapacity() {
        return properties.queueCapacity();
    }

    public int remainingQueueCapacity() {
        return workQueue.remainingCapacity();
    }

    public int queueSize() {
        return workQueue.size();
    }

    private RuntimeException wrapExecutionException(Throwable cause) {
        if (cause instanceof BusinessException businessException) {
            return new BusinessException(
                businessException.errorCode(),
                sanitize(businessException.getMessage()),
                businessException
            );
        }
        return new BusinessException(ErrorCode.TASK_EXECUTOR_FAILED, sanitize(cause == null ? null : cause.getMessage()), cause);
    }

    private static void validate(BoundedTaskExecutorProperties properties) {
        if (properties == null
            || properties.coreSize() <= 0
            || properties.maxSize() < properties.coreSize()
            || properties.queueCapacity() <= 0
            || properties.keepAliveSeconds() < 0
            || properties.taskTimeoutSeconds() <= 0
            || properties.shutdownTimeoutSeconds() < 0) {
            throw new BusinessException(ErrorCode.TASK_EXECUTOR_CONFIGURATION_INVALID);
        }
    }

    private static void validateTask(String taskId, String requestId, Object task) {
        if (isBlank(taskId) || isBlank(requestId) || task == null) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED);
        }
    }

    private static String sanitize(String value) {
        if (value == null) {
            return null;
        }
        String sanitized = SENSITIVE_WORDS.matcher(value).replaceAll("[redacted]");
        sanitized = WINDOWS_PATH.matcher(sanitized).replaceAll("[path]");
        return UNIX_HOME_PATH.matcher(sanitized).replaceAll("[path]");
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private static class AnalysisWorkerThreadFactory implements ThreadFactory {

        private final AtomicInteger nextId = new AtomicInteger(1);

        @Override
        public Thread newThread(Runnable runnable) {
            Thread thread = new Thread(runnable);
            thread.setName("courselingo-analysis-worker-" + nextId.getAndIncrement());
            thread.setDaemon(false);
            return thread;
        }
    }
}
