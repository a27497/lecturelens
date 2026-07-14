package com.example.courselingo.artifact;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.example.courselingo.artifact.domain.ArtifactFile;
import com.example.courselingo.artifact.service.ArtifactFileDownloadResponse;
import com.example.courselingo.artifact.service.ArtifactFileDownloadServiceImpl;
import com.example.courselingo.artifact.mapper.ArtifactFileMapper;
import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.storage.StorageService;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.InOrder;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class ArtifactFileDownloadServiceTest {

    private static final String AUTHORIZATION = "test-authorization";
    private static final String TASK_ID = "task_fixture";
    private static final String OBJECT_KEY = "fixture/artifact.vtt";
    private static final String VTT_CONTENT = "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\n你好\n";

    @Mock
    private CurrentUserService currentUserService;

    @Mock
    private AnalysisTaskMapper analysisTaskMapper;

    @Mock
    private ArtifactFileMapper artifactFileMapper;

    @Mock
    private StorageService storageService;

    private ArtifactFileDownloadServiceImpl service;

    @BeforeEach
    void setUp() {
        service = new ArtifactFileDownloadServiceImpl(
            currentUserService,
            analysisTaskMapper,
            artifactFileMapper,
            storageService
        );
    }

    @Test
    void downloadGuardsTaskBeforeArtifactAndStorageWithoutLeakingInternalFields() throws Exception {
        ArtifactFile artifact = artifact();
        when(currentUserService.currentUser(AUTHORIZATION)).thenReturn(currentUser());
        when(analysisTaskMapper.selectByIdAndUserId(TASK_ID, 42L)).thenReturn(task());
        when(artifactFileMapper.selectByScope(TASK_ID, 42L, "VTT", "zh-CN")).thenReturn(artifact);
        when(storageService.openObject(OBJECT_KEY))
            .thenReturn(new ByteArrayInputStream(VTT_CONTENT.getBytes(StandardCharsets.UTF_8)));

        ArtifactFileDownloadResponse response = service.download(AUTHORIZATION, TASK_ID, "VTT", "zh-CN");

        assertThat(response.fileName()).isEqualTo("fixture.vtt");
        assertThat(response.contentType()).isEqualTo("text/vtt; charset=utf-8");
        assertThat(response.sizeBytes()).isEqualTo(VTT_CONTENT.getBytes(StandardCharsets.UTF_8).length);
        assertThat(response.inputStream().readAllBytes()).isEqualTo(VTT_CONTENT.getBytes(StandardCharsets.UTF_8));
        assertThat(response.getClass().getRecordComponents())
            .extracting(java.lang.reflect.RecordComponent::getName)
            .doesNotContain("userId", "objectKey", "localPath");

        InOrder order = inOrder(analysisTaskMapper, artifactFileMapper, storageService);
        order.verify(analysisTaskMapper, times(1)).selectByIdAndUserId(TASK_ID, 42L);
        order.verify(artifactFileMapper, times(1)).selectByScope(TASK_ID, 42L, "VTT", "zh-CN");
        order.verify(storageService, times(1)).openObject(OBJECT_KEY);
    }

    @Test
    void downloadReturnsTaskNotFoundWhenTaskIsMissingWithoutArtifactOrStorageRead() {
        when(currentUserService.currentUser(AUTHORIZATION)).thenReturn(currentUser());

        assertThatThrownBy(() -> service.download(AUTHORIZATION, TASK_ID, "VTT", "zh-CN"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_NOT_FOUND);

        verify(analysisTaskMapper).selectByIdAndUserId(TASK_ID, 42L);
        verifyNoInteractions(artifactFileMapper, storageService);
    }

    @Test
    void downloadUsesUniformTaskNotFoundWhenOwnerGuardRejectsTask() {
        when(currentUserService.currentUser(AUTHORIZATION)).thenReturn(currentUser());

        assertThatThrownBy(() -> service.download(AUTHORIZATION, TASK_ID, "VTT", "zh-CN"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_NOT_FOUND);

        verify(analysisTaskMapper).selectByIdAndUserId(TASK_ID, 42L);
        verifyNoInteractions(artifactFileMapper, storageService);
    }

    @Test
    void downloadTreatsSoftDeletedTaskAsNotFoundWhenVisibleOwnerGuardReturnsNull() {
        when(currentUserService.currentUser(AUTHORIZATION)).thenReturn(currentUser());

        assertThatThrownBy(() -> service.download(AUTHORIZATION, TASK_ID, "VTT", "zh-CN"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.TASK_NOT_FOUND);

        verify(analysisTaskMapper).selectByIdAndUserId(TASK_ID, 42L);
        verifyNoInteractions(artifactFileMapper, storageService);
    }

    @Test
    void downloadReturnsArtifactNotFoundWhenVisibleTaskHasNoArtifactWithoutStorageRead() {
        when(currentUserService.currentUser(AUTHORIZATION)).thenReturn(currentUser());
        when(analysisTaskMapper.selectByIdAndUserId(TASK_ID, 42L)).thenReturn(task());

        assertThatThrownBy(() -> service.download(AUTHORIZATION, TASK_ID, "VTT", "zh-CN"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.ARTIFACT_NOT_FOUND);

        verify(analysisTaskMapper).selectByIdAndUserId(TASK_ID, 42L);
        verify(artifactFileMapper).selectByScope(TASK_ID, 42L, "VTT", "zh-CN");
        verifyNoInteractions(storageService);
    }

    @Test
    void downloadRejectsInvalidArtifactTypeBeforeStorageRead() {
        when(currentUserService.currentUser(AUTHORIZATION)).thenReturn(currentUser());

        assertThatThrownBy(() -> service.download(AUTHORIZATION, TASK_ID, "HTML", "zh-CN"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);

        verifyNoInteractions(analysisTaskMapper, artifactFileMapper, storageService);
    }

    @Test
    void downloadReturnsUnauthorizedBeforeTaskArtifactOrStorageRead() {
        when(currentUserService.currentUser(AUTHORIZATION))
            .thenThrow(new BusinessException(ErrorCode.COMMON_UNAUTHORIZED));

        assertThatThrownBy(() -> service.download(AUTHORIZATION, TASK_ID, "VTT", "zh-CN"))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_UNAUTHORIZED);

        verifyNoInteractions(analysisTaskMapper, artifactFileMapper, storageService);
    }

    private static CurrentUserResponse currentUser() {
        return new CurrentUserResponse(42L, "redacted", "ACTIVE");
    }

    private static AnalysisTask task() {
        AnalysisTask task = new AnalysisTask();
        task.setId(TASK_ID);
        task.setUserId(42L);
        return task;
    }

    private static ArtifactFile artifact() {
        byte[] bytes = VTT_CONTENT.getBytes(StandardCharsets.UTF_8);
        ArtifactFile artifact = new ArtifactFile();
        artifact.setTaskId(TASK_ID);
        artifact.setUserId(42L);
        artifact.setArtifactType("VTT");
        artifact.setLanguage("zh-CN");
        artifact.setFileName("fixture.vtt");
        artifact.setContentType("text/vtt; charset=utf-8");
        artifact.setStorageBackend("MINIO");
        artifact.setObjectKey(OBJECT_KEY);
        artifact.setSizeBytes((long) bytes.length);
        artifact.setSha256("fixture-sha256");
        return artifact;
    }
}
