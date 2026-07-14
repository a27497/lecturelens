package com.example.courselingo.dispatch;

import java.util.concurrent.Callable;

public interface BoundedTaskExecutor {

    <T> T submitAndWait(String taskId, String requestId, Callable<T> callable);

    void execute(String taskId, String requestId, Runnable runnable);
}
