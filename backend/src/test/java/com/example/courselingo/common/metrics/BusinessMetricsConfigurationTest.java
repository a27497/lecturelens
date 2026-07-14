package com.example.courselingo.common.metrics;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;

class BusinessMetricsConfigurationTest {

    @Test
    void applicationExposesOnlySafeActuatorEndpointsForE2() throws Exception {
        String yaml = Files.readString(Path.of("src/main/resources/application.yml"));

        assertThat(yaml).contains("include: health,info,metrics");
        assertThat(yaml).contains("show-details: never");
        assertThat(yaml).contains("application: courselingo-pro");
        assertThat(yaml).contains("enabled: false");
        assertThat(yaml).doesNotContain("prometheus");
        assertThat(yaml).doesNotContain("configprops");
        assertThat(yaml).doesNotContain("heapdump");
        assertThat(yaml).doesNotContain("threaddump");
        assertThat(yaml).doesNotContain("loggers");
    }

    @Test
    void metricsPackageDoesNotIntroduceTracingOrExternalAiCalls() throws Exception {
        Path sourceDir = Path.of("src/main/java/com/example/courselingo/common/metrics");
        if (!Files.exists(sourceDir)) {
            return;
        }
        String source = Files.walk(sourceDir)
            .filter(Files::isRegularFile)
            .map(path -> {
                try {
                    return Files.readString(path);
                } catch (Exception exception) {
                    throw new IllegalStateException(exception);
                }
            })
            .reduce("", String::concat);

        assertThat(source)
            .doesNotContain("Tracer")
            .doesNotContain("Span")
            .doesNotContain("OpenTelemetry")
            .doesNotContain("LangChain4j")
            .doesNotContain("OpenAi")
            .doesNotContain("SiliconFlow")
            .doesNotContain("Ffmpeg");
    }
}
