package com.example.courselingo.chapter;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

import com.example.courselingo.chapter.dto.CourseChapterEvidenceItem;
import com.example.courselingo.chapter.service.CourseChapterEvidenceBuilder;
import com.example.courselingo.chapter.service.CourseChapterEvidenceBundle;
import com.example.courselingo.chapter.service.CourseChapterProperties;
import com.example.courselingo.fusion.VideoSegment;
import com.example.courselingo.fusion.mapper.VideoSegmentMapper;
import com.example.courselingo.learning.mapper.LearningPackageMapper;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.subtitle.domain.SubtitleTranslationSegment;
import com.example.courselingo.subtitle.mapper.SubtitleSegmentMapper;
import com.example.courselingo.subtitle.mapper.SubtitleTranslationSegmentMapper;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class CourseChapterEvidenceBuilderTest {

    @Mock
    private SubtitleSegmentMapper subtitleSegmentMapper;

    @Mock
    private SubtitleTranslationSegmentMapper translationSegmentMapper;

    @Mock
    private VideoSegmentMapper videoSegmentMapper;

    @Mock
    private LearningPackageMapper learningPackageMapper;

    private CourseChapterEvidenceBuilder builder;

    @BeforeEach
    void setUp() {
        CourseChapterProperties properties = new CourseChapterProperties();
        properties.setWindowSeconds(240);
        properties.setMaxCharsPerWindow(1200);
        builder = new CourseChapterEvidenceBuilder(
            subtitleSegmentMapper,
            translationSegmentMapper,
            videoSegmentMapper,
            learningPackageMapper,
            properties
        );
    }

    @Test
    void buildUsesSubtitleTranslationAndAsrWithoutOcrOrFusedSummary() {
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            subtitle(0, 0L, 60000L, "The teacher introduces language models.")
        ));
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(List.of(translation(0, 0L, 60000L, "老师介绍语言模型。")));
        VideoSegment videoSegment = videoSegment(0, 0L, 60000L, "Whatever the user types becomes input tokens.");
        videoSegment.setOcrText("画面文字包括：Vt — it 哥 gl");
        videoSegment.setFusedSummary("画面文字包括：{emcee ade");
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(videoSegment));

        CourseChapterEvidenceBundle bundle = builder.build("task_1", 42L, "zh-CN");

        assertThat(bundle.evidence()).hasSize(1);
        CourseChapterEvidenceItem item = bundle.evidence().getFirst();
        assertThat(item.text())
            .contains("字幕译文：老师介绍语言模型。")
            .contains("原文：The teacher introduces language models.")
            .contains("本段语音原文：Whatever the user types becomes input tokens.")
            .doesNotContain("画面文字包括")
            .doesNotContain("{emcee")
            .doesNotContain("Vt");
    }

    @Test
    void buildReturnsEmptyEvidenceWhenOnlyOcrOrVisualDataExists() {
        VideoSegment videoSegment = videoSegment(0, 0L, 60000L, "");
        videoSegment.setOcrText("What is OpenCL?");
        videoSegment.setVisualSummary("Slide with a title");
        videoSegment.setFusedSummary("画面文字包括：What is OpenCL?");
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN")).thenReturn(List.of());
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(videoSegment));

        CourseChapterEvidenceBundle bundle = builder.build("task_1", 42L, "zh-CN");

        assertThat(bundle.evidence()).isEmpty();
    }

    @Test
    void buildKeepsSubtitleAndFusionTailAtAuthoritativeDuration() {
        long durationMillis = 4_090_265L;
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            subtitle(68, 4_080_000L, durationMillis, "Final transcript segment")
        ));
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(List.of());
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            videoSegment(68, 4_080_000L, durationMillis, "Final fused ASR segment")
        ));

        CourseChapterEvidenceBundle bundle = builder.build("task_1", 42L, "zh-CN");

        assertThat(bundle.evidence()).isNotEmpty();
        assertThat(bundle.evidence())
            .extracting(CourseChapterEvidenceItem::endTimeMillis)
            .allMatch(end -> end <= durationMillis);
        assertThat(bundle.evidence().getLast().endTimeMillis()).isEqualTo(durationMillis);
        assertThat(bundle.evidence().getLast().text())
            .contains("Final transcript segment")
            .contains("Final fused ASR segment");
    }

    private static SubtitleSegment subtitle(int index, long start, long end, String text) {
        SubtitleSegment segment = new SubtitleSegment();
        segment.setTaskId("task_1");
        segment.setUserId(42L);
        segment.setSegmentIndex(index);
        segment.setStartMillis(start);
        segment.setEndMillis(end);
        segment.setLanguage("en");
        segment.setText(text);
        return segment;
    }

    private static SubtitleTranslationSegment translation(int index, long start, long end, String text) {
        SubtitleTranslationSegment segment = new SubtitleTranslationSegment();
        segment.setTaskId("task_1");
        segment.setUserId(42L);
        segment.setSegmentIndex(index);
        segment.setStartMillis(start);
        segment.setEndMillis(end);
        segment.setTargetLanguage("zh-CN");
        segment.setTranslatedText(text);
        return segment;
    }

    private static VideoSegment videoSegment(int index, long start, long end, String asrText) {
        VideoSegment segment = new VideoSegment();
        segment.setTaskId("task_1");
        segment.setUserId(42L);
        segment.setSegmentIndex(index);
        segment.setStartMillis(start);
        segment.setEndMillis(end);
        segment.setTimeText("00:00:00 - 00:01:00");
        segment.setAsrText(asrText);
        return segment;
    }
}
