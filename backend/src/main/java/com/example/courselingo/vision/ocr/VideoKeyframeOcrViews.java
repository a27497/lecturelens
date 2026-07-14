package com.example.courselingo.vision.ocr;

import java.util.Collection;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

public final class VideoKeyframeOcrViews {

    private VideoKeyframeOcrViews() {
    }

    public static Map<Long, VideoKeyframeOcrView> byKeyframeId(Collection<VideoKeyframeOcr> rows) {
        if (rows == null || rows.isEmpty()) {
            return Map.of();
        }
        return rows.stream().collect(Collectors.toMap(
            VideoKeyframeOcr::getKeyframeId,
            VideoKeyframeOcrViews::toView,
            (left, right) -> left
        ));
    }

    public static VideoKeyframeOcrView missing(boolean enabled) {
        if (!enabled) {
            return new VideoKeyframeOcrView(
                OcrStatus.DISABLED.name(),
                "",
                "",
                "",
                null,
                false,
                "OCR 暂未启用"
            );
        }
        return new VideoKeyframeOcrView(
            OcrStatus.PENDING.name(),
            "",
            "",
            "",
            null,
            false,
            "OCR 识别中"
        );
    }

    public static Function<Long, VideoKeyframeOcrView> resolver(
        Map<Long, VideoKeyframeOcrView> views,
        boolean enabled
    ) {
        return keyframeId -> views.getOrDefault(keyframeId, missing(enabled));
    }

    private static VideoKeyframeOcrView toView(VideoKeyframeOcr row) {
        OcrStatus status = parseStatus(row.getStatus());
        return new VideoKeyframeOcrView(
            status.name(),
            status == OcrStatus.SUCCEEDED ? nullToEmpty(row.getOcrText()) : "",
            nullToEmpty(row.getProvider()),
            nullToEmpty(row.getLanguageHint()),
            row.getConfidence(),
            Boolean.TRUE.equals(row.getTextTruncated()),
            message(status)
        );
    }

    private static OcrStatus parseStatus(String status) {
        try {
            return OcrStatus.valueOf(status);
        } catch (RuntimeException ex) {
            return OcrStatus.PENDING;
        }
    }

    private static String message(OcrStatus status) {
        return switch (status) {
            case SUCCEEDED -> "";
            case EMPTY -> "未识别到文字";
            case FAILED -> "OCR 失败，不影响转写和学习笔记";
            case SKIPPED -> "已跳过 OCR";
            case DISABLED -> "OCR 暂未启用";
            case PENDING -> "OCR 识别中";
        };
    }

    private static String nullToEmpty(String value) {
        return value == null ? "" : value;
    }
}
