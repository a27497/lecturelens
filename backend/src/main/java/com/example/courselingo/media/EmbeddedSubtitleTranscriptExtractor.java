package com.example.courselingo.media;

import com.example.courselingo.ai.asr.AsrTextNormalizer;
import com.example.courselingo.ai.asr.TranscribedSegment;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.stereotype.Service;

@Service
public class EmbeddedSubtitleTranscriptExtractor {

    private static final Set<String> SUPPORTED_CODECS = Set.of("mov_text", "subrip", "srt", "webvtt");
    private static final Pattern TIMING = Pattern.compile(
        "(?m)^(?:(\\d{1,2}):)?(\\d{2}):(\\d{2})[.,](\\d{3})\\s+-->\\s+"
            + "(?:(\\d{1,2}):)?(\\d{2}):(\\d{2})[.,](\\d{3})(?:[ \\t]+.*)?$"
    );

    private final FfmpegProperties ffmpeg;
    private final FfmpegProcessExecutor executor;
    private final EmbeddedSubtitleTranscriptProperties properties;
    private final ObjectMapper objectMapper;

    public EmbeddedSubtitleTranscriptExtractor(
        FfmpegProperties ffmpeg,
        FfmpegProcessExecutor executor,
        EmbeddedSubtitleTranscriptProperties properties,
        ObjectMapper objectMapper
    ) {
        this.ffmpeg = ffmpeg;
        this.executor = executor;
        this.properties = properties;
        this.objectMapper = objectMapper;
    }

    public Optional<EmbeddedSubtitleTranscript> extract(
        Path video,
        String requestedLanguage,
        long durationMillis
    ) {
        if (!properties.embeddedSubtitleFirst() || video == null || !Files.isRegularFile(video) || durationMillis <= 0L) {
            return Optional.empty();
        }
        try {
            Optional<Track> selected = tracks(video).stream()
                .filter(track -> languageMatches(requestedLanguage, track.language()))
                .min(Comparator.comparingInt(Track::streamIndex));
            if (selected.isEmpty()) {
                return Optional.empty();
            }
            return convertAndParse(video, selected.get(), requestedLanguage, durationMillis);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            return Optional.empty();
        } catch (IOException | RuntimeException exception) {
            return Optional.empty();
        }
    }

    private List<Track> tracks(Path video) throws IOException, InterruptedException {
        FfmpegProcessResult result = executor.execute(List.of(
            ffmpeg.ffprobeExecutable(), "-v", "error", "-print_format", "json", "-show_streams", video.toString()
        ), boundedTimeout());
        if (result.timedOut() || result.exitCode() != 0) {
            return List.of();
        }
        JsonNode streams = objectMapper.readTree(result.stdout()).path("streams");
        List<Track> tracks = new ArrayList<>();
        if (streams.isArray()) {
            for (JsonNode stream : streams) {
                String codec = stream.path("codec_name").asText("").toLowerCase(Locale.ROOT);
                if ("subtitle".equals(stream.path("codec_type").asText()) && SUPPORTED_CODECS.contains(codec)) {
                    tracks.add(new Track(
                        stream.path("index").asInt(-1),
                        codec,
                        stream.path("tags").path("language").asText("auto")
                    ));
                }
            }
        }
        return tracks.stream().filter(track -> track.streamIndex() >= 0).toList();
    }

