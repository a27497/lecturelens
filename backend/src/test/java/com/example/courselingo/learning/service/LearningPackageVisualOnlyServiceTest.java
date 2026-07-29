package com.example.courselingo.learning.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.ai.llm.LlmProvider;
import com.example.courselingo.ai.llm.LlmRequest;
import com.example.courselingo.ai.llm.LlmResult;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.fusion.VideoSegment;
import com.example.courselingo.fusion.mapper.VideoSegmentMapper;
import com.example.courselingo.learning.domain.LearningPackage;
import com.example.courselingo.learning.mapper.LearningPackageMapper;
import com.example.courselingo.subtitle.mapper.SubtitleSegmentMapper;
import com.example.courselingo.subtitle.mapper.SubtitleTranslationSegmentMapper;
import com.example.courselingo.subtitle.mapper.TaskFullTextResultMapper;
import java.time.Clock;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

class LearningPackageVisualOnlyServiceTest {

    private final SubtitleSegmentMapper sourceMapper = mock(SubtitleSegmentMapper.class);
    private final SubtitleTranslationSegmentMapper translationMapper = mock(SubtitleTranslationSegmentMapper.class);
    private final TaskFullTextResultMapper fullTextMapper = mock(TaskFullTextResultMapper.class);
    private final LearningPackageMapper packageMapper = mock(LearningPackageMapper.class);
    private final VideoSegmentMapper videoSegmentMapper = mock(VideoSegmentMapper.class);

    @Test
    void visualOnlyUsesSemanticTimelineWithoutReadingSubtitleDependentData() {
        AtomicReference<LlmRequest> capturedRequest = new AtomicReference<>();
        LlmProvider provider = provider(capturedRequest);
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(visualSegment()));
        when(packageMapper.insert(any(LearningPackage.class))).thenReturn(1);
        LearningPackageServiceImpl service = service(provider);

        int saved = service.generateLearningPackage(command());

        assertThat(saved).isEqualTo(1);
        assertThat(capturedRequest.get().messages().get(1).content())
            .contains("\"mode\":\"MULTIMODAL\"")
            .contains("Tests move from failed to successful")
            .doesNotContain("translatedSubtitles");
        verify(translationMapper, never()).selectByTaskIdUserIdAndTargetLanguage(any(), any(), any());
        verify(fullTextMapper, never()).selectByTaskIdUserIdAndTargetLanguage(any(), any(), any());
        verify(packageMapper).insert(any(LearningPackage.class));
    }

    @Test
    void emptySubtitlesWithoutSemanticVisualEvidenceAreRejectedBeforeCallingLlm() {
        AtomicReference<LlmRequest> capturedRequest = new AtomicReference<>();
        when(sourceMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of());
        VideoSegment nonSemantic = visualSegment();
        nonSemantic.setOcrText(" ");
        nonSemantic.setVisualSummary(null);
        when(videoSegmentMapper.selectByTaskIdAndUserId("task_1", 42L)).thenReturn(List.of(nonSemantic));

        assertThatThrownBy(() -> service(provider(capturedRequest)).generateLearningPackage(command()))
            .isInstanceOf(BusinessException.class)
            .hasMessage("Source subtitle segments are required");

        assertThat(capturedRequest).hasNullValue();
        verify(packageMapper, never()).insert(any(LearningPackage.class));
    }

    private LearningPackageServiceImpl service(LlmProvider provider) {
        return new LearningPackageServiceImpl(
            sourceMapper,
            translationMapper,
            fullTextMapper,
            packageMapper,
            videoSegmentMapper,
            () -> provider,
            Clock.systemUTC(),
            new LearningPackageResponseParser(),
            new LearningPackageProperties(),
            null
        );
    }

    private static LlmProvider provider(AtomicReference<LlmRequest> capturedRequest) {
        return new LlmProvider() {
            @Override
            public LlmResult generate(LlmRequest request) {
                capturedRequest.set(request);
                return new LlmResult(
                    "fake",
                    "fake-model",
                    "{\"title\":\"Visual course\",\"summary\":\"Visual summary\"," +
                        "\"keyPoints\":[\"Tests pass\"],\"glossary\":[],\"qa\":[]}",
                    "stop",
                    null,
                    Duration.ofMillis(1),
                    Map.of()
                );
            }

            @Override
            public String providerName() {
                return "fake";
            }
        };
    }

    private static GenerateLearningPackageCommand command() {
        return new GenerateLearningPackageCommand("task_1", 42L, "en", "zh-CN", "req_1");
    }

    private static VideoSegment visualSegment() {
        VideoSegment segment = new VideoSegment();
        segment.setId(1L);
        segment.setTaskId("task_1");
        segment.setUserId(42L);
        segment.setSegmentIndex(0);
        segment.setStartMillis(0L);
        segment.setEndMillis(60_000L);
        segment.setTimeText("00:00:00 - 00:01:00");
        segment.setOcrText("FAIL then PASS");
        segment.setVisualSummary("Tests move from failed to successful");
        segment.setFusedSummary("Visual-only terminal progression");
        segment.setKeywordsJson("[\"tests\"]");
        segment.setStatus("SUCCEEDED");
        segment.setConfidence(0.9d);
        return segment;
    }
}
