package com.example.courselingo.subtitle;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.CALLS_REAL_METHODS;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.baomidou.mybatisplus.core.conditions.Wrapper;
import com.example.courselingo.subtitle.domain.SubtitleTranslationSegment;
import com.example.courselingo.subtitle.mapper.SubtitleTranslationSegmentMapper;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.Test;

class SubtitleTranslationMapperTest {

    @Test
    void mapperCanInsertTranslationSegment() {
        SubtitleTranslationSegmentMapper mapper = mock(SubtitleTranslationSegmentMapper.class);
        SubtitleTranslationSegment segment = segment("task_1", 42L, "zh-CN", 0, "你好");
        when(mapper.insert(segment)).thenReturn(1);

        int inserted = mapper.insert(segment);

        assertThat(inserted).isEqualTo(1);
        verify(mapper).insert(segment);
    }

    @Test
    void mapperQueriesByTaskUserAndTargetLanguageInSegmentIndexOrder() {
        SubtitleTranslationSegmentMapper mapper = mock(SubtitleTranslationSegmentMapper.class, CALLS_REAL_METHODS);
        SubtitleTranslationSegment first = segment("task_1", 42L, "zh-CN", 0, "第一");
        SubtitleTranslationSegment second = segment("task_1", 42L, "zh-CN", 1, "第二");
        when(mapper.selectList(any(Wrapper.class))).thenReturn(List.of(first, second));

        List<SubtitleTranslationSegment> segments = mapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN");

        assertThat(segments).extracting(SubtitleTranslationSegment::getSegmentIndex).containsExactly(0, 1);
        verify(mapper).selectList(any(Wrapper.class));
    }

    @Test
    void mapperDeleteAndCountAreScopedByTaskUserAndTargetLanguage() {
        SubtitleTranslationSegmentMapper mapper = mock(SubtitleTranslationSegmentMapper.class, CALLS_REAL_METHODS);
        when(mapper.delete(any(Wrapper.class))).thenReturn(2);
        when(mapper.selectCount(any(Wrapper.class))).thenReturn(3L);

        assertThat(mapper.deleteByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN")).isEqualTo(2);
        assertThat(mapper.countByTaskIdAndLanguage("task_1", 42L, "zh-CN")).isEqualTo(3L);

        verify(mapper).delete(any(Wrapper.class));
        verify(mapper).selectCount(any(Wrapper.class));
    }

    private static SubtitleTranslationSegment segment(String taskId, Long userId, String targetLanguage, int index, String text) {
        SubtitleTranslationSegment segment = new SubtitleTranslationSegment();
        segment.setId((long) index + 1);
        segment.setTaskId(taskId);
        segment.setUserId(userId);
        segment.setSegmentIndex(index);
        segment.setStartMillis(index * 1000L);
        segment.setEndMillis(index * 1000L + 900L);
        segment.setSourceLanguage("en");
        segment.setTargetLanguage(targetLanguage);
        segment.setTranslatedText(text);
        segment.setProvider("fake");
        segment.setCreatedAt(LocalDateTime.parse("2026-06-28T10:00:00"));
        segment.setUpdatedAt(LocalDateTime.parse("2026-06-28T10:00:00"));
        return segment;
    }
}