    private Optional<EmbeddedSubtitleTranscript> convertAndParse(
        Path video,
        Track track,
        String requestedLanguage,
        long durationMillis
    ) throws IOException, InterruptedException {
        Path temporary = Files.createTempFile("lecturelens-embedded-subtitle-", ".vtt");
        try {
            FfmpegProcessResult result = executor.execute(List.of(
                ffmpeg.executable(), "-y", "-v", "error", "-i", video.toString(),
                "-map", "0:" + track.streamIndex(), "-c:s", "webvtt", "-f", "webvtt", temporary.toString()
            ), boundedTimeout());
            if (result.timedOut() || result.exitCode() != 0 || !Files.isRegularFile(temporary) || Files.size(temporary) == 0L) {
                return Optional.empty();
            }
            List<TranscribedSegment> segments = clipToMediaTimeline(
                parseWebVtt(Files.readString(temporary, StandardCharsets.UTF_8), requestedLanguage),
                durationMillis
            );
            int minimumCues = Math.max(
                properties.getMinimumCues(),
                (int) Math.min(20L, Math.max(0L, durationMillis / 60_000L))
            );
            if (segments.size() < minimumCues || segments.size() > properties.getMaximumCues()) {
                return Optional.empty();
            }
            double coverage = coverage(segments, durationMillis);
            if (coverage < properties.getMinimumCoverage()) {
                return Optional.empty();
            }
            String language = "auto".equalsIgnoreCase(requestedLanguage) ? normalizeLanguage(track.language()) : requestedLanguage;
            List<TranscribedSegment> courseTimeline = compactTimeline(
                segments,
                properties.getSegmentDuration(),
                language
            );
            return Optional.of(new EmbeddedSubtitleTranscript(language, courseTimeline, coverage, track.streamIndex()));
        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    static List<TranscribedSegment> parseWebVtt(String content, String language) {
        String normalized = content == null ? "" : content.replace("\uFEFF", "").replace("\r\n", "\n").replace('\r', '\n');
        Matcher matcher = TIMING.matcher(normalized);
        List<TranscribedSegment> segments = new ArrayList<>();
        while (matcher.find()) {
            long start = millis(matcher, 1);
            long end = millis(matcher, 5);
            int textStart = matcher.end();
            int nextBlank = normalized.indexOf("\n\n", textStart);
            String text = normalized.substring(textStart, nextBlank < 0 ? normalized.length() : nextBlank)
                .replaceAll("<[^>]+>", " ");
            text = AsrTextNormalizer.normalize(text, language);
            if (end > start && !text.isBlank()) {
                segments.add(new TranscribedSegment(segments.size(), start, end, text));
            }
        }
        return List.copyOf(segments);
    }

    static List<TranscribedSegment> compactTimeline(
        List<TranscribedSegment> cues,
        Duration segmentDuration,
        String language
    ) {
        if (cues == null || cues.isEmpty()) {
            return List.of();
        }
        long windowMillis = Math.max(5_000L, segmentDuration == null ? 60_000L : segmentDuration.toMillis());
        List<TranscribedSegment> compacted = new ArrayList<>();
        long currentWindow = -1L;
        long start = 0L;
        long end = 0L;
        StringBuilder text = new StringBuilder();
        for (TranscribedSegment cue : cues) {
            long cueWindow = Math.max(0L, cue.startMillis()) / windowMillis;
            if (currentWindow >= 0L && cueWindow != currentWindow) {
                addCompacted(compacted, start, end, text, language);
                text.setLength(0);
            }
            if (text.isEmpty()) {
                currentWindow = cueWindow;
                start = cue.startMillis();
            }
            end = Math.max(end, cue.endMillis());
            if (!cue.text().isBlank()) {
                if (!text.isEmpty()) {
                    text.append(' ');
                }
                text.append(cue.text().strip());
            }
        }
        addCompacted(compacted, start, end, text, language);
        return List.copyOf(compacted);
    }

    private static void addCompacted(
        List<TranscribedSegment> compacted,
        long start,
        long end,
        StringBuilder text,
        String language
    ) {
        String normalized = AsrTextNormalizer.normalize(text.toString(), language);
        if (end > start && !normalized.isBlank()) {
            compacted.add(new TranscribedSegment(compacted.size(), start, end, normalized));
        }
    }

    private static long millis(Matcher matcher, int group) {
        long hours = matcher.group(group) == null ? 0L : Long.parseLong(matcher.group(group));
        long minutes = Long.parseLong(matcher.group(group + 1));
        long seconds = Long.parseLong(matcher.group(group + 2));
        long millis = Long.parseLong(matcher.group(group + 3));
        return ((hours * 60L + minutes) * 60L + seconds) * 1000L + millis;
    }

    static List<TranscribedSegment> clipToMediaTimeline(
        List<TranscribedSegment> segments,
        long durationMillis
    ) {
        if (segments == null || segments.isEmpty() || durationMillis <= 0L) {
            return List.of();
        }
        List<TranscribedSegment> clipped = new ArrayList<>();
        segments.stream()
            .filter(java.util.Objects::nonNull)
            .sorted(java.util.Comparator.comparingLong(TranscribedSegment::startMillis)
                .thenComparingLong(TranscribedSegment::endMillis))
            .forEach(segment -> {
                long start = Math.max(0L, Math.min(durationMillis, segment.startMillis()));
                long end = Math.max(0L, Math.min(durationMillis, segment.endMillis()));
                String text = segment.text() == null ? "" : segment.text().strip();
                if (end > start && !text.isBlank()) {
                    clipped.add(new TranscribedSegment(clipped.size(), start, end, text));
                }
            });
        return List.copyOf(clipped);
    }

    static double coverage(List<TranscribedSegment> segments, long durationMillis) {
        List<TranscribedSegment> clipped = clipToMediaTimeline(segments, durationMillis);
        if (clipped.isEmpty()) {
            return 0.0d;
        }
        long coveredMillis = 0L;
        long intervalStart = clipped.getFirst().startMillis();
        long intervalEnd = clipped.getFirst().endMillis();
        for (int index = 1; index < clipped.size(); index++) {
            TranscribedSegment segment = clipped.get(index);
            if (segment.startMillis() <= intervalEnd) {
                intervalEnd = Math.max(intervalEnd, segment.endMillis());
                continue;
            }
            coveredMillis += intervalEnd - intervalStart;
            intervalStart = segment.startMillis();
            intervalEnd = segment.endMillis();
        }
        coveredMillis += intervalEnd - intervalStart;
        return Math.min(1.0d, coveredMillis / (double) durationMillis);
    }

    private Duration boundedTimeout() {
        return Duration.ofSeconds(Math.min(120L, ffmpeg.timeoutSeconds()));
    }

    private static boolean languageMatches(String requested, String actual) {
        String wanted = normalizeLanguage(requested);
        String found = normalizeLanguage(actual);
        return "auto".equals(wanted) || wanted.equals(found)
            || (wanted.startsWith("en") && found.startsWith("en"))
            || (wanted.startsWith("zh") && found.startsWith("zh"));
    }

    private static String normalizeLanguage(String value) {
        String normalized = value == null ? "auto" : value.strip().replace('_', '-').toLowerCase(Locale.ROOT);
        return switch (normalized) {
            case "eng" -> "en";
            case "chi", "zho" -> "zh";
            default -> normalized.isBlank() || "und".equals(normalized) ? "auto" : normalized;
        };
    }

    private record Track(int streamIndex, String codec, String language) {
    }
}
