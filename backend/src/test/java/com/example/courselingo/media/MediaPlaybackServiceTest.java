package com.example.courselingo.media;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.when;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.infrastructure.JwtAccessTokenProperties;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.upload.entity.UploadSession;
import com.example.courselingo.upload.mapper.UploadSessionMapper;
import com.example.courselingo.upload.service.ChunkStagingPathResolver;
import com.example.courselingo.upload.service.ChunkStagingProperties;
import java.io.InputStream;
import java.lang.reflect.RecordComponent;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Arrays;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class MediaPlaybackServiceTest {

    private static final Clock FIXED_CLOCK = Clock.fixed(Instant.parse("2026-07-04T12:00:00Z"), ZoneOffset.UTC);
    private static final String SECRET = "dev-only-change-me-access-secret-at-least-32-characters";
    private static final byte[] VIDEO_BYTES = "0123456789abcdefghijklmnopqrstuvwxyz".getBytes(StandardCharsets.UTF_8);

    @TempDir
    private Path tempDir;

    @Mock
    private CurrentUserService currentUserService;

    @Mock
    private UploadSessionMapper uploadSessionMapper;

    @Mock
    private AnalysisTaskMapper analysisTaskMapper;

    private MediaPlaybackTokenService tokenService;
    private MediaPlaybackServiceImpl service;

    @BeforeEach
    void setUp() {
        ChunkStagingPathResolver pathResolver = new ChunkStagingPathResolver(new ChunkStagingProperties(tempDir));
        tokenService = new MediaPlaybackTokenService(
            new MediaPlaybackProperties(15),
            new JwtAccessTokenProperties(SECRET, 3600),
            FIXED_CLOCK
        );
        service = new MediaPlaybackServiceImpl(
            currentUserService,
            uploadSessionMapper,
            analysisTaskMapper,
            pathResolver,
            tokenService
        );
        lenient().when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
    }

    @Test
    void ownerCanRequestPlaybackTokenForCompletedUploadWithoutExposingStorageDetails() throws Exception {
        UploadSession upload = uploadedSession("up_abc123", 42L, "mp4");
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(upload);
        writeSource(upload);

        PlaybackTokenResponse response = service.requestUploadPlaybackToken("Bearer access-token", "up_abc123");

        assertThat(response.token()).isNotBlank();
        assertThat(response.expiresAt()).isEqualTo(Instant.parse("2026-07-04T12:15:00Z"));
        assertThat(response.playbackUrl()).startsWith("/api/media/uploads/up_abc123/stream?token=");
        assertThat(response.getClass().getRecordComponents())
            .extracting(RecordComponent::getName)
            .containsExactly("token", "expiresAt", "playbackUrl");
        assertThat(response.playbackUrl()).doesNotContain("raw/42");
        assertThat(response.playbackUrl()).doesNotContain(tempDir.toString());
    }

    @Test
    void unfinishedUploadCannotRequestPlaybackToken() {
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L))
            .thenReturn(uploadSession("up_abc123", 42L, "UPLOADING", "mp4"));

        assertThatThrownBy(() -> service.requestUploadPlaybackToken("Bearer access-token", "up_abc123"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_SESSION_STATUS_INVALID);
    }

    @Test
    void userCannotRequestPlaybackTokenForAnotherUsersUpload() {
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(null);

        assertThatThrownBy(() -> service.requestUploadPlaybackToken("Bearer access-token", "up_abc123"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.MEDIA_PLAYBACK_FORBIDDEN);
    }

    @Test
    void ownerCanRequestPlaybackTokenForOwnTaskWithoutKnowingUploadId() throws Exception {
        AnalysisTask task = task("task_abc123", "up_abc123", 42L);
        UploadSession upload = uploadedSession("up_abc123", 42L, "webm");
        when(analysisTaskMapper.selectByIdAndUserId("task_abc123", 42L)).thenReturn(task);
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(upload);
        writeSource(upload);

        PlaybackTokenResponse response = service.requestTaskPlaybackToken("Bearer access-token", "task_abc123");

        assertThat(response.playbackUrl()).startsWith("/api/media/uploads/up_abc123/stream?token=");
        assertThat(response.playbackUrl()).doesNotContain("task_abc123");
    }

    @Test
    void userCannotRequestPlaybackTokenForAnotherUsersTask() {
        when(analysisTaskMapper.selectByIdAndUserId("task_abc123", 42L)).thenReturn(null);

        assertThatThrownBy(() -> service.requestTaskPlaybackToken("Bearer access-token", "task_abc123"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_NOT_FOUND);
    }

    @Test
    void streamRejectsMissingToken() {
        assertThatThrownBy(() -> service.stream("up_abc123", null, null))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.MEDIA_PLAYBACK_TOKEN_INVALID);
    }

    @Test
    void streamRejectsExpiredToken() {
        MediaPlaybackTokenService expiredTokenService = new MediaPlaybackTokenService(
            new MediaPlaybackProperties(15),
            new JwtAccessTokenProperties(SECRET, 3600),
            Clock.fixed(Instant.parse("2026-07-04T11:00:00Z"), ZoneOffset.UTC)
        );
        String expiredToken = expiredTokenService.issue(42L, "up_abc123").token();

        assertThatThrownBy(() -> service.stream("up_abc123", expiredToken, null))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.MEDIA_PLAYBACK_TOKEN_EXPIRED);
    }

    @Test
    void streamRejectsTamperedToken() {
        String token = tokenService.issue(42L, "up_abc123").token() + "x";

        assertThatThrownBy(() -> service.stream("up_abc123", token, null))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.MEDIA_PLAYBACK_TOKEN_INVALID);
    }

    @Test
    void streamRejectsUploadIdThatDiffersFromTokenUploadId() {
        String token = tokenService.issue(42L, "up_abc123").token();

        assertThatThrownBy(() -> service.stream("up_other", token, null))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.MEDIA_PLAYBACK_TOKEN_INVALID);
    }

    @Test
    void rangeRequestReturnsPartialContentWithoutReadingWholeFileIntoMemory() throws Exception {
        UploadSession upload = uploadedSession("up_abc123", 42L, "mp4");
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(upload);
        writeSource(upload);
        String token = tokenService.issue(42L, "up_abc123").token();

        MediaStreamResponse response = service.stream("up_abc123", token, "bytes=0-9");

        assertThat(response.status()).isEqualTo(206);
        assertThat(response.contentType()).isEqualTo("video/mp4");
        assertThat(response.contentLength()).isEqualTo(10);
        assertThat(response.contentRange()).isEqualTo("bytes 0-9/" + VIDEO_BYTES.length);
        try (InputStream inputStream = response.inputStream()) {
            assertThat(inputStream.readAllBytes()).isEqualTo(Arrays.copyOfRange(VIDEO_BYTES, 0, 10));
        }
    }

    @Test
    void requestWithoutRangeReturnsWholeStream() throws Exception {
        UploadSession upload = uploadedSession("up_abc123", 42L, "mkv");
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(upload);
        writeSource(upload);
        String token = tokenService.issue(42L, "up_abc123").token();

        MediaStreamResponse response = service.stream("up_abc123", token, null);

        assertThat(response.status()).isEqualTo(200);
        assertThat(response.contentType()).isEqualTo("video/x-matroska");
        assertThat(response.contentLength()).isEqualTo(VIDEO_BYTES.length);
        assertThat(response.contentRange()).isNull();
        try (InputStream inputStream = response.inputStream()) {
            assertThat(inputStream.readAllBytes()).isEqualTo(VIDEO_BYTES);
        }
    }

    @Test
    void invalidRangeReturnsRangeNotSatisfiable() throws Exception {
        UploadSession upload = uploadedSession("up_abc123", 42L, "mp4");
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(upload);
        writeSource(upload);
        String token = tokenService.issue(42L, "up_abc123").token();

        assertThatThrownBy(() -> service.stream("up_abc123", token, "bytes=999-1000"))
            .isInstanceOf(MediaRangeNotSatisfiableException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.MEDIA_RANGE_NOT_SATISFIABLE);
    }

    private void writeSource(UploadSession upload) throws Exception {
        Path source = tempDir.resolve(upload.getUserId().toString())
            .resolve(upload.getId())
            .resolve("assembled")
            .resolve("source." + upload.getExt());
        Files.createDirectories(source.getParent());
        Files.write(source, VIDEO_BYTES);
    }

    private static AnalysisTask task(String taskId, String uploadId, Long userId) {
        AnalysisTask task = new AnalysisTask();
        task.setId(taskId);
        task.setUploadId(uploadId);
        task.setUserId(userId);
        return task;
    }

    private static UploadSession uploadedSession(String uploadId, Long userId, String ext) {
        return uploadSession(uploadId, userId, "STORED", ext);
    }

    private static UploadSession uploadSession(String uploadId, Long userId, String status, String ext) {
        UploadSession session = new UploadSession();
        session.setId(uploadId);
        session.setUserId(userId);
        session.setStatus(status);
        session.setExt(ext);
        session.setSizeBytes((long) VIDEO_BYTES.length);
        session.setObjectKey("raw/" + userId + "/" + uploadId + "/source." + ext);
        return session;
    }
}
