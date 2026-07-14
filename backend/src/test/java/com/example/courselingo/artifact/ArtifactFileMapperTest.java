package com.example.courselingo.artifact;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.CALLS_REAL_METHODS;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.baomidou.mybatisplus.core.conditions.Wrapper;
import com.example.courselingo.artifact.domain.ArtifactFile;
import com.example.courselingo.artifact.domain.ArtifactType;
import com.example.courselingo.artifact.mapper.ArtifactFileMapper;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.Test;

class ArtifactFileMapperTest {

    @Test
    void mapperCanInsertArtifactFile() {
        ArtifactFileMapper mapper = mock(ArtifactFileMapper.class);
        ArtifactFile entity = artifact("task_1", 42L, ArtifactType.SRT, "zh-CN", "lesson.srt");
        when(mapper.insert(entity)).thenReturn(1);

        int inserted = mapper.insert(entity);

        assertThat(inserted).isEqualTo(1);
        verify(mapper).insert(entity);
    }

    @Test
    void mapperQueriesByTaskAndUserInStableOrder() {
        ArtifactFileMapper mapper = mock(ArtifactFileMapper.class, CALLS_REAL_METHODS);
        ArtifactFile srt = artifact("task_1", 42L, ArtifactType.SRT, "zh-CN", "lesson.srt");
        ArtifactFile vtt = artifact("task_1", 42L, ArtifactType.VTT, "zh-CN", "lesson.vtt");
        when(mapper.selectList(any(Wrapper.class))).thenReturn(List.of(srt, vtt));

        List<ArtifactFile> artifacts = mapper.selectByTaskIdAndUserId("task_1", 42L);

        assertThat(artifacts).extracting(ArtifactFile::getArtifactType).containsExactly("SRT", "VTT");
        verify(mapper).selectList(any(Wrapper.class));
    }

    @Test
    void mapperQueryDeleteAndCountAreScopedByTaskUserTypeAndLanguage() {
        ArtifactFileMapper mapper = mock(ArtifactFileMapper.class, CALLS_REAL_METHODS);
        ArtifactFile entity = artifact("task_1", 42L, ArtifactType.MARKDOWN, "en", "lesson.md");
        when(mapper.selectOne(any(Wrapper.class))).thenReturn(entity);
        when(mapper.delete(any(Wrapper.class))).thenReturn(1);
        when(mapper.selectCount(any(Wrapper.class))).thenReturn(1L);

        assertThat(mapper.selectByScope("task_1", 42L, ArtifactType.MARKDOWN.name(), "en")).isSameAs(entity);
        assertThat(mapper.deleteByScope("task_1", 42L, ArtifactType.MARKDOWN.name(), "en")).isEqualTo(1);
        assertThat(mapper.countByScope("task_1", 42L, ArtifactType.MARKDOWN.name(), "en")).isEqualTo(1L);

        verify(mapper).selectOne(any(Wrapper.class));
        verify(mapper).delete(any(Wrapper.class));
        verify(mapper).selectCount(any(Wrapper.class));
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
        entity.setObjectKey("artifacts/%d/%s/%s/%s/%s".formatted(
            userId,
            taskId,
            artifactType.name(),
            language,
            fileName
        ));
        entity.setSizeBytes(11L);
        entity.setSha256("a".repeat(64));
        entity.setCreatedAt(LocalDateTime.parse("2026-06-28T10:00:00"));
        entity.setUpdatedAt(LocalDateTime.parse("2026-06-28T10:00:00"));
        return entity;
    }
}
