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
import java.io.IOException;
import java.io.InputStream;
import java.nio.channels.Channels;
import java.nio.channels.SeekableByteChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Locale;
import java.util.Objects;
import java.util.regex.Pattern;
import org.springframework.stereotype.Service;

@Service
public class MediaPlaybackServiceImpl implements MediaPlaybackService {

    private static final String UPLOADED_STATUS = "UPLOADED";
    private static final String STORED_STATUS = "STORED";
    private static final Pattern UPLOAD_ID_PATTERN = Pattern.compile("^up_[A-Za-z0-9_-]+$");
    private static final Pattern TASK_ID_PATTERN = Pattern.compile("^task_[A-Za-z0-9_-]+$");
    private static final Pattern SAFE_EXTENSION = Pattern.compile("^[A-Za-z0-9][A-Za-z0-9_-]{0,15}$");

    private final CurrentUserService currentUserService;
    private final UploadSessionMapper uploadSessionMapper;
    private final AnalysisTaskMapper analysisTaskMapper;
    private final ChunkStagingPathResolver pathResolver;
    private final MediaPlaybackTokenService tokenService;

    public MediaPlaybackServiceImpl(
        CurrentUserService currentUserService,
        UploadSessionMapper uploadSessionMapper,
        AnalysisTaskMapper analysisTaskMapper,
        ChunkStagingPathResolver pathResolver,
        MediaPlaybackTokenService tokenService
    ) {
        this.currentUserService = currentUserService;
        this.uploadSessionMapper = uploadSessionMapper;
        this.analysisTaskMapper = analysisTaskMapper;
        this.pathResolver = pathResolver;
        this.tokenService = tokenService;
    }

    @Override
    public PlaybackTokenResponse requestUploadPlaybackToken(String authorizationHeader, String uploadId) {
        String normalizedUploadId = validateUploadId(uploadId);
        CurrentUserResponse currentUser = currentUserService.currentUser(authorizationHeader);
        UploadSession upload = uploadSessionMapper.selectByIdAndUserId(normalizedUploadId, currentUser.userId());
        if (upload == null) {
            throw new BusinessException(ErrorCode.MEDIA_PLAYBACK_FORBIDDEN);
        }
        ensurePlayable(upload);
        return issueResponse(upload.getUserId(), upload.getId());
    }

    @Override
    public PlaybackTokenResponse requestTaskPlaybackToken(String authorizationHeader, String taskId) {
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
        ensurePlayable(upload);
        return issueResponse(upload.getUserId(), upload.getId());
    }

    @Override
    public MediaStreamResponse stream(String uploadId, String token, String rangeHeader) {
        String normalizedUploadId = validateUploadId(uploadId);
        MediaPlaybackTokenClaims claims = tokenService.verify(token);
        if (!Objects.equals(normalizedUploadId, claims.uploadId())) {
            throw new BusinessException(ErrorCode.MEDIA_PLAYBACK_TOKEN_INVALID);
        }
        UploadSession upload = uploadSessionMapper.selectByIdAndUserId(normalizedUploadId, claims.userId());
        if (upload == null) {
            throw new BusinessException(ErrorCode.MEDIA_PLAYBACK_FORBIDDEN);
        }
        ensureUploaded(upload);
        Path source = sourcePath(upload);
        long sizeBytes = fileSize(source);
        Range range = parseRange(rangeHeader, sizeBytes);
        return new MediaStreamResponse(
            range.partial() ? 206 : 200,
            contentType(upload.getExt()),
            range.length(),
            range.partial() ? "bytes " + range.start() + "-" + range.end() + "/" + sizeBytes : null,
            openBoundedStream(source, range.start(), range.length())
        );
    }

    private PlaybackTokenResponse issueResponse(Long userId, String uploadId) {
        MediaPlaybackToken token = tokenService.issue(userId, uploadId);
        return new PlaybackTokenResponse(
            token.token(),
            token.expiresAt(),
            "/api/media/uploads/" + uploadId + "/stream?token=" + token.token()
        );
    }

