package com.example.courselingo.task.service;

import com.example.courselingo.task.dto.TaskDetailResponse;
import com.example.courselingo.task.dto.TaskListQuery;
import com.example.courselingo.task.dto.TaskListResponse;

public interface TaskQueryService {

    TaskListResponse list(TaskListQuery query, String authorizationHeader);

    TaskDetailResponse detail(String taskId, String authorizationHeader);
}
