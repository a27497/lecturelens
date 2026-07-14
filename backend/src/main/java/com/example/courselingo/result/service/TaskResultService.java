package com.example.courselingo.result.service;

import com.example.courselingo.result.dto.TaskResultResponse;

public interface TaskResultService {

    TaskResultResponse getResult(String taskId, String authorizationHeader);
}