    private void ensurePlayable(UploadSession upload) {
        ensureUploaded(upload);
        Path source = sourcePath(upload);
        if (!Files.isRegularFile(source)) {
            throw new BusinessException(ErrorCode.MEDIA_SOURCE_NOT_FOUND);
        }
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

    private long fileSize(Path source) {
        try {
            if (!Files.isRegularFile(source)) {
                throw new BusinessException(ErrorCode.MEDIA_SOURCE_NOT_FOUND);
            }
            return Files.size(source);
        } catch (BusinessException exception) {
            throw exception;
        } catch (IOException exception) {
            throw new BusinessException(ErrorCode.MEDIA_SOURCE_NOT_FOUND, exception);
        }
    }

    private InputStream openBoundedStream(Path source, long offset, long length) {
        try {
            SeekableByteChannel channel = Files.newByteChannel(source, StandardOpenOption.READ);
            channel.position(offset);
            return new BoundedInputStream(Channels.newInputStream(channel), length);
        } catch (IOException exception) {
            throw new BusinessException(ErrorCode.MEDIA_SOURCE_NOT_FOUND, exception);
        }
    }

    private Range parseRange(String rangeHeader, long sizeBytes) {
        if (rangeHeader == null || rangeHeader.isBlank()) {
            return new Range(0, sizeBytes - 1, sizeBytes, false);
        }
        if (!rangeHeader.startsWith("bytes=") || rangeHeader.contains(",")) {
            throw new MediaRangeNotSatisfiableException(sizeBytes);
        }
        String spec = rangeHeader.substring("bytes=".length()).trim();
        int dashIndex = spec.indexOf('-');
        if (dashIndex < 0) {
            throw new MediaRangeNotSatisfiableException(sizeBytes);
        }
        String startPart = spec.substring(0, dashIndex).trim();
        String endPart = spec.substring(dashIndex + 1).trim();
        try {
            long start;
            long end;
            if (startPart.isEmpty()) {
                long suffixLength = Long.parseLong(endPart);
                if (suffixLength <= 0) {
                    throw new NumberFormatException("invalid suffix range");
                }
                start = Math.max(0, sizeBytes - suffixLength);
                end = sizeBytes - 1;
            } else {
                start = Long.parseLong(startPart);
                end = endPart.isEmpty() ? sizeBytes - 1 : Long.parseLong(endPart);
            }
            if (sizeBytes <= 0 || start < 0 || end < start || start >= sizeBytes) {
                throw new MediaRangeNotSatisfiableException(sizeBytes);
            }
            end = Math.min(end, sizeBytes - 1);
            return new Range(start, end, end - start + 1, true);
        } catch (MediaRangeNotSatisfiableException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw new MediaRangeNotSatisfiableException(sizeBytes);
        }
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

    private static String contentType(String ext) {
        if (ext == null) {
            return "application/octet-stream";
        }
        return switch (ext.toLowerCase(Locale.ROOT)) {
            case "mp4" -> "video/mp4";
            case "webm" -> "video/webm";
            case "mov" -> "video/quicktime";
            case "mkv" -> "video/x-matroska";
            default -> "application/octet-stream";
        };
    }

    private record Range(long start, long end, long length, boolean partial) {
    }

    private static final class BoundedInputStream extends InputStream {

        private final InputStream delegate;
        private long remaining;

        private BoundedInputStream(InputStream delegate, long length) {
            this.delegate = delegate;
            this.remaining = length;
        }

        @Override
        public int read() throws IOException {
            if (remaining <= 0) {
                return -1;
            }
            int value = delegate.read();
            if (value != -1) {
                remaining--;
            }
            return value;
        }

        @Override
        public int read(byte[] b, int off, int len) throws IOException {
            if (remaining <= 0) {
                return -1;
            }
            int maxLength = (int) Math.min(len, remaining);
            int count = delegate.read(b, off, maxLength);
            if (count > 0) {
                remaining -= count;
            }
            return count;
        }

        @Override
        public void close() throws IOException {
            delegate.close();
        }
    }
}
