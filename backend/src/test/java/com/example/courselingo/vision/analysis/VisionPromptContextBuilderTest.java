package com.example.courselingo.vision.analysis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.subtitle.domain.SubtitleTranslationSegment;
import com.example.courselingo.subtitle.mapper.SubtitleSegmentMapper;
import com.example.courselingo.subtitle.mapper.SubtitleTranslationSegmentMapper;
import java.util.List;
import org.junit.jupiter.api.Test;

class VisionPromptContextBuilderTest {

    @Test
    void includesOnlyNearbyAsrAndTranslationAndKeepsContextBounded() {
        SubtitleSegmentMapper subtitleMapper = mock(SubtitleSegmentMapper.class);
        SubtitleTranslationSegmentMapper translationMapper = mock(SubtitleTranslationSegmentMapper.class);
        when(subtitleMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            subtitle(50_000L, 55_000L, "nearby source evidence"),
            subtitle(150_000L, 155_000L, "outside source evidence")
        ));
        when(translationMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(List.of(
                translation(70_000L, 75_000L, "附近译文"),
                translation(10_000L, 15_000L, "区间外译文")
            ));

        String context = new VisionPromptContextBuilder(subtitleMapper, translationMapper)
            .build("task_1", 42L, 60_000L, "zh-CN");

        assertThat(context)
            .contains("Task language: zh-CN", "ASR [-30s,+30s]: nearby source evidence", "Translation [-30s,+30s]: 附近译文")
            .doesNotContain("outside source evidence", "区间外译文")
            .hasSizeLessThanOrEqualTo(6_000);
    }

    private static SubtitleSegment subtitle(long start, long end, String text) {
        SubtitleSegment row = new SubtitleSegment();
        row.setStartMillis(start);
        row.setEndMillis(end);
        row.setText(text);
        return row;
    }

    private static SubtitleTranslationSegment translation(long start, long end, String text) {
        SubtitleTranslationSegment row = new SubtitleTranslationSegment();
        row.setStartMillis(start);
        row.setEndMillis(end);
        row.setTranslatedText(text);
        return row;
    }
}
