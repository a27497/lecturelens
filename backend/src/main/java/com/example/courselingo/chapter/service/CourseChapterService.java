package com.example.courselingo.chapter.service;

import com.example.courselingo.chapter.dto.CourseChapterResponse;
import java.util.List;

public interface CourseChapterService {

    List<CourseChapterResponse> list(String taskId, String authorizationHeader);

    List<CourseChapterResponse> generate(String taskId, String authorizationHeader);
}
