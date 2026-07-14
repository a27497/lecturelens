package com.example.courselingo.dispatch;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

class BoundedTaskExecutorTest {

    private ThreadPoolBoundedTaskExecutor executor;

    @AfterEach
    void tearDown() {
        if (executor != null) {
            executor.shutdown();
        }
    }

    @Test
    void submitAndWaitExecutesCallableAndReturnsValue() {
        executor = newExecutor(1, 1, 1, 5);

        String result = executor.submitAndWait("task_1", "req_1", () -> "ok");

        assertThat(result).isEqualTo("ok");
    }

    @Test
    void executeRunsRunnableSuccessfully() {
        executor = newExecutor(1, 1, 1, 5);
        AtomicBoolean called = new AtomicBoolean(false);

        executor.execute("task_1", "req_1", () -> called.set(true));

        assertThat(called).isTrue();
    }

    @Test
    void preservesBusinessExceptionErrorCodeAndSanitizesMessageFromCallable() {
        executor = newExecutor(1, 1, 1, 5);

        assertThatThrownBy(() -> executor.submitAndWait("task_1", "req_1", () -> {
            throw new BusinessException(
                ErrorCode.TASK_RUNNER_EXECUTION_FAILED,
                sensitiveMessage()
            );
        }))
            .isInstanceOf(BusinessException.class)
            .satisfies(error -> {
                BusinessException exception = (BusinessException) error;
                assertThat(exception.errorCode()).isEqualTo(ErrorCode.TASK_RUNNER_EXECUTION_FAILED);
                assertSanitized(exception.getMessage());
            });
    }

    @Test
    void wrapsRunnableExceptionWithSanitizedMessage() {
        executor = newExecutor(1, 1, 1, 5);

        assertThatThrownBy(() -> executor.execute("task_1", "req_1", () -> {
            throw new IllegalStateException(sensitiveMessage());
        }))
            .isInstanceOf(BusinessException.class)
            .satisfies(error -> {
                BusinessException exception = (BusinessException) error;
                assertThat(exception.errorCode()).isEqualTo(ErrorCode.TASK_EXECUTOR_FAILED);
                assertSanitized(exception.getMessage());
            });
    }

    @Test
    void rejectsSubmissionWhenQueueIsFullWithExplicitErrorCode() throws Exception {
        executor = newExecutor(1, 1, 1, 5);
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        Thread first = new Thread(() -> executor.execute("task_running", "req_running", () -> {
            started.countDown();
            await(release);
        }));
        first.start();
        assertThat(started.await(1, TimeUnit.SECONDS)).isTrue();

        CountDownLatch queuedStarted = new CountDownLatch(1);
        Thread queued = new Thread(() -> executor.execute("task_queued", "req_queued", queuedStarted::countDown));
        queued.start();
        waitUntil(() -> executor.queueSize() == 1);

        assertThatThrownBy(() -> executor.execute("task_rejected", "req_rejected", () -> { }))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_EXECUTOR_BUSY);

        release.countDown();
        first.join(1000);
        queued.join(1000);
    }

    @Test
    void usesBoundedQueueAndConfiguredPoolSizes() {
        executor = newExecutor(2, 4, 3, 5);

        assertThat(executor.queueCapacity()).isEqualTo(3);
        assertThat(executor.remainingQueueCapacity()).isEqualTo(3);
        assertThat(executor.corePoolSize()).isEqualTo(2);
        assertThat(executor.maximumPoolSize()).isEqualTo(4);
    }

    @Test
    void defaultTaskTimeoutAllowsFourHourPipelineExecution() {
        BoundedTaskExecutorProperties properties = new BoundedTaskExecutorProperties();

        assertThat(properties.taskTimeoutSeconds()).isEqualTo(14_400L);
    }

    @Test
    void rejectsInvalidConfiguration() {
        assertThatThrownBy(() -> new ThreadPoolBoundedTaskExecutor(properties(4, 2, 1, 60, 5, 1)))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_EXECUTOR_CONFIGURATION_INVALID);

        assertThatThrownBy(() -> new ThreadPoolBoundedTaskExecutor(properties(1, 1, 0, 60, 5, 1)))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_EXECUTOR_CONFIGURATION_INVALID);

        assertThatThrownBy(() -> new ThreadPoolBoundedTaskExecutor(properties(1, 1, 1, 60, 0, 1)))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_EXECUTOR_CONFIGURATION_INVALID);

        assertThatThrownBy(() -> new ThreadPoolBoundedTaskExecutor(properties(1, 1, 1, 60, 5, -1)))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_EXECUTOR_CONFIGURATION_INVALID);
    }

    @Test
    void shutdownStopsNewSubmissionsAndTerminatesWithinTimeout() {
        executor = newExecutor(1, 1, 1, 5);

        executor.shutdown();

        assertThat(executor.isShutdown()).isTrue();
        assertThat(executor.isTerminated()).isTrue();
        assertThatThrownBy(() -> executor.execute("task_1", "req_1", () -> { }))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_EXECUTOR_SHUTDOWN);
    }

    @Test
    void workerThreadNameIsRecognizable() {
        executor = newExecutor(1, 1, 1, 5);
        AtomicReference<String> threadName = new AtomicReference<>();

        executor.execute("task_1", "req_1", () -> threadName.set(Thread.currentThread().getName()));

        assertThat(threadName.get()).startsWith("courselingo-analysis-worker-");
    }

    @Test
    void taskTimeoutFailsWithoutHanging() {
        executor = newExecutor(1, 1, 1, 1);

        assertThatThrownBy(() -> executor.submitAndWait("task_1", "req_1", () -> {
            Thread.sleep(5_000);
            return "too-late";
        }))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_EXECUTOR_TIMEOUT);
    }

    private ThreadPoolBoundedTaskExecutor newExecutor(
        int coreSize,
        int maxSize,
        int queueCapacity,
        int taskTimeoutSeconds
    ) {
        return new ThreadPoolBoundedTaskExecutor(
            properties(coreSize, maxSize, queueCapacity, 1, taskTimeoutSeconds, 1)
        );
    }

    private static BoundedTaskExecutorProperties properties(
        int coreSize,
        int maxSize,
        int queueCapacity,
        int keepAliveSeconds,
        int taskTimeoutSeconds,
        int shutdownTimeoutSeconds
    ) {
        return new BoundedTaskExecutorProperties(
            coreSize,
            maxSize,
            queueCapacity,
            keepAliveSeconds,
            taskTimeoutSeconds,
            shutdownTimeoutSeconds
        );
    }

    private static void assertSanitized(String value) {
        assertThat(value).doesNotContainIgnoringCase("token");
        assertThat(value).doesNotContainIgnoringCase("secret");
        assertThat(value).doesNotContainIgnoringCase("api key");
        assertThat(value).doesNotContain("C:\\");
        assertThat(value).doesNotContain("/home/");
    }

    private static String sensitiveMessage() {
        return "access token raw refresh token raw secret key raw api key raw C:\\Users\\demo\\a.mp4 /home/demo/a.mp4";
    }

    private static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
        }
    }

    private static void waitUntil(BooleanSupplier supplier) throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(1);
        while (!supplier.getAsBoolean() && System.nanoTime() < deadline) {
            Thread.sleep(10);
        }
        assertThat(supplier.getAsBoolean()).isTrue();
    }

    private interface BooleanSupplier {
        boolean getAsBoolean();
    }
}
