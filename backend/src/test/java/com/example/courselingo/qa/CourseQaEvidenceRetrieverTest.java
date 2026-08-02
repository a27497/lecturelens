package com.example.courselingo.qa;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

import com.example.courselingo.fusion.VideoSegment;
import com.example.courselingo.fusion.mapper.VideoSegmentMapper;
import com.example.courselingo.qa.dto.CourseQaEvidenceItem;
import com.example.courselingo.qa.service.CourseQaEvidenceRetriever;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.subtitle.domain.SubtitleTranslationSegment;
import com.example.courselingo.subtitle.mapper.SubtitleSegmentMapper;
import com.example.courselingo.subtitle.mapper.SubtitleTranslationSegmentMapper;
import com.example.courselingo.vision.ocr.mapper.VideoKeyframeOcrMapper;
import java.util.List;
import java.util.stream.IntStream;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class CourseQaEvidenceRetrieverTest {

    @Mock
    private VideoSegmentMapper videoSegmentMapper;

    @Mock
    private SubtitleSegmentMapper subtitleSegmentMapper;

    @Mock
    private SubtitleTranslationSegmentMapper translationSegmentMapper;

    @Mock
    private VideoKeyframeOcrMapper ocrMapper;

    private CourseQaEvidenceRetriever retriever;

    @BeforeEach
    void setUp() {
        retriever = new CourseQaEvidenceRetriever(
            videoSegmentMapper,
            subtitleSegmentMapper,
            translationSegmentMapper,
            ocrMapper
        );
    }

    @Test
    void retrieveRanksVideoSegmentAndSubtitleEvidenceForKeywordQuestion() {
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            videoSegment(10L, 0, 180000L, 240000L, "OpenCL gateway and agent design", 0.86d),
            videoSegment(11L, 1, 240000L, 300000L, "unrelated content", 0.6d)
        ));
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            subtitle(20L, 0, 181000L, 190000L, "The teacher explains OpenCL here")
        ));
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(List.of(translation(0, 181000L, 190000L, "老师在这里讲 OpenCL")));
        List<CourseQaEvidenceItem> evidence = retriever.retrieve("task_1", 42L, "zh-CN", "老师在哪里讲了 OpenCL?");

        assertThat(evidence).isNotEmpty();
        assertThat(evidence.getFirst().sourceType()).isEqualTo("VIDEO_SEGMENT");
        assertThat(evidence.getFirst().startTimeMillis()).isEqualTo(180000L);
        assertThat(evidence).extracting(CourseQaEvidenceItem::snippet)
            .anySatisfy(text -> assertThat(text).contains("OpenCL"));
    }

    @Test
    void retrievePrioritizesExplicitTimeWindowAndExcludesKeyframeOcr() {
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            videoSegment(10L, 0, 0L, 60000L, "React pattern", 0.6d),
            videoSegment(11L, 3, 180000L, 300000L, "Agent gateway", 0.7d)
        ));
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(List.of());
        List<CourseQaEvidenceItem> evidence = retriever.retrieve("task_1", 42L, "zh-CN", "请解释 00:03:00 到 00:05:00 的内容");

        assertThat(evidence).isNotEmpty();
        assertThat(evidence.getFirst().startTimeMillis()).isEqualTo(180000L);
        assertThat(evidence).extracting(CourseQaEvidenceItem::snippet)
            .noneMatch(text -> text.contains("/////"))
            .noneMatch(text -> text.contains("Agent Gateway Architecture"))
            .noneMatch(text -> text.contains("画面文字包括"));
    }

    @Test
    void retrieveCleansHistoricalFusedSummaryForCourseQaEvidence() {
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            videoSegment(
                10L,
                0,
                0L,
                60000L,
                "Large language models explain course concepts",
                "本段主要讲解：Large language models explain course concepts；画面文字包括：{emcee ade ie ot...；画面显示：slides"
            )
        ));
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(List.of());
        List<CourseQaEvidenceItem> evidence = retriever.retrieve("task_1", 42L, "zh-CN", "language models");

        assertThat(evidence).isNotEmpty();
        assertThat(evidence.getFirst().snippet())
            .contains("本段语音原文：Large language models explain course concepts")
            .doesNotContain("本段主要讲解")
            .doesNotContain("画面文字包括：{emcee ade")
            .doesNotContain("ie ot");
    }

    @Test
    void retrieveKeepsReliableHistoricalOcrInFusedSummary() {
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            videoSegment(
                10L,
                0,
                0L,
                60000L,
                "The slide introduces language models",
                "本段主要讲解：The slide introduces language models；画面文字包括：Large Language Models for the curious beginner"
            )
        ));
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(List.of());
        List<CourseQaEvidenceItem> evidence = retriever.retrieve("task_1", 42L, "zh-CN", "language models");

        assertThat(evidence).isNotEmpty();
        assertThat(evidence.getFirst().snippet())
            .contains("本段语音原文：The slide introduces language models")
            .contains("画面文字包括：Large Language Models for the curious beginner");
    }

    @Test
    void retrieveUsesStructuredAsrLabelAndExcludesStructuredOcr() {
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            videoSegmentWithOcr(
                10L,
                0,
                0L,
                60000L,
                "The teacher explains what OpenCL is",
                "{emcee ade ie ot...",
                "本段主要讲解：stale fused text；画面文字包括：{emcee ade ie ot..."
            )
        ));
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(List.of());
        List<CourseQaEvidenceItem> evidence = retriever.retrieve("task_1", 42L, "zh-CN", "what is OpenCL");

        assertThat(evidence).isNotEmpty();
        assertThat(evidence.getFirst().snippet())
            .contains("本段语音原文：The teacher explains what OpenCL is")
            .doesNotContain("本段主要讲解")
            .doesNotContain("stale fused text")
            .doesNotContain("{emcee ade")
            .doesNotContain("ie ot");
    }

    @Test
    void retrieveKeepsReliableStructuredOcrInVideoSegmentEvidence() {
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            videoSegmentWithOcr(
                10L,
                0,
                0L,
                60000L,
                "The lesson introduces model parameters",
                "Parameter Weight",
                ""
            )
        ));
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(List.of());
        List<CourseQaEvidenceItem> evidence = retriever.retrieve("task_1", 42L, "zh-CN", "parameters");

        assertThat(evidence).isNotEmpty();
        assertThat(evidence.getFirst().snippet())
            .contains("本段语音原文：The lesson introduces model parameters")
            .contains("画面文字包括：Parameter Weight");
    }

    @Test
    void retrieveMatchesOcrOnlyEvidence() {
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            videoSegmentWithOcr(
                10L,
                0,
                0L,
                60000L,
                "",
                "What is OpenCL?",
                "画面文字包括：What is OpenCL?"
            )
        ));
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(List.of());
        List<CourseQaEvidenceItem> evidence = retriever.retrieve("task_1", 42L, "zh-CN", "OpenCL");

        assertThat(evidence).hasSize(1);
        assertThat(evidence.getFirst().snippet()).contains("画面文字包括：What is OpenCL?");
    }

    @Test
    void retrieveMatchesVisualOnlyEvidence() {
        VideoSegment segment = videoSegment(10L, 0, 0L, 60000L, "", "");
        segment.setVisualSummary("A dependency graph connects gateway and worker nodes");
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(segment));
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(List.of());

        List<CourseQaEvidenceItem> evidence = retriever.retrieve("task_1", 42L, "zh-CN", "dependency graph");

        assertThat(evidence).hasSize(1);
        assertThat(evidence.getFirst().snippet()).contains("画面显示：A dependency graph connects gateway and worker nodes");
    }

    @Test
    void retrieveReturnsEmptyForCompletelyUnrelatedQuestionEvenWithManyConfidentCandidates() {
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(
            IntStream.range(0, 100)
                .mapToObj(index -> videoSegment(
                    (long) index + 1,
                    index,
                    index * 60_000L,
                    (index + 1L) * 60_000L,
                    "Spring Boot microservices and Config Server",
                    1.0d
                ))
                .toList()
        );
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(List.of());

        List<CourseQaEvidenceItem> evidence = retriever.retrieve(
            "task_1",
            42L,
            "zh-CN",
            "古埃及金字塔的石料运输和建造工艺是什么？"
        );

        assertThat(evidence).isEmpty();
    }

    @Test
    void retrieveReturnsEmptyWhenOnlyGenericQuestionWordsMatch() {
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            videoSegment(10L, 0, 0L, 60_000L, "This course video explains lesson content", 1.0d)
        ));
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(List.of());

        assertThat(retriever.retrieve("task_1", 42L, "zh-CN", "What does this course video explain?"))
            .isEmpty();
    }

    @Test
    void retrieveReturnsEmptyWhenOnlyChineseGenericQuestionWordsMatch() {
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            videoSegment(10L, 0, 0L, 60_000L, "本节课程视频介绍内容", 1.0d)
        ));
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(List.of());

        assertThat(retriever.retrieve("task_1", 42L, "zh-CN", "课程 视频 内容 讲了 什么"))
            .isEmpty();
    }

    @Test
    void retrieveMatchesEnglishTechnicalTermsCaseInsensitively() {
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            videoSegment(10L, 0, 0L, 60_000L, "SPRING BOOT configuration", 0.8d)
        ));
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(List.of());

        assertThat(retriever.retrieve("task_1", 42L, "zh-CN", "spring boot"))
            .singleElement()
            .satisfies(item -> assertThat(item.snippet()).containsIgnoringCase("spring boot"));
    }

    @Test
    void retrieveMatchesHyphenatedQuestionAgainstSpacedTranscript() {
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            subtitle(20L, 0, 120_000L, 180_000L, "TF IDF stands for term frequency inverse document frequency.")
        ));
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(List.of());

        assertThat(retriever.retrieve("task_1", 42L, "zh-CN", "What does TF-IDF stand for?"))
            .singleElement()
            .satisfies(item -> assertThat(item.snippet()).contains("TF IDF"));
    }

    @ParameterizedTest
    @ValueSource(strings = {"TF-IDF", "TF IDF", "TF\u2010IDF", "TF\u2011IDF", "TF\u2012IDF", "TF\u2013IDF", "TF\u2014IDF"})
    void retrieveMatchesEverySupportedTfIdfDashVariant(String term) {
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            subtitle(20L, 0, 1_140_000L, 1_200_000L, "TF IDF stands for term frequency inverse document frequency.")
        ));
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(List.of());

        assertThat(retriever.retrieve("task_1", 42L, "zh-CN", "What does " + term + " stand for?"))
            .singleElement()
            .satisfies(item -> {
                assertThat(item.startTimeMillis()).isEqualTo(1_140_000L);
                assertThat(item.endTimeMillis()).isEqualTo(1_200_000L);
            });
    }

    @Test
    void retrieveMatchesSpacedQuestionAgainstUnicodeDashTranscript() {
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            videoSegment(10L, 0, 0L, 60_000L, "The TF–IDF weighting scheme ranks search results.", 0.8d)
        ));
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(List.of());

        assertThat(retriever.retrieve("task_1", 42L, "zh-CN", "Explain TF IDF"))
            .singleElement()
            .satisfies(item -> assertThat(item.snippet()).contains("TF–IDF"));
    }

    @Test
    void retrieveMatchesTechnicalTermInsideNaturalEnglishQuestion() {
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            videoSegment(10L, 0, 0L, 60_000L, "Spring Boot configuration", 0.8d)
        ));
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(List.of());

        assertThat(retriever.retrieve("task_1", 42L, "zh-CN", "How does Spring Boot work?"))
            .singleElement()
            .satisfies(item -> assertThat(item.snippet()).contains("Spring Boot"));
    }

    @Test
    void retrieveFindsBachFactForLongNaturalEnglishQuestion() {
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            subtitle(
                20L,
                0,
                600_000L,
                620_000L,
                "Johann Sebastian Bach served as cantor in Leipzig at St. Thomas Church."
            )
        ));
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(List.of(translation(0, 600_000L, 620_000L, "约翰·塞巴斯蒂安·巴赫在莱比锡担任圣托马斯教堂乐长。")));

        List<CourseQaEvidenceItem> evidence = retriever.retrieve(
            "task_1",
            42L,
            "zh-CN",
            "What position did Johann Sebastian Bach hold in Leipzig?"
        );

        assertThat(evidence).singleElement().satisfies(item -> {
            assertThat(item.snippet()).contains("Bach", "Leipzig");
            assertThat(item.translatedSnippet()).contains("巴赫", "莱比锡");
        });
    }

    @Test
    void retrieveFindsBachFactForLongNaturalChineseQuestion() {
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            subtitle(20L, 0, 600_000L, 620_000L, "Bach served as cantor in Leipzig.")
        ));
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(List.of(translation(0, 600_000L, 620_000L, "巴赫在莱比锡担任教堂乐长。")));

        List<CourseQaEvidenceItem> evidence = retriever.retrieve(
            "task_1",
            42L,
            "zh-CN",
            "请问巴赫在莱比锡担任的职位叫什么名字？"
        );

        assertThat(evidence).singleElement()
            .satisfies(item -> assertThat(item.translatedSnippet()).contains("巴赫", "莱比锡", "乐长"));
    }

    @Test
    void retrieveFindsEvidenceForTheThreeRealBachQuestions() {
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            subtitle(20L, 0, 0L, 60_000L, "Bach was born in 1685."),
            subtitle(21L, 1, 480_000L, 540_000L,
                "The Duke had Bach thrown in jail for a month because he had not obtained a release.")
        ));
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(List.of(
                translation(0, 0L, 60_000L, "巴赫出生于1685年。"),
                translation(1, 480_000L, 540_000L,
                    "公爵让巴赫入狱，巴赫被关押了一个月，因为他没有获得解职许可。")
            ));

        assertThat(retriever.retrieve(
            "task_1", 42L, "zh-CN", "课程中提到巴赫为什么被关押一个月？请指出相关时间段。"
        )).isNotEmpty().allSatisfy(item -> assertThat(item.startTimeMillis()).isEqualTo(480_000L));
        assertThat(retriever.retrieve(
            "task_1", 42L, "zh-CN", "Why was Bach thrown in jail for a month?"
        )).isNotEmpty().allSatisfy(item -> assertThat(item.startTimeMillis()).isEqualTo(480_000L));
        assertThat(retriever.retrieve(
            "task_1", 42L, "zh-CN", "When was Bach born?"
        )).isNotEmpty().allSatisfy(item -> assertThat(item.startTimeMillis()).isEqualTo(0L));
    }

    @Test
    void retrieveDoesNotAcceptOneIncidentalWordFromANaturalQuestion() {
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            videoSegment(10L, 0, 0L, 60_000L, "The machine completed its monthly backup.", 0.8d)
        ));
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(List.of());

        assertThat(retriever.retrieve(
            "task_1", 42L, "zh-CN", "Why was Bach thrown in jail for a month?"
        )).isEmpty();
    }

    @Test
    void retrieveSplitsChineseEnglishBoundaryForTechnicalTermWithoutSpaces() {
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            videoSegment(10L, 0, 0L, 60_000L, "Transformer 架构与注意力机制", 0.8d)
        ));
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(List.of());

        List<CourseQaEvidenceItem> evidence = retriever.retrieve(
            "task_1",
            42L,
            "zh-CN",
            "课程中介绍的Transformer是什么？"
        );

        assertThat(evidence).isNotEmpty();
        assertThat(evidence.getFirst().snippet()).contains("Transformer");
    }

    @Test
    void retrieveExtractsChineseTechnicalTermFromCompleteQuestion() {
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            videoSegment(10L, 0, 0L, 60_000L, "反向传播用于计算神经网络梯度", 0.8d)
        ));
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(List.of());

        List<CourseQaEvidenceItem> evidence = retriever.retrieve(
            "task_1",
            42L,
            "zh-CN",
            "这节课讲解的反向传播是什么？"
        );

        assertThat(evidence).isNotEmpty();
        assertThat(evidence.getFirst().snippet()).contains("反向传播");
    }

    @Test
    void retrieveRanksRelevantEvidenceAndLimitsResultsToEight() {
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(
            IntStream.range(0, 12)
                .mapToObj(index -> videoSegment(
                    (long) index + 1,
                    index,
                    index * 60_000L,
                    (index + 1L) * 60_000L,
                    "Spring Boot configuration " + index,
                    index / 12.0d
                ))
                .toList()
        );
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(List.of());

        List<CourseQaEvidenceItem> evidence = retriever.retrieve("task_1", 42L, "zh-CN", "Spring Boot");

        assertThat(evidence).hasSize(8);
        assertThat(evidence).extracting(CourseQaEvidenceItem::confidence).isSortedAccordingTo(
            java.util.Comparator.reverseOrder()
        );
    }

    @Test
    void retrieveOverviewSamplesTheWholeTimelineWithoutGenericKeywordBias() {
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(
            IntStream.range(0, 10)
                .mapToObj(index -> videoSegment(
                    (long) index + 1,
                    index,
                    index * 60_000L,
                    (index + 1L) * 60_000L,
                    "course topic " + index,
                    0.8d
                ))
                .toList()
        );
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(List.of());

        List<CourseQaEvidenceItem> evidence = retriever.retrieve(
            "task_1",
            42L,
            "zh-CN",
            "这节课程主要讲了什么？"
        );

        assertThat(evidence).hasSize(6);
        assertThat(evidence.getFirst().startTimeMillis()).isZero();
        assertThat(evidence.getLast().endTimeMillis()).isEqualTo(600_000L);
    }

    @Test
    void retrieveUnderstandsNaturalMinuteAndUsesNarrowNearbyWindow() {
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            videoSegment(1L, 0, 0L, 60_000L, "course introduction", 0.9d),
            videoSegment(2L, 9, 540_000L, 600_000L, "service discovery", 0.8d),
            videoSegment(3L, 10, 600_000L, 660_000L, "API Gateway", 0.8d),
            videoSegment(4L, 12, 720_000L, 780_000L, "Docker Compose", 0.9d)
        ));
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(List.of());

        List<CourseQaEvidenceItem> evidence = retriever.retrieve(
            "task_1",
            42L,
            "zh-CN",
            "10 分钟附近讲了什么？"
        );

        assertThat(evidence).extracting(CourseQaEvidenceItem::startTimeMillis)
            .containsExactly(540_000L, 600_000L);
    }

    @Test
    void retrieveUnderstandsNaturalEnglishSecondTimestamp() {
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            videoSegment(1L, 0, 0L, 60_000L, "course introduction", 0.9d),
            videoSegment(2L, 1, 60_000L, 120_000L,
                "Remember that the example document contains three searchable tokens.", 0.8d),
            videoSegment(3L, 3, 180_000L, 240_000L, "unrelated conclusion", 0.9d)
        ));
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(List.of());

        List<CourseQaEvidenceItem> evidence = retriever.retrieve(
            "task_1",
            42L,
            "zh-CN",
            "At 60 seconds, what does the lesson ask us to remember?"
        );

        assertThat(evidence).isNotEmpty();
        assertThat(evidence.getFirst().startTimeMillis()).isEqualTo(60_000L);
        assertThat(evidence).extracting(CourseQaEvidenceItem::startTimeMillis)
            .doesNotContain(180_000L);
    }

    @Test
    void retrieveDeduplicatesOverlappingSemanticallyEquivalentSources() {
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            videoSegment(1L, 0, 0L, 60_000L, "Spring Boot configures the Java backend API", 0.9d)
        ));
        when(subtitleSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(
            subtitle(2L, 0, 1_000L, 20_000L, "Spring Boot configures the Java backend API")
        ));
        when(translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage("task_1", 42L, "zh-CN"))
            .thenReturn(List.of());

        assertThat(retriever.retrieve("task_1", 42L, "zh-CN", "Spring Boot"))
            .singleElement()
            .satisfies(item -> assertThat(item.sourceType()).isEqualTo("VIDEO_SEGMENT"));
    }

    private static VideoSegment videoSegment(Long id, int index, long start, long end, String text, double confidence) {
        return videoSegment(id, index, start, end, text, text, confidence);
    }

    private static VideoSegment videoSegment(Long id, int index, long start, long end, String asrText, String fusedSummary) {
        return videoSegment(id, index, start, end, asrText, fusedSummary, 0.8d);
    }

    private static VideoSegment videoSegment(
        Long id,
        int index,
        long start,
        long end,
        String asrText,
        String fusedSummary,
        double confidence
    ) {
        VideoSegment segment = new VideoSegment();
        segment.setId(id);
        segment.setTaskId("task_1");
        segment.setUserId(42L);
        segment.setSegmentIndex(index);
        segment.setStartMillis(start);
        segment.setEndMillis(end);
        segment.setTimeText(format(start) + " - " + format(end));
        segment.setAsrText(asrText);
        segment.setFusedSummary(fusedSummary);
        segment.setKeywordsJson("[\"OpenCL\",\"agent\"]");
        segment.setStatus("SUCCEEDED");
        segment.setConfidence(confidence);
        return segment;
    }

    private static VideoSegment videoSegmentWithOcr(
        Long id,
        int index,
        long start,
        long end,
        String asrText,
        String ocrText,
        String fusedSummary
    ) {
        VideoSegment segment = videoSegment(id, index, start, end, asrText, fusedSummary, 0.8d);
        segment.setOcrText(ocrText);
        return segment;
    }

    private static SubtitleSegment subtitle(Long id, int index, long start, long end, String text) {
        SubtitleSegment segment = new SubtitleSegment();
        segment.setId(id);
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

    private static String format(long millis) {
        long total = millis / 1000L;
        return "%02d:%02d:%02d".formatted(total / 3600, (total % 3600) / 60, total % 60);
    }
}
