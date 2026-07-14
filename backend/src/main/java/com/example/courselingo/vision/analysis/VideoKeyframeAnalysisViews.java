package com.example.courselingo.vision.analysis;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

public final class VideoKeyframeAnalysisViews {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();
    private static final TypeReference<List<String>> STRING_LIST = new TypeReference<>() {
    };

    private VideoKeyframeAnalysisViews() {
    }

    public static Map<Long, VideoKeyframeAnalysisView> byKeyframeId(Collection<VideoKeyframeAnalysis> rows) {
        if (rows == null || rows.isEmpty()) {
            return Map.of();
        }
        return rows.stream().collect(Collectors.toMap(
            VideoKeyframeAnalysis::getKeyframeId,
            VideoKeyframeAnalysisViews::toView,
            (left, right) -> left
        ));
    }

    public static VideoKeyframeAnalysisView missing(boolean enabled) {
        if (!enabled) {
            return new VideoKeyframeAnalysisView(
                VisionAnalysisStatus.DISABLED.name(),
                "",
                "",
                List.of(),
                "",
                "",
                "视觉分析暂未启用"
            );
        }
        return new VideoKeyframeAnalysisView(
            VisionAnalysisStatus.PENDING.name(),
            "",
            "",
            List.of(),
            "",
            "",
            "视觉分析待生成"
        );
    }

    public static Function<Long, VideoKeyframeAnalysisView> resolver(
        Map<Long, VideoKeyframeAnalysisView> views,
        boolean enabled
    ) {
        return keyframeId -> views.getOrDefault(keyframeId, missing(enabled));
    }

    private static VideoKeyframeAnalysisView toView(VideoKeyframeAnalysis row) {
        VisionAnalysisStatus status = parseStatus(row.getStatus());
        return new VideoKeyframeAnalysisView(
            status.name(),
            status == VisionAnalysisStatus.SUCCEEDED ? nullToEmpty(row.getScreenType()) : "",
            status == VisionAnalysisStatus.SUCCEEDED ? nullToEmpty(row.getVisualSummary()) : "",
            status == VisionAnalysisStatus.SUCCEEDED ? detectedElements(row.getDetectedElementsJson()) : List.of(),
            nullToEmpty(row.getProvider()),
            nullToEmpty(row.getModel()),
            message(status)
        );
    }

    private static VisionAnalysisStatus parseStatus(String status) {
        try {
            return VisionAnalysisStatus.valueOf(status);
        } catch (RuntimeException ex) {
            return VisionAnalysisStatus.PENDING;
        }
    }

    private static List<String> detectedElements(String json) {
        if (json == null || json.isBlank()) {
            return List.of();
        }
        try {
            return OBJECT_MAPPER.readValue(json, STRING_LIST).stream()
                .filter(value -> value != null && !value.isBlank())
                .map(String::strip)
                .toList();
        } catch (Exception ignored) {
            return List.of();
        }
    }

    private static String message(VisionAnalysisStatus status) {
        return switch (status) {
            case SUCCEEDED -> "已生成画面说明";
            case EMPTY -> "未生成有效画面说明";
            case FAILED -> "视觉分析失败，不影响转写和学习笔记";
            case SKIPPED -> "已跳过视觉分析";
            case DISABLED -> "视觉分析暂未启用";
            case PENDING -> "视觉分析待生成";
        };
    }

    private static String nullToEmpty(String value) {
        return value == null ? "" : value;
    }
}
