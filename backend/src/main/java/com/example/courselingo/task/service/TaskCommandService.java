package com.example.courselingo.task.service;

import com.example.courselingo.task.dto.TaskCommandResponse;
import com.example.courselingo.task.dto.TaskRetryResponse;

public interface TaskCommandService {

    TaskRetryResponse retry(String taskId, String authorizationHeader);

    TaskCommandResponse cancel(String taskId, String authorizationHeader);
}
