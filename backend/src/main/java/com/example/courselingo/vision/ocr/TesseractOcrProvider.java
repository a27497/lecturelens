package com.example.courselingo.vision.ocr;

import com.example.courselingo.common.logging.SafeLogSanitizer;
import java.io.IOException;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

public class TesseractOcrProvider implements OcrProvider {

    private static final String PROVIDER = "tesseract";

    private final VisionOcrProperties properties;
    private final OcrProcessExecutor processExecutor;

    TesseractOcrProvider(VisionOcrProperties properties, OcrProcessExecutor processExecutor) {
        this.properties = properties == null ? new VisionOcrProperties() : properties;
        this.processExecutor = processExecutor;
    }

    @Override
    public OcrResult recognize(OcrRequest request) {
        if (request == null || request.imageFile() == null) {
            return failed("OCR_INPUT_INVALID", "OCR image is unavailable", null, 0L);
        }
        Instant startedAt = Instant.now();
        Path imageFile = request.imageFile();
        Duration timeout = Duration.ofSeconds(properties.getTimeoutSeconds());
        List<String> command = List.of(
            properties.getCommand(),
            imageFile.toString(),
            "stdout",
            "-l",
            properties.getLanguage(),
            "--psm",
            "6",
            "tsv"
        );
        try {
            OcrProcessResult result = processExecutor.execute(command, timeout);
            long durationMillis = Duration.between(startedAt, Instant.now()).toMillis();
            if (result.timedOut()) {
                return failed("OCR_TIMEOUT", "OCR timed out", imageFile, durationMillis);
            }
            if (result.exitCode() != 0) {
                return failed("OCR_PROVIDER_FAILED", result.stderr(), imageFile, durationMillis);
            }
            ParsedTsv parsed = parseTsv(result.stdout());
            if (parsed.text().isBlank()) {
                return OcrResult.empty(PROVIDER, properties.getLanguage(), durationMillis);
            }
            return new OcrResult(
                OcrStatus.SUCCEEDED,
                parsed.text(),
                parsed.confidence(),
                PROVIDER,
                properties.getLanguage(),
                durationMillis,
                null,
                null
            );
        } catch (IOException exception) {
            return failed("OCR_PROVIDER_UNAVAILABLE", exception.getMessage(), imageFile, elapsed(startedAt));
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            return failed("OCR_INTERRUPTED", exception.getMessage(), imageFile, elapsed(startedAt));
        }
    }

    private static ParsedTsv parseTsv(String stdout) {
        if (stdout == null || stdout.isBlank()) {
            return new ParsedTsv("", null);
        }
        String[] lines = stdout.split("\\R");
        if (lines.length < 2) {
            return new ParsedTsv(stdout.strip(), null);
        }
        String[] headings = lines[0].split("\\t", -1);
        int textIndex = indexOf(headings, "text");
        int confidenceIndex = indexOf(headings, "conf");
        if (textIndex < 0) {
            return new ParsedTsv(stdout.strip(), null);
        }
        List<String> words = new ArrayList<>();
        double confidenceSum = 0.0;
        int confidenceCount = 0;
        for (int index = 1; index < lines.length; index++) {
            String[] columns = lines[index].split("\\t", -1);
            if (columns.length <= textIndex) {
                continue;
            }
            String text = columns[textIndex].strip();
            if (text.isBlank()) {
                continue;
            }
            words.add(text);
            if (confidenceIndex >= 0 && columns.length > confidenceIndex) {
                double confidence = parseConfidence(columns[confidenceIndex]);
                if (confidence >= 0) {
                    confidenceSum += confidence;
                    confidenceCount++;
                }
            }
        }
        Double confidence = confidenceCount == 0
            ? null
            : BigDecimal.valueOf(confidenceSum / confidenceCount / 100.0)
                .setScale(4, RoundingMode.HALF_UP)
                .doubleValue();
        return new ParsedTsv(String.join(" ", words).strip(), confidence);
    }

    private static int indexOf(String[] columns, String name) {
        for (int index = 0; index < columns.length; index++) {
            if (name.equalsIgnoreCase(columns[index])) {
                return index;
            }
        }
        return -1;
    }

    private static double parseConfidence(String value) {
        try {
            return Double.parseDouble(value);
        } catch (NumberFormatException ex) {
            return -1.0;
        }
    }

    private OcrResult failed(String code, String message, Path imageFile, long durationMillis) {
        return new OcrResult(
            OcrStatus.FAILED,
            "",
            null,
            PROVIDER,
            properties.getLanguage(),
            durationMillis,
            code,
            sanitize(message, imageFile)
        );
    }

    private static String sanitize(String message, Path imageFile) {
        String sanitized = SafeLogSanitizer.sanitizeAndLimit(message == null ? "OCR failed" : message);
        if (imageFile != null) {
            String path = imageFile.toString();
            if (!path.isBlank()) {
                sanitized = sanitized.replace(path, "[redacted-path]");
            }
            Path fileName = imageFile.getFileName();
            if (fileName != null) {
                sanitized = sanitized.replace(fileName.toString(), "[redacted-file]");
            }
        }
        return sanitized;
    }

    private static long elapsed(Instant startedAt) {
        return Duration.between(startedAt, Instant.now()).toMillis();
    }

    private record ParsedTsv(String text, Double confidence) {
    }
}
