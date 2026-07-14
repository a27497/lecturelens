package com.example.courselingo.qa.service;

import com.example.courselingo.qa.dto.CourseQaAskRequest;
import com.example.courselingo.qa.dto.CourseQaResponse;

public interface CourseQaService {

    CourseQaResponse ask(String taskId, String authorizationHeader, CourseQaAskRequest request);
}
