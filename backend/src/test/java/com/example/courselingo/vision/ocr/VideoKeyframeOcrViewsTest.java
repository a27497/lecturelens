package com.example.courselingo.vision.ocr;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.courselingo.vision.analysis.VideoKeyframeAnalysis;
import java.util.List;
import org.junit.jupiter.api.Test;

class VideoKeyframeOcrViewsTest {

    @Test
    void historicalSucceededNoiseIsExposedAsEmptyWithoutChangingTheRow() {
        VideoKeyframeOcr row = row("RX eee I tok 一 mm c i eS yr * zz", null, "chi_sim+eng");
        VideoKeyframeAnalysis analysis = new VideoKeyframeAnalysis();
        analysis.setKeyframeId(9L);
        analysis.setScreenType("BROWSER");

        VideoKeyframeOcrView view = VideoKeyframeOcrViews.byKeyframeId(List.of(row), List.of(analysis)).get(9L);

        assertThat(view.status()).isEqualTo("EMPTY");
        assertThat(view.text()).isEmpty();
        assertThat(view.message()).isEqualTo("未识别到有效文字");
        assertThat(row.getStatus()).isEqualTo("SUCCEEDED");
    }

    @Test
    void historicalTechnicalTextRemainsVisible() {
        VideoKeyframeOcr row = row("docker compose up -d", 0.81d, "eng");

        VideoKeyframeOcrView view = VideoKeyframeOcrViews.byKeyframeId(List.of(row)).get(9L);

        assertThat(view.status()).isEqualTo("SUCCEEDED");
        assertThat(view.text()).isEqualTo("docker compose up -d");
    }

    private static VideoKeyframeOcr row(String text, Double confidence, String language) {
        VideoKeyframeOcr row = new VideoKeyframeOcr();
        row.setKeyframeId(9L);
        row.setStatus("SUCCEEDED");
        row.setOcrText(text);
        row.setConfidence(confidence);
        row.setLanguageHint(language);
        row.setProvider("fictional-test");
        return row;
    }
}
