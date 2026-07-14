package com.example.courselingo.video.context.service;

import com.example.courselingo.video.context.dto.CourseVideoContextRebuildResponse;
import com.example.courselingo.video.context.dto.CourseVideoContextResponse;

public interface CourseVideoContextService {

    CourseVideoContextResponse get(String taskId, String authorizationHeader);

    CourseVideoContextRebuildResponse rebuild(String taskId, String authorizationHeader);
}
