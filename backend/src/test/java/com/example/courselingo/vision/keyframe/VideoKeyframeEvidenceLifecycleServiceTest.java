package com.example.courselingo.vision.keyframe;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.when;

import com.example.courselingo.storage.StorageService;
import com.example.courselingo.vision.analysis.mapper.VideoKeyframeAnalysisMapper;
import com.example.courselingo.vision.keyframe.mapper.VideoKeyframeMapper;
import com.example.courselingo.vision.ocr.mapper.VideoKeyframeOcrMapper;
import java.util.List;
import org.junit.jupiter.api.Test;

class VideoKeyframeEvidenceLifecycleServiceTest {

    @Test
    void storageFailureKeepsKeyframeRowsDiscoverableForADeferredRetry() {
        VideoKeyframeMapper keyframes = mock(VideoKeyframeMapper.class);
        VideoKeyframeOcrMapper ocr = mock(VideoKeyframeOcrMapper.class);
        VideoKeyframeAnalysisMapper analysis = mock(VideoKeyframeAnalysisMapper.class);
        StorageService storage = mock(StorageService.class);
        VideoKeyframe first = frame("evidence/first.jpg");
        VideoKeyframe second = frame("evidence/second.jpg");
        when(keyframes.selectExistingForTask("task_1", 42L)).thenReturn(List.of(first, second));
        doThrow(new IllegalStateException("storage unavailable"))
            .when(storage).deleteObject("evidence/first.jpg");
        VideoKeyframeEvidenceLifecycleServiceImpl service = new VideoKeyframeEvidenceLifecycleServiceImpl(
            keyframes,
            ocr,
            analysis,
            storage
        );

        assertThatThrownBy(() -> service.cleanupTaskEvidence("task_1", 42L))
            .isInstanceOf(IllegalStateException.class)
            .hasMessage("Keyframe evidence object cleanup incomplete")
            .satisfies(error -> assertThat(error.getMessage()).doesNotContain("evidence/first.jpg"));

        verify(analysis).deleteByTaskIdAndUserId("task_1", 42L);
        verify(ocr).deleteByTaskIdAndUserId("task_1", 42L);
        verify(keyframes, never()).deleteByTaskIdAndUserId("task_1", 42L);
        verify(storage).deleteObject("evidence/first.jpg");
        verify(storage).deleteObject("evidence/second.jpg");
    }

    @Test
    void deletesRowsOnlyAfterEveryObjectDeleteSucceeds() {
        VideoKeyframeMapper keyframes = mock(VideoKeyframeMapper.class);
        VideoKeyframeOcrMapper ocr = mock(VideoKeyframeOcrMapper.class);
        VideoKeyframeAnalysisMapper analysis = mock(VideoKeyframeAnalysisMapper.class);
        StorageService storage = mock(StorageService.class);
        when(keyframes.selectExistingForTask("task_1", 42L)).thenReturn(List.of(frame("evidence/first.jpg")));
        when(keyframes.deleteByTaskIdAndUserId("task_1", 42L)).thenReturn(1);
        VideoKeyframeEvidenceLifecycleServiceImpl service = new VideoKeyframeEvidenceLifecycleServiceImpl(
            keyframes,
            ocr,
            analysis,
            storage
        );

        assertThat(service.cleanupTaskEvidence("task_1", 42L)).isEqualTo(1);

        verify(storage).deleteObject("evidence/first.jpg");
        verify(keyframes).deleteByTaskIdAndUserId("task_1", 42L);
    }

    private static VideoKeyframe frame(String objectKey) {
        VideoKeyframe frame = new VideoKeyframe();
        frame.setObjectKey(objectKey);
        return frame;
    }
}
