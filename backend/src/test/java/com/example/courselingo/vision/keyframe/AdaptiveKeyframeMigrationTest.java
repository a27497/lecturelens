package com.example.courselingo.vision.keyframe;

import static org.assertj.core.api.Assertions.assertThat;

import com.baomidou.mybatisplus.annotation.TableField;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Map;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

class AdaptiveKeyframeMigrationTest {

    @Test
    void addsOnlyNullableBackwardCompatibleQualityColumns() throws Exception {
        String sql;
        try (var input = getClass().getClassLoader().getResourceAsStream(
            "db/migration/V20__add_adaptive_keyframe_quality.sql"
        )) {
            assertThat(input).isNotNull();
            sql = new String(input.readAllBytes(), StandardCharsets.UTF_8);
        }

        assertThat(sql).contains("quality_score DECIMAL(10,6) NULL");
        assertThat(sql).contains("perceptual_hash VARCHAR(32) NULL");
        assertThat(sql).contains("degraded BOOLEAN NULL");
        assertThat(sql).contains("source_type VARCHAR(32) NULL");
        assertThat(sql).doesNotContain("NOT NULL");
        assertThat(sql.lines().filter(line -> line.contains("ADD COLUMN")).count()).isEqualTo(8);
        assertThat(sql.strip()).endsWith(";");
        assertThat(sql).doesNotContain("AUTOINCREMENT", "NVARCHAR", "CLOB", "GO\n");

        Map<String, String> mappedColumns = Arrays.stream(VideoKeyframe.class.getDeclaredFields())
            .filter(field -> field.isAnnotationPresent(TableField.class))
            .collect(Collectors.toMap(field -> field.getName(), field -> field.getAnnotation(TableField.class).value()));
        assertThat(mappedColumns).containsAllEntriesOf(Map.of(
            "qualityScore", "quality_score",
            "sharpnessScore", "sharpness_score",
            "brightnessMean", "brightness_mean",
            "brightnessVariance", "brightness_variance",
            "edgeDensity", "edge_density",
            "perceptualHash", "perceptual_hash",
            "degraded", "degraded",
            "sourceType", "source_type"
        ));
    }
}
