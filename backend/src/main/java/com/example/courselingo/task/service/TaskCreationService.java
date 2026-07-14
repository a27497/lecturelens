package com.example.courselingo.task.service;

import com.example.courselingo.task.dto.CreateAnalysisTaskRequest;
import com.example.courselingo.task.dto.CreateAnalysisTaskResponse;

public interface TaskCreationService {

    CreateAnalysisTaskResponse create(CreateAnalysisTaskRequest request, String authorizationHeader);
}
