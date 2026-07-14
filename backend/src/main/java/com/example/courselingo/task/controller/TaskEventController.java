package com.example.courselingo.task.controller;

import com.example.courselingo.task.events.TaskEventStreamService;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
public class TaskEventController {

    private final TaskEventStreamService taskEventStreamService;

    public TaskEventController(TaskEventStreamService taskEventStreamService) {
        this.taskEventStreamService = taskEventStreamService;
    }

    @GetMapping(path = "/api/tasks/{taskId}/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter events(
        @PathVariable String taskId,
        @RequestHeader(value = "Authorization", required = false) String authorizationHeader
    ) {
        return taskEventStreamService.open(authorizationHeader, taskId);
    }
}
