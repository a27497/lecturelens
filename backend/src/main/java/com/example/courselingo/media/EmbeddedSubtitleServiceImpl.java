package com.example.courselingo.media;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.upload.entity.UploadSession;
import com.example.courselingo.upload.mapper.UploadSessionMapper;
import com.example.courselingo.upload.service.ChunkStagingPathResolver;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Pattern;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class EmbeddedSubtitleServiceImpl implements EmbeddedSubtitleService {

    private static final String UPLOADED_STATUS = "UPLOADED";
    private static final String STORED_STATUS = "STORED";
    private static final Pattern UPLOAD_ID_PATTERN = Pattern.compile("^up_[A-Za-z0-9_-]+$");
    private static final Pattern TASK_ID_PATTERN = Pattern.compile("^task_[A-Za-z0-9_-]+$");
    private static final Pattern SAFE_EXTENSION = Pattern.compile("^[A-Za-z0-9][A-Za-z0-9_-]{0,15}$");
    private static final Set<String> SUPPORTED_CODECS = Set.of("subrip", "srt", "ass", "ssa", "mov_text", "webvtt");
    private static final Set<String> IMAGE_SUBTITLE_CODECS = Set.of(
        "hdmv_pgs_subtitle",
        "dvd_subtitle",
        "dvb_subtitle",
        "xsub"
    );
    private static final Set<String> PREFERRED_LANGUAGES = Set.of("zh", "zh-cn", "zh-hans", "chi", "zho", "eng", "en");

    private final CurrentUserService currentUserService;
    private final UploadSessionMapper uploadSessionMapper;
    private final AnalysisTaskMapper analysisTaskMapper;
    private final ChunkStagingPathResolver pathResolver;
    private final FfmpegProcessExecutor processExecutor;
    private final FfmpegProperties ffmpegProperties;
    private final ObjectMapper objectMapper;
    private final Path cacheRoot;

    @Autowired
    public EmbeddedSubtitleServiceImpl(
        CurrentUserService currentUserService,
        UploadSessionMapper uploadSessionMapper,
        AnalysisTaskMapper analysisTaskMapper,
        ChunkStagingPathResolver pathResolver,
        FfmpegProcessExecutor processExecutor,
        FfmpegProperties ffmpegProperties,
        ObjectMapper objectMapper
    ) {
        this(
            currentUserService,
            uploadSessionMapper,
            analysisTaskMapper,
            pathResolver,
            processExecutor,
            ffmpegProperties,
            objectMapper,
            Path.of("storage", "embedded-subtitles")
        );
    }

    EmbeddedSubtitleServiceImpl(
        CurrentUserService currentUserService,
        UploadSessionMapper uploadSessionMapper,
        AnalysisTaskMapper analysisTaskMapper,
        ChunkStagingPathResolver pathResolver,
        FfmpegProcessExecutor processExecutor,
        FfmpegProperties ffmpegProperties,
        ObjectMapper objectMapper,
        Path cacheRoot
    ) {
        this.currentUserService = currentUserService;
        this.uploadSessionMapper = uploadSessionMapper;
        this.analysisTaskMapper = analysisTaskMapper;
        this.pathResolver = pathResolver;
        this.processExecutor = processExecutor;
        this.ffmpegProperties = ffmpegProperties;
        this.objectMapper = objectMapper;
        this.cacheRoot = cacheRoot.toAbsolutePath().normalize();
    }

    @Override
    public EmbeddedSubtitleProbeResponse probeUpload(String authorizationHeader, String uploadId) {
        UploadSession upload = resolveUploadForCurrentUser(authorizationHeader, uploadId);
        return probe(upload);
    }

    @Override
    public EmbeddedSubtitleProbeResponse probeTask(String authorizationHeader, String taskId) {
        UploadSession upload = resolveTaskUploadForCurrentUser(authorizationHeader, taskId);
        return probe(upload);
    }

    @Override
    public EmbeddedSubtitleFileResponse downloadUpload(String authorizationHeader, String uploadId, int streamIndex) {
        UploadSession upload = resolveUploadForCurrentUser(authorizationHeader, uploadId);
        return download(upload, streamIndex);
    }

    @Override
    public EmbeddedSubtitleFileResponse downloadTask(String authorizationHeader, String taskId, int streamIndex) {
        UploadSession upload = resolveTaskUploadForCurrentUser(authorizationHeader, taskId);
        return download(upload, streamIndex);
    }

    private EmbeddedSubtitleProbeResponse probe(UploadSession upload) {
        Path source = sourcePath(upload);
        ensureSourceExists(source);
        FfmpegProcessResult result;
        try {
            result = processExecutor.execute(
                List.of(
                    ffprobeExecutable(),
                    "-v",
                    "error",
                    "-print_format",
                    "json",
                    "-show_streams",
                    source.toString()
                ),
                ffmpegProperties.timeout()
            );
        } catch (IOException exception) {
            throw new BusinessException(ErrorCode.MEDIA_SUBTITLE_PROBE_FAILED, exception);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new BusinessException(ErrorCode.MEDIA_SUBTITLE_PROBE_FAILED, exception);
        }
        if (result.timedOut() || result.exitCode() != 0) {
            throw new BusinessException(ErrorCode.MEDIA_SUBTITLE_PROBE_FAILED);
        }
        List<EmbeddedSubtitleTrackResponse> tracks = parseTracks(result.stdout());
        if (tracks.isEmpty()) {
            return new EmbeddedSubtitleProbeResponse(EmbeddedSubtitleStatus.NOT_FOUND, List.of(), null);
        }
        Optional<EmbeddedSubtitleTrackResponse> selected = selectTrack(tracks);
        if (selected.isEmpty()) {
            return new EmbeddedSubtitleProbeResponse(EmbeddedSubtitleStatus.UNSUPPORTED, tracks, null);
        }
        return new EmbeddedSubtitleProbeResponse(
            EmbeddedSubtitleStatus.FOUND,
            tracks,
            selected.get().streamIndex()
        );
    }

    private EmbeddedSubtitleFileResponse download(UploadSession upload, int streamIndex) {
        if (streamIndex < 0) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED);
        }
        Path source = sourcePath(upload);
        ensureSourceExists(source);
        EmbeddedSubtitleTrackResponse track = probe(upload).tracks().stream()
            .filter(item -> item.streamIndex() == streamIndex)
            .findFirst()
            .orElseThrow(() -> new BusinessException(ErrorCode.MEDIA_SUBTITLE_UNSUPPORTED));
        if (!track.supported()) {
            throw new BusinessException(ErrorCode.MEDIA_SUBTITLE_UNSUPPORTED);
        }

        Path cacheFile = cacheFile(upload.getId(), streamIndex);
        try {
            if (!Files.isRegularFile(cacheFile) || Files.size(cacheFile) == 0) {
                extractWebVtt(source, streamIndex, cacheFile);
            }
            return new EmbeddedSubtitleFileResponse(
                Files.readAllBytes(cacheFile),
                "text/vtt;charset=utf-8",
                "embedded-subtitle-" + streamIndex + ".vtt"
            );
        } catch (IOException exception) {
            throw new BusinessException(ErrorCode.MEDIA_SUBTITLE_EXTRACTION_FAILED, exception);
        }
    }

    private void extractWebVtt(Path source, int streamIndex, Path cacheFile) throws IOException {
        Files.createDirectories(cacheFile.getParent());
        Path tempFile = cacheFile.resolveSibling(cacheFile.getFileName() + ".tmp");
        FfmpegProcessResult result;
        try {
            result = processExecutor.execute(
                List.of(
                    ffmpegProperties.executable(),
                    "-y",
                    "-i",
                    source.toString(),
                    "-map",
                    "0:" + streamIndex,
                    "-c:s",
                    "webvtt",
                    tempFile.toString()
                ),
                ffmpegProperties.timeout()
            );
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new BusinessException(ErrorCode.MEDIA_SUBTITLE_EXTRACTION_FAILED, exception);
        }
        if (result.timedOut() || result.exitCode() != 0 || !Files.isRegularFile(tempFile)) {
            Files.deleteIfExists(tempFile);
            throw new BusinessException(ErrorCode.MEDIA_SUBTITLE_EXTRACTION_FAILED);
        }
        Files.move(tempFile, cacheFile, StandardCopyOption.REPLACE_EXISTING);
    }

    private List<EmbeddedSubtitleTrackResponse> parseTracks(String stdout) {
        try {
            JsonNode streams = objectMapper.readTree(stdout).path("streams");
            if (!streams.isArray()) {
                return List.of();
            }
            List<EmbeddedSubtitleTrackResponse> tracks = new ArrayList<>();
            Iterator<JsonNode> iterator = streams.elements();
            while (iterator.hasNext()) {
                JsonNode stream = iterator.next();
                if (Objects.equals("subtitle", stream.path("codec_type").asText())) {
                    tracks.add(toTrack(stream));
                }
            }
            return tracks;
        } catch (RuntimeException | IOException exception) {
            throw new BusinessException(ErrorCode.MEDIA_SUBTITLE_PROBE_FAILED, exception);
        }
    }

    private EmbeddedSubtitleTrackResponse toTrack(JsonNode stream) {
        int index = stream.path("index").asInt(-1);
        String codec = stream.path("codec_name").asText("");
        String normalizedCodec = normalize(codec);
        boolean supported = SUPPORTED_CODECS.contains(normalizedCodec);
        String unsupportedReason = "";
        if (!supported) {
            unsupportedReason = IMAGE_SUBTITLE_CODECS.contains(normalizedCodec)
                ? "图片字幕暂不支持提取为文字字幕"
                : "该字幕格式暂不支持提取为 WebVTT";
        }
        JsonNode tags = stream.path("tags");
        JsonNode disposition = stream.path("disposition");
        return new EmbeddedSubtitleTrackResponse(
            index,
            codec,
            tags.path("language").asText(""),
            tags.path("title").asText(""),
            disposition.path("default").asInt(0) == 1,
            supported,
            unsupportedReason
        );
    }

    private Optional<EmbeddedSubtitleTrackResponse> selectTrack(List<EmbeddedSubtitleTrackResponse> tracks) {
        return tracks.stream()
            .filter(EmbeddedSubtitleTrackResponse::supported)
            .min(Comparator
                .comparingInt((EmbeddedSubtitleTrackResponse track) -> track.defaultTrack() ? 0 : 1)
                .thenComparingInt(track -> PREFERRED_LANGUAGES.contains(normalize(track.language())) ? 0 : 1)
                .thenComparingInt(EmbeddedSubtitleTrackResponse::streamIndex));
    }

    private UploadSession resolveUploadForCurrentUser(String authorizationHeader, String uploadId) {
        String normalizedUploadId = validateUploadId(uploadId);
        CurrentUserResponse currentUser = currentUserService.currentUser(authorizationHeader);
        UploadSession upload = uploadSessionMapper.selectByIdAndUserId(normalizedUploadId, currentUser.userId());
        if (upload == null) {
            throw new BusinessException(ErrorCode.MEDIA_PLAYBACK_FORBIDDEN);
        }
        ensureUploaded(upload);
        return upload;
    }

    private UploadSession resolveTaskUploadForCurrentUser(String authorizationHeader, String taskId) {
        String normalizedTaskId = validateTaskId(taskId);
        CurrentUserResponse currentUser = currentUserService.currentUser(authorizationHeader);
        AnalysisTask task = analysisTaskMapper.selectByIdAndUserId(normalizedTaskId, currentUser.userId());
        if (task == null) {
            throw new BusinessException(ErrorCode.TASK_NOT_FOUND);
        }
        UploadSession upload = uploadSessionMapper.selectByIdAndUserId(task.getUploadId(), currentUser.userId());
        if (upload == null) {
            throw new BusinessException(ErrorCode.MEDIA_SOURCE_NOT_FOUND);
        }
        ensureUploaded(upload);
        return upload;
    }

    private void ensureUploaded(UploadSession upload) {
        if (!STORED_STATUS.equals(upload.getStatus()) && !UPLOADED_STATUS.equals(upload.getStatus())) {
            throw new BusinessException(ErrorCode.UPLOAD_SESSION_STATUS_INVALID);
        }
    }

    private Path sourcePath(UploadSession upload) {
        String ext = validateExtension(upload.getExt());
        return pathResolver.resolveAssembledFile(upload.getUserId(), upload.getId(), ext);
    }

    private void ensureSourceExists(Path source) {
        if (!Files.isRegularFile(source)) {
            throw new BusinessException(ErrorCode.MEDIA_SOURCE_NOT_FOUND);
        }
    }

    private Path cacheFile(String uploadId, int streamIndex) {
        Path file = cacheRoot
            .resolve(validateUploadId(uploadId))
            .resolve("track-" + streamIndex + ".vtt")
            .normalize();
        if (!file.startsWith(cacheRoot)) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED);
        }
        return file;
    }

    private String validateUploadId(String uploadId) {
        if (uploadId == null || !UPLOAD_ID_PATTERN.matcher(uploadId).matches()) {
            throw new BusinessException(ErrorCode.UPLOAD_INVALID_SESSION_ID);
        }
        return uploadId;
    }

    private String validateTaskId(String taskId) {
        if (taskId == null || !TASK_ID_PATTERN.matcher(taskId).matches()) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED);
        }
        return taskId;
    }

    private String validateExtension(String ext) {
        if (ext == null || !SAFE_EXTENSION.matcher(ext).matches()) {
            throw new BusinessException(ErrorCode.MEDIA_SOURCE_NOT_FOUND);
        }
        return ext;
    }

    private String ffprobeExecutable() {
        String executable = ffmpegProperties.executable();
        if (executable.endsWith("ffmpeg.exe")) {
            return executable.substring(0, executable.length() - "ffmpeg.exe".length()) + "ffprobe.exe";
        }
        if (executable.endsWith("ffmpeg")) {
            return executable.substring(0, executable.length() - "ffmpeg".length()) + "ffprobe";
        }
        return "ffprobe";
    }

    private static String normalize(String value) {
        return value == null ? "" : value.trim().toLowerCase(Locale.ROOT);
    }
}
