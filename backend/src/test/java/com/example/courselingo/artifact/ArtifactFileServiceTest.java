package com.example.courselingo.artifact;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.artifact.domain.ArtifactFile;
import com.example.courselingo.artifact.domain.ArtifactType;
import com.example.courselingo.artifact.dto.ArtifactFileView;
import com.example.courselingo.artifact.mapper.ArtifactFileMapper;
import com.example.courselingo.artifact.service.ArtifactFileQueryServiceImpl;
import com.example.courselingo.artifact.service.ArtifactFileServiceImpl;
import com.example.courselingo.artifact.service.ArtifactObjectKeyGenerator;
import com.example.courselingo.artifact.service.SaveArtifactFileCommand;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.storage.StorageService;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.transaction.annotation.Transactional;

@ExtendWith(MockitoExtension.class)
class ArtifactFileServiceTest {

    private static final Clock FIXED_CLOCK = Clock.fixed(
        Instant.parse("2026-06-28T10:00:00Z"),
        ZoneOffset.UTC
    );

    @Mock
    private ArtifactFileMapper mapper;

    private FakeStorageService fakeStorage;
    private ArtifactFileServiceImpl service;
    private ArtifactFileQueryServiceImpl queryService;

    @BeforeEach
    void setUp() {
        fakeStorage = new FakeStorageService();
        service = new ArtifactFileServiceImpl(
            mapper,
            fakeStorage,
            FIXED_CLOCK,
            new ArtifactObjectKeyGenerator()
        );
        queryService = new ArtifactFileQueryServiceImpl(mapper);
    }

    @Test
    void saveArtifactFileWritesToFakeStorageAndPersistsMetadata() {
        when(mapper.insert(any(ArtifactFile.class))).thenReturn(1);

        ArtifactFileView view = service.saveArtifactFile(command());

        assertThat(fakeStorage.puts).hasSize(1);
        FakeStorageService.PutCall put = fakeStorage.puts.getFirst();
        assertThat(put.objectKey()).startsWith("artifacts/42/task_1/SRT/zh-CN/");
        assertThat(put.objectKey()).endsWith("-lesson.srt");
        assertSafeObjectKey(put.objectKey());
        assertThat(put.contentType()).isEqualTo("application/x-subrip");
        assertThat(put.bytes()).isEqualTo("hello world".getBytes(java.nio.charset.StandardCharsets.UTF_8));

        ArtifactFile inserted = captureInserted();
        assertThat(inserted.getTaskId()).isEqualTo("task_1");
        assertThat(inserted.getUserId()).isEqualTo(42L);
        assertThat(inserted.getArtifactType()).isEqualTo("SRT");
        assertThat(inserted.getLanguage()).isEqualTo("zh-CN");
        assertThat(inserted.getFileName()).isEqualTo("lesson.srt");
        assertThat(inserted.getContentType()).isEqualTo("application/x-subrip");
        assertThat(inserted.getStorageBackend()).isEqualTo("MINIO");
        assertThat(inserted.getObjectKey()).isEqualTo(put.objectKey());
        assertThat(inserted.getSizeBytes()).isEqualTo(11L);
        assertThat(inserted.getSha256()).isEqualTo(sha256("hello world".getBytes(java.nio.charset.StandardCharsets.UTF_8)));
        assertThat(inserted.getCreatedAt()).isEqualTo(now());
        assertThat(inserted.getUpdatedAt()).isEqualTo(now());
        assertThat(view.taskId()).isEqualTo("task_1");
        assertThat(view.fileName()).isEqualTo("lesson.srt");
        assertThat(view.sha256()).isEqualTo(inserted.getSha256());
        assertThat(view.getClass().getRecordComponents())
            .extracting(java.lang.reflect.RecordComponent::getName)
            .doesNotContain("userId", "objectKey");
    }

    @Test
    void saveArtifactFileRequiresTransaction() throws NoSuchMethodException {
        Transactional annotation = ArtifactFileServiceImpl.class
            .getMethod("saveArtifactFile", SaveArtifactFileCommand.class)
            .getAnnotation(Transactional.class);

        assertThat(annotation).isNotNull();
    }

    @Test
    void queryReturnsOwnerScopedViewsWithoutUserIdOrObjectKey() {
        when(mapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            artifact("task_1", 42L, ArtifactType.SRT, "zh-CN", "lesson.srt"),
            artifact("task_1", 42L, ArtifactType.VTT, "en", "lesson.vtt")
        ));
        when(mapper.selectByScope("task_1", 42L, "SRT", "zh-CN"))
            .thenReturn(artifact("task_1", 42L, ArtifactType.SRT, "zh-CN", "lesson.srt"));
        when(mapper.countByScope("task_1", 42L, "SRT", "zh-CN")).thenReturn(1L);

