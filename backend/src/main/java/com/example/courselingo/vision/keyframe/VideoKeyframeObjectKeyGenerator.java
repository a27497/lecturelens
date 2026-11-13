package com.example.courselingo.vision.keyframe;

import java.util.regex.Pattern;

final class VideoKeyframeObjectKeyGenerator {

    private static final Pattern UNSAFE = Pattern.compile("[^A-Za-z0-9._-]");

    private VideoKeyframeObjectKeyGenerator() {
    }

    static String generate(Long userId, String taskId, int frameIndex) {
        var execution=com.example.courselingo.task.service.PipelineExecutionScope.current();
        String generation=execution==null?"":"/execution-"+execution.epoch()+"-"+safe(execution.eventId());
        return "keyframes/"
            + safe(userId)
            + "/"
            + safe(taskId)
            + generation
            + "/frame-"
            + String.format("%06d", frameIndex)
            + ".jpg";
    }

    private static String safe(Object value) {
        if (value == null) {
            return "unknown";
        }
        String safe = UNSAFE.matcher(String.valueOf(value)).replaceAll("_");
        if (safe.isBlank()) {
            return "unknown";
        }
        return safe.length() > 80 ? safe.substring(0, 80) : safe;
    }
}
