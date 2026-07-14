package com.example.courselingo.subtitle;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.CALLS_REAL_METHODS;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.baomidou.mybatisplus.core.conditions.Wrapper;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.subtitle.mapper.SubtitleSegmentMapper;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.Test;

class SubtitleSegmentMapperTest {

    @Test
    void mapperCanInsertSubtitleSegment() {
        SubtitleSegmentMapper mapper = mock(SubtitleSegmentMapper.class);
        SubtitleSegment segment = segment("task_1", 42L, 0, "hello");
        when(mapper.insert(segment)).thenReturn(1);

        int inserted = mapper.insert(segment);

        assertThat(inserted).isEqualTo(1);
        verify(mapper).insert(segment);
    }

    @Test
    void mapperQueriesByTaskIdAndUserIdInSegmentIndexOrder() {
        SubtitleSegmentMapper mapper = mock(SubtitleSegmentMapper.class, CALLS_REAL_METHODS);
        SubtitleSegment first = segment("task_1", 42L, 0, "first");
        SubtitleSegment second = segment("task_1", 42L, 1, "second");
        when(mapper.selectList(any(Wrapper.class))).thenReturn(List.of(first, second));

        List<SubtitleSegment> segments = mapper.selectByTaskIdAndUserId("task_1", 42L);

        assertThat(segments).extracting(SubtitleSegment::getSegmentIndex).containsExactly(0, 1);
        verify(mapper).selectList(any(Wrapper.class));
    }

    @Test
    void mapperDeleteAndCountAreOwnerScoped() {
        SubtitleSegmentMapper mapper = mock(SubtitleSegmentMapper.class, CALLS_REAL_METHODS);
        when(mapper.delete(any(Wrapper.class))).thenReturn(2);
        when(mapper.selectCount(any(Wrapper.class))).thenReturn(3L);

        assertThat(mapper.deleteByTaskIdAndUserId("task_1", 42L)).isEqualTo(2);
        assertThat(mapper.countByTaskIdAndUserId("task_1", 42L)).isEqualTo(3L);

        verify(mapper).delete(any(Wrapper.class));
        verify(mapper).selectCount(any(Wrapper.class));
    }

    private static SubtitleSegment segment(String taskId, Long userId, int index, String text) {
        SubtitleSegment segment = new SubtitleSegment();
        segment.setId((long) index + 1);
        segment.setTaskId(taskId);
        segment.setUserId(userId);
        segment.setSegmentIndex(index);
        segment.setStartMillis(index * 1000L);
        segment.setEndMillis(index * 1000L + 900L);
        segment.setLanguage("en");
        segment.setText(text);
        segment.setProvider("mock");
        segment.setCreatedAt(LocalDateTime.parse("2026-06-28T10:00:00"));
        segment.setUpdatedAt(LocalDateTime.parse("2026-06-28T10:00:00"));
        return segment;
    }
}
