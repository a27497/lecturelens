package com.example.courselingo.learning;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.CALLS_REAL_METHODS;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.baomidou.mybatisplus.core.conditions.Wrapper;
import com.example.courselingo.learning.domain.LearningPackage;
import com.example.courselingo.learning.mapper.LearningPackageMapper;
import java.time.LocalDateTime;
import org.junit.jupiter.api.Test;

class LearningPackageMapperTest {

    @Test
    void mapperCanInsertLearningPackage() {
        LearningPackageMapper mapper = mock(LearningPackageMapper.class);
        LearningPackage entity = learningPackage("task_1", 42L, "zh-CN", "Title");
        when(mapper.insert(entity)).thenReturn(1);

        int inserted = mapper.insert(entity);

        assertThat(inserted).isEqualTo(1);
        verify(mapper).insert(entity);
    }

    @Test
    void mapperQueryDeleteAndCountAreScopedByTaskUserAndTargetLanguage() {
        LearningPackageMapper mapper = mock(LearningPackageMapper.class, CALLS_REAL_METHODS);
        LearningPackage entity = learningPackage("task_1", 42L, "zh-CN", "Title");
        when(mapper.selectOne(any(Wrapper.class))).thenReturn(entity);
        when(mapper.delete(any(Wrapper.class))).thenReturn(1);
        when(mapper.selectCount(any(Wrapper.class))).thenReturn(1L);

        assertThat(mapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN")).isSameAs(entity);
        assertThat(mapper.deleteByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN")).isEqualTo(1);
        assertThat(mapper.countByTaskIdAndLanguage("task_1", 42L, "zh-CN")).isEqualTo(1L);

        verify(mapper).selectOne(any(Wrapper.class));
        verify(mapper).delete(any(Wrapper.class));
        verify(mapper).selectCount(any(Wrapper.class));
    }

    private static LearningPackage learningPackage(String taskId, Long userId, String targetLanguage, String title) {
        LearningPackage entity = new LearningPackage();
        entity.setId(1L);
        entity.setTaskId(taskId);
        entity.setUserId(userId);
        entity.setSourceLanguage("en");
        entity.setTargetLanguage(targetLanguage);
        entity.setTitle(title);
        entity.setSummary("Summary");
        entity.setKeyPointsJson("[{\"index\":1,\"text\":\"Point\"}]");
        entity.setGlossaryJson("[]");
        entity.setQaJson("[]");
        entity.setProvider("fake");
        entity.setSchemaVersion("learning-package.v1");
        entity.setCreatedAt(LocalDateTime.parse("2026-06-28T10:00:00"));
        entity.setUpdatedAt(LocalDateTime.parse("2026-06-28T10:00:00"));
        return entity;
    }
}
