package com.example.courselingo.task.service;

import com.example.courselingo.task.dto.TaskBatchDeleteRequest;
import com.example.courselingo.task.dto.TaskBatchDeleteResponse;

public interface TaskBatchDeleteService {

    TaskBatchDeleteResponse delete(TaskBatchDeleteRequest request, String authorizationHeader);
}
