package com.example.courselingo.media;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.when;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.upload.entity.UploadSession;
import com.example.courselingo.upload.mapper.UploadSessionMapper;
import com.example.courselingo.upload.service.ChunkStagingPathResolver;
import com.example.courselingo.upload.service.ChunkStagingProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class EmbeddedSubtitleServiceTest {

    private static final byte[] VIDEO_BYTES = "video-with-subtitles".getBytes(StandardCharsets.UTF_8);

    @TempDir
    private Path tempDir;

    @Mock
    private CurrentUserService currentUserService;

    @Mock
    private UploadSessionMapper uploadSessionMapper;

    @Mock
    private AnalysisTaskMapper analysisTaskMapper;

    private RecordingFfmpegProcessExecutor executor;
    private EmbeddedSubtitleServiceImpl service;

    @BeforeEach
    void setUp() {
        executor = new RecordingFfmpegProcessExecutor();
        service = new EmbeddedSubtitleServiceImpl(
            currentUserService,
            uploadSessionMapper,
            analysisTaskMapper,
            new ChunkStagingPathResolver(new ChunkStagingProperties(tempDir.resolve("chunks"))),
            executor,
            new FfmpegProperties(),
            new ObjectMapper(),
            tempDir.resolve("embedded-subtitles")
        );
        lenient().when(currentUserService.currentUser("Bearer access-token"))
            .thenReturn(new CurrentUserResponse(42L, "demo@example.com", "ACTIVE"));
    }

    @Test
    void probeUploadReturnsNotFoundWhenVideoHasNoSubtitleStreams() throws Exception {
        UploadSession upload = uploadedSession("up_abc123", 42L, "mp4");
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(upload);
        writeSource(upload);
        executor.nextProbeJson = """
            {"streams":[{"index":0,"codec_type":"video","codec_name":"h264"}]}
            """;

        EmbeddedSubtitleProbeResponse response = service.probeUpload("Bearer access-token", "up_abc123");

        assertThat(response.status()).isEqualTo(EmbeddedSubtitleStatus.NOT_FOUND);
        assertThat(response.tracks()).isEmpty();
        assertThat(response.selectedStreamIndex()).isNull();
    }

    @Test
    void probeUploadSelectsDefaultSupportedSubtitleTrack() throws Exception {
        UploadSession upload = uploadedSession("up_abc123", 42L, "mkv");
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(upload);
        writeSource(upload);
        executor.nextProbeJson = """
            {
              "streams": [
                {"index":0,"codec_type":"video","codec_name":"h264"},
                {"index":2,"codec_type":"subtitle","codec_name":"ass","tags":{"language":"eng","title":"English"},"disposition":{"default":0}},
                {"index":3,"codec_type":"subtitle","codec_name":"subrip","tags":{"language":"zho","title":"Chinese"},"disposition":{"default":1}}
              ]
            }
            """;

        EmbeddedSubtitleProbeResponse response = service.probeUpload("Bearer access-token", "up_abc123");

        assertThat(response.status()).isEqualTo(EmbeddedSubtitleStatus.FOUND);
        assertThat(response.selectedStreamIndex()).isEqualTo(3);
        assertThat(response.tracks()).extracting(EmbeddedSubtitleTrackResponse::streamIndex)
            .containsExactly(2, 3);
        assertThat(response.tracks()).allMatch(EmbeddedSubtitleTrackResponse::supported);
    }

    @Test
    void probeUploadMarksImageSubtitleTracksUnsupported() throws Exception {
        UploadSession upload = uploadedSession("up_abc123", 42L, "mkv");
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(upload);
        writeSource(upload);
        executor.nextProbeJson = """
            {"streams":[{"index":4,"codec_type":"subtitle","codec_name":"hdmv_pgs_subtitle","tags":{"language":"eng"}}]}
            """;

        EmbeddedSubtitleProbeResponse response = service.probeUpload("Bearer access-token", "up_abc123");

        assertThat(response.status()).isEqualTo(EmbeddedSubtitleStatus.UNSUPPORTED);
        assertThat(response.selectedStreamIndex()).isNull();
        assertThat(response.tracks()).singleElement()
            .satisfies(track -> {
                assertThat(track.supported()).isFalse();
                assertThat(track.unsupportedReason()).contains("图片字幕");
            });
    }

    @Test
    void downloadUploadSubtitleExtractsSupportedTrackAsWebVttAndCachesIt() throws Exception {
        UploadSession upload = uploadedSession("up_abc123", 42L, "mkv");
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(upload);
        writeSource(upload);
        executor.nextProbeJson = """
            {"streams":[{"index":3,"codec_type":"subtitle","codec_name":"subrip","tags":{"language":"zho"},"disposition":{"default":1}}]}
            """;

        EmbeddedSubtitleFileResponse response = service.downloadUpload("Bearer access-token", "up_abc123", 3);
        EmbeddedSubtitleFileResponse cached = service.downloadUpload("Bearer access-token", "up_abc123", 3);

        assertThat(response.contentType()).isEqualTo("text/vtt;charset=utf-8");
        assertThat(response.bytes()).asString(StandardCharsets.UTF_8)
            .contains("WEBVTT")
            .contains("内嵌字幕");
        assertThat(cached.bytes()).isEqualTo(response.bytes());
        assertThat(executor.extractCommandCount).isEqualTo(1);
    }

    @Test
    void downloadRejectsUnsupportedSubtitleTrack() throws Exception {
        UploadSession upload = uploadedSession("up_abc123", 42L, "mkv");
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(upload);
        writeSource(upload);
        executor.nextProbeJson = """
            {"streams":[{"index":4,"codec_type":"subtitle","codec_name":"dvd_subtitle"}]}
            """;

        assertThatThrownBy(() -> service.downloadUpload("Bearer access-token", "up_abc123", 4))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.MEDIA_SUBTITLE_UNSUPPORTED);
    }

    @Test
    void unfinishedUploadCannotProbeEmbeddedSubtitles() {
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L))
            .thenReturn(uploadSession("up_abc123", 42L, "UPLOADING", "mp4"));

        assertThatThrownBy(() -> service.probeUpload("Bearer access-token", "up_abc123"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.UPLOAD_SESSION_STATUS_INVALID);
    }

    @Test
    void taskProbeRequiresTaskOwnerAndResolvesTaskUpload() throws Exception {
        AnalysisTask task = task("task_abc123", "up_abc123", 42L);
        UploadSession upload = uploadedSession("up_abc123", 42L, "mp4");
        when(analysisTaskMapper.selectByIdAndUserId("task_abc123", 42L)).thenReturn(task);
        when(uploadSessionMapper.selectByIdAndUserId("up_abc123", 42L)).thenReturn(upload);
        writeSource(upload);
        executor.nextProbeJson = """
            {"streams":[{"index":1,"codec_type":"subtitle","codec_name":"mov_text","tags":{"language":"zh-CN"},"disposition":{"default":0}}]}
            """;

        EmbeddedSubtitleProbeResponse response = service.probeTask("Bearer access-token", "task_abc123");

        assertThat(response.status()).isEqualTo(EmbeddedSubtitleStatus.FOUND);
        assertThat(response.selectedStreamIndex()).isEqualTo(1);
    }

    @Test
    void userCannotProbeAnotherUsersTask() {
        when(analysisTaskMapper.selectByIdAndUserId("task_abc123", 42L)).thenReturn(null);

        assertThatThrownBy(() -> service.probeTask("Bearer access-token", "task_abc123"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_NOT_FOUND);
    }

    private void writeSource(UploadSession upload) throws IOException {
        Path source = tempDir.resolve("chunks")
            .resolve(upload.getUserId().toString())
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
        return session;
    }

    private static final class RecordingFfmpegProcessExecutor implements FfmpegProcessExecutor {

        private String nextProbeJson = "{\"streams\":[]}";
        private int extractCommandCount;

        @Override
        public FfmpegProcessResult execute(List<String> command, Duration timeout) throws IOException {
            if (command.get(0).contains("ffprobe")) {
                return FfmpegProcessResult.success(nextProbeJson, "");
            }
            extractCommandCount++;
            Path output = Path.of(command.get(command.size() - 1));
            Files.createDirectories(output.getParent());
            Files.writeString(
                output,
                "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n内嵌字幕\n",
                StandardCharsets.UTF_8
            );
            return FfmpegProcessResult.success("", "");
        }
    }
}
