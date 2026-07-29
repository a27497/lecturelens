package com.example.courselingo.vision.analysis;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.courselingo.vision.keyframe.VideoKeyframeProperties;
import com.example.courselingo.vision.ocr.VisionOcrProperties;
import java.time.Duration;
import org.junit.jupiter.api.Test;

class VisionConfigurationBoundsTest {

    @Test
    void clampsUntrustedConfigurationToOperationalBounds() {
        VideoKeyframeProperties keyframes = new VideoKeyframeProperties();
        keyframes.setSceneChangeThreshold(5.0d);
        keyframes.setContentChangeThreshold(-5.0d);
        keyframes.setMaxKeyframesPerMinute(Integer.MAX_VALUE);
        keyframes.setMaxKeyframesTotal(Integer.MAX_VALUE);
        keyframes.setPreOcrMaxFramesPerWindow(Integer.MAX_VALUE);
        keyframes.setPreOcrContentChangeMaxFramesPerWindow(Integer.MIN_VALUE);
        keyframes.setPreOcrLowInformationMaxFramesPerWindow(Integer.MAX_VALUE);
        keyframes.setPreOcrMaxFramesTotal(Integer.MAX_VALUE);
        keyframes.setFrameSamplingBatchSize(Integer.MAX_VALUE);
        keyframes.setBranchTimeoutSeconds(Long.MAX_VALUE);

        VisionAnalysisProperties analysis = new VisionAnalysisProperties();
        analysis.setMaxFramesPerMinute(Integer.MAX_VALUE);
        analysis.setMaxFramesTotal(Integer.MAX_VALUE);
        analysis.setMaxImageWidth(Integer.MAX_VALUE);
        analysis.setTimeout(Duration.ofDays(2));

        VisionOcrProperties ocr = new VisionOcrProperties();
        ocr.setTimeoutSeconds(Integer.MAX_VALUE);
        ocr.setPreprocessMaxWidth(Integer.MAX_VALUE);
        ocr.setConcurrency(Integer.MAX_VALUE);
        ocr.setQueueCapacity(Integer.MAX_VALUE);

        assertThat(keyframes.getSceneChangeThreshold()).isEqualTo(1.0d);
        assertThat(keyframes.getContentChangeThreshold()).isEqualTo(0.001d);
        assertThat(keyframes.getMaxKeyframesPerMinute()).isEqualTo(12);
        assertThat(keyframes.getMaxKeyframesTotal()).isEqualTo(1_000);
        assertThat(keyframes.getPreOcrMaxFramesPerWindow()).isEqualTo(12);
        assertThat(keyframes.getPreOcrContentChangeMaxFramesPerWindow()).isEqualTo(12);
        assertThat(keyframes.getPreOcrLowInformationMaxFramesPerWindow()).isEqualTo(12);
        assertThat(keyframes.getPreOcrMaxFramesTotal()).isEqualTo(2_000);
        assertThat(keyframes.getFrameSamplingBatchSize()).isEqualTo(64);
        assertThat(keyframes.getBranchTimeoutSeconds()).isEqualTo(14_400L);
        assertThat(analysis.getMaxFramesPerMinute()).isEqualTo(12);
        assertThat(analysis.getMaxFramesTotal()).isEqualTo(1_000);
        assertThat(analysis.getMaxImageWidth()).isEqualTo(3_840);
        assertThat(analysis.getTimeout()).isEqualTo(Duration.ofMinutes(10));
        assertThat(ocr.getTimeoutSeconds()).isEqualTo(300);
        assertThat(ocr.getPreprocessMaxWidth()).isEqualTo(3_840);
        assertThat(ocr.getConcurrency()).isEqualTo(8);
        assertThat(ocr.getQueueCapacity()).isEqualTo(64);
    }
}
