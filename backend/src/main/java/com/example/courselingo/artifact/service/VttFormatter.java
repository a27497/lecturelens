package com.example.courselingo.artifact.service;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.util.Comparator;
import java.util.List;
import org.springframework.stereotype.Component;

@Component
public class VttFormatter {

    private static final long MILLIS_PER_HOUR = 3_600_000L;
    private static final long MILLIS_PER_MINUTE = 60_000L;
    private static final long MILLIS_PER_SECOND = 1_000L;

    public String format(List<VttCue> cues) {
        if (cues == null || cues.isEmpty()) {
            throw validationFailure("VTT subtitles are required");
        }
        List<VttCue> sortedCues = cues.stream()
            .sorted(Comparator.comparingInt(VttCue::segmentIndex))
            .toList();
        StringBuilder builder = new StringBuilder("WEBVTT\n\n");
        for (VttCue cue : sortedCues) {
            String text = validateAndNormalizeText(cue);
            builder.append(formatTime(cue.startMillis()))
                .append(" --> ")
                .append(formatTime(cue.endMillis()))
                .append('\n')
                .append(text)
                .append("\n\n");
        }
        return builder.toString();
    }

    private String validateAndNormalizeText(VttCue cue) {
        if (cue == null) {
            throw validationFailure("VTT subtitle cue is required");
        }
        if (cue.startMillis() < 0 || cue.endMillis() < cue.startMillis()) {
            throw validationFailure("VTT subtitle time range is invalid");
        }
        String text = normalizeText(cue.text());
        if (text.isBlank()) {
            throw validationFailure("VTT subtitle text is required");
        }
        if (ArtifactSensitiveDataValidator.containsSensitiveData(text)) {
            throw validationFailure("VTT subtitle text is invalid");
        }
        return text.replace("-->", "-- >");
    }

    private String normalizeText(String value) {
        if (value == null) {
            return "";
        }
        StringBuilder builder = new StringBuilder();
        boolean previousSpace = false;
        for (int i = 0; i < value.length(); i++) {
            char current = value.charAt(i);
            boolean asSpace = Character.isWhitespace(current) || Character.isISOControl(current);
            if (asSpace) {
                if (!previousSpace) {
                    builder.append(' ');
                    previousSpace = true;
                }
            } else {
                builder.append(current);
                previousSpace = false;
            }
        }
        return builder.toString().trim();
    }

    private String formatTime(long millis) {
        long hours = millis / MILLIS_PER_HOUR;
        long remainder = millis % MILLIS_PER_HOUR;
        long minutes = remainder / MILLIS_PER_MINUTE;
        remainder %= MILLIS_PER_MINUTE;
        long seconds = remainder / MILLIS_PER_SECOND;
        long milliseconds = remainder % MILLIS_PER_SECOND;
        return "%02d:%02d:%02d.%03d".formatted(hours, minutes, seconds, milliseconds);
    }

    private BusinessException validationFailure(String message) {
        return new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, message);
    }
}