        List<ArtifactFileView> views = queryService.listByTaskId("task_1", 42L);
        Optional<ArtifactFileView> single = queryService.getByTaskTypeAndLanguage("task_1", 42L, ArtifactType.SRT, "zh-CN");

        assertThat(views).extracting(ArtifactFileView::artifactType).containsExactly(ArtifactType.SRT, ArtifactType.VTT);
        assertThat(single).isPresent();
        assertThat(single.get().language()).isEqualTo("zh-CN");
        assertThat(queryService.countByScope("task_1", 42L, ArtifactType.SRT, "zh-CN")).isEqualTo(1L);
        assertThat(single.get().getClass().getRecordComponents())
            .extracting(java.lang.reflect.RecordComponent::getName)
            .doesNotContain("userId", "objectKey");
    }

    @Test
    void overwriteIsScopedAndDeletesOldObjectBestEffort() {
        ArtifactFile old = artifact("task_1", 42L, ArtifactType.SRT, "zh-CN", "old.srt");
        old.setObjectKey("artifacts/42/task_1/SRT/zh-CN/old.srt");
        when(mapper.selectByScope("task_1", 42L, "SRT", "zh-CN")).thenReturn(old);
        when(mapper.insert(any(ArtifactFile.class))).thenReturn(1);

        service.saveArtifactFile(command());

        verify(mapper).deleteByScope("task_1", 42L, "SRT", "zh-CN");
        verify(mapper, never()).deleteByScope("task_1", 43L, "SRT", "zh-CN");
        verify(mapper, never()).deleteByScope("task_1", 42L, "SRT", "en");
        verify(mapper, never()).deleteByScope("task_1", 42L, "VTT", "zh-CN");
        assertThat(fakeStorage.deletes).containsExactly("artifacts/42/task_1/SRT/zh-CN/old.srt");
    }

    @Test
    void overwriteContinuesWhenOldObjectDeleteFailsWithoutPointingToOldObject() {
        ArtifactFile old = artifact("task_1", 42L, ArtifactType.SRT, "zh-CN", "old.srt");
        old.setObjectKey("artifacts/42/task_1/SRT/zh-CN/old.srt");
        when(mapper.selectByScope("task_1", 42L, "SRT", "zh-CN")).thenReturn(old);
        when(mapper.insert(any(ArtifactFile.class))).thenReturn(1);
        fakeStorage.failDelete = true;

        ArtifactFileView view = service.saveArtifactFile(command());

        assertThat(view.fileName()).isEqualTo("lesson.srt");
        assertThat(captureInserted().getObjectKey()).isNotEqualTo(old.getObjectKey());
    }

    @Test
    void deleteArtifactIsScopedAndDeletesStorageObjectBestEffort() {
        ArtifactFile old = artifact("task_1", 42L, ArtifactType.JSON, "en", "lesson.json");
        when(mapper.selectByScope("task_1", 42L, "JSON", "en")).thenReturn(old);
        when(mapper.deleteByScope("task_1", 42L, "JSON", "en")).thenReturn(1);

        int deleted = service.deleteArtifact("task_1", 42L, ArtifactType.JSON, "en");

        assertThat(deleted).isEqualTo(1);
        verify(mapper).deleteByScope("task_1", 42L, "JSON", "en");
        assertThat(fakeStorage.deletes).containsExactly(old.getObjectKey());
    }

    @Test
    void storageWriteFailureDoesNotWriteDatabase() {
        fakeStorage.failPut = true;

        assertThatThrownBy(() -> service.saveArtifactFile(command()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.STORAGE_OPERATION_FAILED);

        verify(mapper, never()).deleteByScope(any(), any(), any(), any());
        verify(mapper, never()).insert(any(ArtifactFile.class));
    }

    @Test
    void databaseInsertFailureCleansNewObjectBestEffort() {
        when(mapper.insert(any(ArtifactFile.class))).thenReturn(0);

        assertThatThrownBy(() -> service.saveArtifactFile(command()))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_INTERNAL_ERROR);

        assertThat(fakeStorage.deletes).hasSize(1);
        assertThat(fakeStorage.deletes.getFirst()).isEqualTo(fakeStorage.puts.getFirst().objectKey());
    }

    @Test
    void invalidCommandFieldsFailBeforeStorageAndDatabase() {
        assertValidationFailure(() -> service.saveArtifactFile(null));
        assertValidationFailure(() -> service.saveArtifactFile(command("", 42L, ArtifactType.SRT, "zh-CN", "lesson.srt", "text/plain", bytes())));
        assertValidationFailure(() -> service.saveArtifactFile(command("task_1", null, ArtifactType.SRT, "zh-CN", "lesson.srt", "text/plain", bytes())));
        assertValidationFailure(() -> service.saveArtifactFile(command("task_1", 42L, null, "zh-CN", "lesson.srt", "text/plain", bytes())));
        assertValidationFailure(() -> service.saveArtifactFile(command("task_1", 42L, ArtifactType.SRT, " ", "lesson.srt", "text/plain", bytes())));
        assertValidationFailure(() -> service.saveArtifactFile(command("task_1", 42L, ArtifactType.SRT, "x".repeat(33), "lesson.srt", "text/plain", bytes())));
        assertValidationFailure(() -> service.saveArtifactFile(command("task_1", 42L, ArtifactType.SRT, "zh-CN", " ", "text/plain", bytes())));
        assertValidationFailure(() -> service.saveArtifactFile(command("task_1", 42L, ArtifactType.SRT, "zh-CN", "x".repeat(256), "text/plain", bytes())));
        assertValidationFailure(() -> service.saveArtifactFile(command("task_1", 42L, ArtifactType.SRT, "zh-CN", "../lesson.srt", "text/plain", bytes())));
        assertValidationFailure(() -> service.saveArtifactFile(command("task_1", 42L, ArtifactType.SRT, "zh-CN", "..\\lesson.srt", "text/plain", bytes())));
        assertValidationFailure(() -> service.saveArtifactFile(command("task_1", 42L, ArtifactType.SRT, "zh-CN", "C:\\Users\\demo\\lesson.srt", "text/plain", bytes())));
        assertValidationFailure(() -> service.saveArtifactFile(command("task_1", 42L, ArtifactType.SRT, "zh-CN", "lesson.srt", " ", bytes())));
        assertValidationFailure(() -> service.saveArtifactFile(command("task_1", 42L, ArtifactType.SRT, "zh-CN", "lesson.srt", "x".repeat(129), bytes())));
        assertValidationFailure(() -> service.saveArtifactFile(command("task_1", 42L, ArtifactType.SRT, "zh-CN", "lesson.srt", "text/plain", null)));
        assertValidationFailure(() -> service.saveArtifactFile(command("task_1", 42L, ArtifactType.SRT, "zh-CN", "lesson.srt", "text/plain", new byte[0])));
        assertValidationFailure(() -> service.saveArtifactFile(command("task_1", 42L, ArtifactType.SRT, "zh-CN", "lesson.srt", "text/plain", new byte[10 * 1024 * 1024 + 1])));

        assertThat(fakeStorage.puts).isEmpty();
        verify(mapper, never()).insert(any(ArtifactFile.class));
    }

    @Test
    void validationErrorsAndObjectKeysDoNotLeakSecretsOrLocalPaths() {
        assertThatThrownBy(() -> service.saveArtifactFile(command(
            "task_1",
            42L,
            ArtifactType.SRT,
            "zh-CN",
            "Authorization Bearer token secret api key C:\\Users\\demo\\lesson.srt",
            "text/plain",
            bytes()
        )))
            .isInstanceOf(BusinessException.class)
            .satisfies(error -> assertSafe(error.getMessage()));
    }

    @Test
    void boundariesDoNotCallAiRunnerMqSubtitleLearningOrFrontend() throws Exception {
        String source = Files.readString(Path.of(
            "src/main/java/com/example/courselingo/artifact/service/ArtifactFileServiceImpl.java"
        ));

        assertThat(source)
            .contains("StorageService")
            .doesNotContain("OpenAiCompatible")
            .doesNotContain("LangChain4j")
            .doesNotContain("Ffmpeg")
            .doesNotContain("SpeechToTextProvider")
            .doesNotContain("SiliconFlow")
            .doesNotContain("MockAsr")
            .doesNotContain("AnalysisTaskRunner")
            .doesNotContain("RocketMQ")
            .doesNotContain("Subtitle")
            .doesNotContain("LearningPackage")
            .doesNotContain("ai_call_record");
    }

    private ArtifactFile captureInserted() {
        ArgumentCaptor<ArtifactFile> captor = ArgumentCaptor.forClass(ArtifactFile.class);
        verify(mapper).insert(captor.capture());
        return captor.getValue();
    }

    private static SaveArtifactFileCommand command() {
        return command("task_1", 42L, ArtifactType.SRT, "zh-CN", "lesson.srt", "application/x-subrip", bytes());
    }

    private static SaveArtifactFileCommand command(
        String taskId,
        Long userId,
        ArtifactType artifactType,
        String language,
        String fileName,
        String contentType,
        byte[] contentBytes
    ) {
        return new SaveArtifactFileCommand(taskId, userId, artifactType, language, fileName, contentType, contentBytes);
    }

    private static byte[] bytes() {
        return "hello world".getBytes(java.nio.charset.StandardCharsets.UTF_8);
    }

    private static ArtifactFile artifact(
        String taskId,
        Long userId,
        ArtifactType artifactType,
        String language,
        String fileName
    ) {
        ArtifactFile entity = new ArtifactFile();
        entity.setId(1L);
        entity.setTaskId(taskId);
        entity.setUserId(userId);
        entity.setArtifactType(artifactType.name());
        entity.setLanguage(language);
        entity.setFileName(fileName);
        entity.setContentType("text/plain");
        entity.setStorageBackend("MINIO");
        entity.setObjectKey("artifacts/%d/%s/%s/%s/%s".formatted(userId, taskId, artifactType.name(), language, fileName));
        entity.setSizeBytes(11L);
        entity.setSha256(sha256(bytes()));
        entity.setCreatedAt(now());
        entity.setUpdatedAt(now());
        return entity;
    }

    private static String sha256(byte[] content) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(content));
        } catch (java.security.NoSuchAlgorithmException ex) {
            throw new IllegalStateException(ex);
        }
    }

    private static LocalDateTime now() {
        return LocalDateTime.ofInstant(FIXED_CLOCK.instant(), FIXED_CLOCK.getZone());
    }

    private static void assertValidationFailure(ThrowingCallable callable) {
        assertThatThrownBy(callable::call)
            .isInstanceOf(BusinessException.class)
            .satisfies(error -> {
                assertThat(((BusinessException) error).errorCode()).isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);
                assertSafe(error.getMessage());
            });
    }

    private static void assertSafe(String message) {
        assertThat(message).doesNotContain("C:\\", "/home/", "/Users/");
        assertThat(message.toLowerCase()).doesNotContain("token", "secret", "api key", "authorization");
    }

    private static void assertSafeObjectKey(String objectKey) {
        assertThat(objectKey).doesNotContain("\\", "..", "C:", "/home/", "/Users/");
        assertThat(objectKey.toLowerCase()).doesNotContain("token", "secret", "api_key", "api-key", "authorization");
    }

    @FunctionalInterface
    private interface ThrowingCallable {
        void call();
    }

    private static final class FakeStorageService implements StorageService {

        private final List<PutCall> puts = new ArrayList<>();
        private final List<String> deletes = new ArrayList<>();
        private boolean failPut;
        private boolean failDelete;

        @Override
        public void putObject(String objectKey, Path sourceFile, long sizeBytes, String contentType) {
            if (failPut) {
                throw new BusinessException(ErrorCode.STORAGE_OPERATION_FAILED, "fake storage write failed");
            }
            try {
                byte[] bytes = Files.readAllBytes(sourceFile);
                puts.add(new PutCall(objectKey, bytes, sizeBytes, contentType));
            } catch (IOException ex) {
                throw new BusinessException(ErrorCode.STORAGE_OPERATION_FAILED, "fake storage read failed", ex);
            }
        }

        @Override
        public boolean objectExists(String objectKey) {
            return puts.stream().anyMatch(put -> put.objectKey().equals(objectKey));
        }

        @Override
        public InputStream openObject(String objectKey) {
            return puts.stream()
                .filter(put -> put.objectKey().equals(objectKey))
                .findFirst()
                .map(put -> new ByteArrayInputStream(put.bytes()))
                .orElseThrow(() -> new BusinessException(ErrorCode.ARTIFACT_NOT_FOUND));
        }

        @Override
        public void deleteObject(String objectKey) {
            deletes.add(objectKey);
            if (failDelete) {
                throw new BusinessException(ErrorCode.STORAGE_OPERATION_FAILED, "fake storage delete failed");
            }
        }

        private record PutCall(
            String objectKey,
            byte[] bytes,
            long sizeBytes,
            String contentType
        ) {
        }
    }
}
