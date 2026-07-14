package com.example.courselingo.task.events;

import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

public interface TaskEventStreamService {

    SseEmitter open(String authorizationHeader, String taskId);
}
