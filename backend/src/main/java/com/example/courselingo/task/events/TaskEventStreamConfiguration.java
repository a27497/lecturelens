package com.example.courselingo.task.events;

import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(TaskEventStreamProperties.class)
public class TaskEventStreamConfiguration {

    @Bean(destroyMethod = "shutdown")
    public ScheduledExecutorService taskEventStreamExecutor(TaskEventStreamProperties properties) {
        ScheduledThreadPoolExecutor executor = new ScheduledThreadPoolExecutor(
            properties.workerThreads(),
            new TaskEventThreadFactory()
        );
        executor.setRemoveOnCancelPolicy(true);
        return executor;
    }

    private static final class TaskEventThreadFactory implements ThreadFactory {

        private final AtomicInteger index = new AtomicInteger(1);

        @Override
        public Thread newThread(Runnable runnable) {
            Thread thread = new Thread(runnable, "courselingo-task-events-" + index.getAndIncrement());
            thread.setDaemon(true);
            return thread;
        }
    }
}
