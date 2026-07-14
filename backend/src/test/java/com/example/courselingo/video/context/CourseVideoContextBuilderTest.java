package com.example.courselingo.video.context;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

import com.example.courselingo.chapter.domain.CourseChapter;
import com.example.courselingo.chapter.mapper.CourseChapterMapper;
import com.example.courselingo.fusion.VideoSegment;
import com.example.courselingo.fusion.mapper.VideoSegmentMapper;
import com.example.courselingo.learning.domain.LearningPackage;
import com.example.courselingo.learning.mapper.LearningPackageMapper;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.subtitle.domain.SubtitleTranslationSegment;
import com.example.courselingo.subtitle.domain.TaskFullTextResult;
import com.example.courselingo.subtitle.mapper.SubtitleSegmentMapper;
import com.example.courselingo.subtitle.mapper.SubtitleTranslationSegmentMapper;
import com.example.courselingo.subtitle.mapper.TaskFullTextResultMapper;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.video.context.service.CourseVideoContextBuildResult;
import com.example.courselingo.video.context.service.CourseVideoContextBuilder;
import com.example.courselingo.video.context.service.CourseVideoContextProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class CourseVideoContextBuilderTest {

    @Mock
    private SubtitleSegmentMapper subtitleSegmentMapper;

    @Mock
    private SubtitleTranslationSegmentMapper translationSegmentMapper;

    @Mock
    private CourseChapterMapper courseChapterMapper;

    @Mock
    private LearningPackageMapper learningPackageMapper;

    @Mock
    private VideoSegmentMapper videoSegmentMapper;

    @Mock
    private TaskFullTextResultMapper taskFullTextResultMapper;

    private CourseVideoContextProperties properties;
    private CourseVideoContextBuilder builder;

    @BeforeEach
    void setUp() {
        properties = new CourseVideoContextProperties();
        properties.setChunkWindowSeconds(240);
        properties.setMaxChunks(120);
        properties.setSourcePreviewChars(1200);
        properties.setTranslatedPreviewChars(1200);
        properties.setSummaryMaxChars(500);
        properties.setKeywordMaxCount(12);
        properties.setEvidenceMaxItemsPerChunk(8);
        builder = new CourseVideoContextBuilder(
            subtitleSegmentMapper,
            translationSegmentMapper,
            courseChapterMapper,
            learningPackageMapper,
            videoSegmentMapper,
            taskFullTextResultMapper,
            properties,
            new ObjectMapper()
        );
    }

    @Test
    void buildUsesTranslatedSubtitlesAndFixedTimeWindows() {
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            subtitle(0, 0L, 60000L, "The course introduces language models."),
            subtitle(1, 250000L, 300000L, "The teacher explains context windows.")
        ));
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN")).thenReturn(List.of(
            translation(0, 0L, 60000L, "课程介绍语言模型。"),
            translation(1, 250000L, 300000L, "老师解释上下文窗口。")
        ));
        when(courseChapterMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            chapter(0, 0L, 300000L, "语言模型基础", "介绍语言模型和上下文窗口。", "[\"语言模型\",\"上下文窗口\"]")
        ));
        when(learningPackageMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN")).thenReturn(learningPackage());
        VideoSegment videoSegment = videoSegment(0, 0L, 60000L, "ASR supplemental text");
        videoSegment.setOcrText("OCR should not be used");
        videoSegment.setVisualSummary("visual summary should not be used");
        videoSegment.setFusedSummary("fused visual text should not be used");
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(videoSegment));
        when(taskFullTextResultMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN")).thenReturn(fullText());

        CourseVideoContextBuildResult result = builder.build(task());

        assertThat(result.chunks()).hasSize(2);
        assertThat(result.chunks().getFirst().translatedTextPreview()).contains("课程介绍语言模型");
        assertThat(result.chunks().getFirst().sourceTextPreview()).contains("ASR supplemental text");
        assertThat(result.chunks().getFirst().evidence()).extracting("segmentIndex").containsExactly(0);
        assertThat(result.chunks().getFirst().summary()).contains("语言模型基础");
        assertThat(result.chunks().getFirst().summary()).doesNotContain("OCR").doesNotContain("visual");
        assertThat(result.chapters().getFirst().coveredChunkIndexes()).containsExactly(0, 1);
        assertThat(result.sourceStats().subtitleSegmentCount()).isEqualTo(2);
        assertThat(result.sourceStats().translatedSegmentCount()).isEqualTo(2);
        assertThat(result.sourceStats().hasLearningPackage()).isTrue();
        assertThat(result.sourceStats().hasVideoSegmentAsrText()).isTrue();
        assertThat(result.globalSummary()).contains("学习包总结");
        assertThat(result.globalKeywords()).contains("术语A");
    }

    @Test
    void buildFallsBackToSourceTextWhenTranslationsAreMissing() {
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            subtitle(0, 0L, 60000L, "The source transcript is still useful.")
        ));
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN")).thenReturn(List.of());

        CourseVideoContextBuildResult result = builder.build(task());

        assertThat(result.chunks()).hasSize(1);
        assertThat(result.chunks().getFirst().translatedTextPreview()).isBlank();
        assertThat(result.chunks().getFirst().sourceTextPreview()).contains("source transcript");
    }

    @Test
    void buildReturnsNoChunksWhenSubtitlesAreMissingEvenIfVideoSegmentAsrExists() {
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN")).thenReturn(List.of());
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            videoSegment(0, 0L, 60000L, "ASR-only fallback should not create chunks")
        ));

        CourseVideoContextBuildResult result = builder.build(task());

        assertThat(result.chunks()).isEmpty();
        assertThat(result.sourceStats().chunkCount()).isZero();
        assertThat(result.sourceStats().hasVideoSegmentAsrText()).isTrue();
    }

    @Test
    void buildEnlargesWindowAndTruncatesPreviewForLongVideos() {
        properties.setMaxChunks(1);
        properties.setSourcePreviewChars(20);
        properties.setTranslatedPreviewChars(20);
        properties.setSummaryMaxChars(30);
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            subtitle(0, 0L, 60000L, "source text ".repeat(20)),
            subtitle(1, 600000L, 660000L, "later source text ".repeat(20))
        ));
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN")).thenReturn(List.of(
            translation(0, 0L, 60000L, "中文译文".repeat(20)),
            translation(1, 600000L, 660000L, "后续译文".repeat(20))
        ));

        CourseVideoContextBuildResult result = builder.build(task());

        assertThat(result.chunks()).hasSize(1);
        assertThat(result.chunkWindowSeconds()).isGreaterThan(240);
        assertThat(result.chunks().getFirst().sourceTextPreview()).hasSizeLessThanOrEqualTo(20);
        assertThat(result.chunks().getFirst().translatedTextPreview()).hasSizeLessThanOrEqualTo(20);
        assertThat(result.chunks().getFirst().summary()).hasSizeLessThanOrEqualTo(30);
    }

    private static AnalysisTask task() {
        AnalysisTask task = new AnalysisTask();
        task.setId("task_1");
        task.setUserId(42L);
        task.setTargetLanguage("zh-CN");
        task.setStatus("SUCCEEDED");
        return task;
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

    private static CourseChapter chapter(int index, long start, long end, String title, String summary, String keywordsJson) {
        CourseChapter chapter = new CourseChapter();
        chapter.setTaskId("task_1");
        chapter.setUserId(42L);
        chapter.setChapterIndex(index);
        chapter.setStartMillis(start);
        chapter.setEndMillis(end);
        chapter.setTitle(title);
        chapter.setSummary(summary);
        chapter.setKeywordsJson(keywordsJson);
        return chapter;
    }

    private static LearningPackage learningPackage() {
        LearningPackage learningPackage = new LearningPackage();
        learningPackage.setTaskId("task_1");
        learningPackage.setUserId(42L);
        learningPackage.setTargetLanguage("zh-CN");
        learningPackage.setSummary("学习包总结：本课介绍上下文组织。");
        learningPackage.setGlossaryJson("[{\"term\":\"术语A\",\"definition\":\"定义A\"}]");
        return learningPackage;
    }

    private static VideoSegment videoSegment(int index, long start, long end, String asrText) {
        VideoSegment segment = new VideoSegment();
        segment.setTaskId("task_1");
        segment.setUserId(42L);
        segment.setSegmentIndex(index);
        segment.setStartMillis(start);
        segment.setEndMillis(end);
        segment.setAsrText(asrText);
        return segment;
    }

    private static TaskFullTextResult fullText() {
        TaskFullTextResult result = new TaskFullTextResult();
        result.setTaskId("task_1");
        result.setUserId(42L);
        result.setTargetLanguage("zh-CN");
        result.setSourceFullText("source full text");
        result.setTranslatedFullText("translated full text");
        return result;
    }
}
