package com.example.courselingo.qa;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.evidence.CourseEvidenceService;
import com.example.courselingo.fusion.mapper.VideoSegmentMapper;
import com.example.courselingo.qa.service.CourseQaEvidenceRetriever;
import com.example.courselingo.qa.service.DenseEvidenceClient;
import com.example.courselingo.subtitle.mapper.SubtitleSegmentMapper;
import com.example.courselingo.subtitle.mapper.SubtitleTranslationSegmentMapper;
import com.example.courselingo.vision.ocr.mapper.VideoKeyframeOcrMapper;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class DenseRetrievalRoutingTest {
    private final CourseEvidenceService sources = mock(CourseEvidenceService.class);
    private final DenseEvidenceClient dense = mock(DenseEvidenceClient.class);
    private CourseQaEvidenceRetriever retriever;

    @BeforeEach
    void setup() {
        retriever = new CourseQaEvidenceRetriever(mock(VideoSegmentMapper.class), mock(SubtitleSegmentMapper.class),
            mock(SubtitleTranslationSegmentMapper.class), mock(VideoKeyframeOcrMapper.class));
        retriever.configureEvidence(sources);
        retriever.configureDenseRetrieval(dense);
        when(dense.enabled()).thenReturn(true);
        when(sources.current("task-1", 42L)).thenReturn(List.of(DenseEvidenceClientTest.evidence("e1", 7)));
    }

    @Test
    void semanticQuestionUsesDenseAndCanonicalCitation() {
        when(dense.retrieve(anyString(), anyLong(), anyList(), anyString(), isNull(), isNull(), eq(8)))
            .thenReturn(List.of(DenseEvidenceClientTest.evidence("e1", 7)));
        var result = retriever.retrieve("task-1", 42L, "zh-CN", "如何终止执行？");
        assertThat(result).hasSize(1);
        assertThat(result.getFirst().evidenceId()).isEqualTo("e1");
        assertThat(result.getFirst().revision()).isEqualTo(7);
        verify(sources, times(2)).current("task-1", 42L);
    }

    @Test
    void overviewKeepsDistributedEvidencePath() {
        assertThat(retriever.retrieve("task-1", 42L, "zh-CN", "这节课程主要讲了什么？")).isNotEmpty();
        verify(dense, never()).retrieve(any(), any(), any(), any(), any(), any(), anyInt());
    }

    @Test
    void rebuildingDuringRemoteCallRejectsOldCitations() {
        when(sources.current("task-1", 42L)).thenReturn(List.of(DenseEvidenceClientTest.evidence("e1", 7)))
            .thenReturn(List.of(DenseEvidenceClientTest.evidence("e2", 8)));
        when(dense.retrieve(anyString(), anyLong(), anyList(), anyString(), isNull(), isNull(), eq(8)))
            .thenReturn(List.of(DenseEvidenceClientTest.evidence("e1", 7)));
        assertThatThrownBy(() -> retriever.retrieve("task-1", 42L, "zh-CN", "如何终止执行？"))
            .isInstanceOf(BusinessException.class);
    }

    @Test
    void deletionDuringRemoteCallRejectsResult() {
        when(sources.current("task-1", 42L)).thenReturn(List.of(DenseEvidenceClientTest.evidence("e1", 7)))
            .thenThrow(new BusinessException(ErrorCode.TASK_NOT_FOUND));
        when(dense.retrieve(anyString(), anyLong(), anyList(), anyString(), isNull(), isNull(), eq(8)))
            .thenReturn(List.of(DenseEvidenceClientTest.evidence("e1", 7)));
        assertThatThrownBy(() -> retriever.retrieve("task-1", 42L, "zh-CN", "如何终止执行？"))
            .isInstanceOfSatisfying(BusinessException.class,
                failure -> assertThat(failure.errorCode()).isEqualTo(ErrorCode.TASK_NOT_FOUND));
    }
}
