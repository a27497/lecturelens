package com.example.courselingo.ai.llm;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

class DemoMockLlmProviderTest {

    @Test
    void returnsDeterministicAlignedTranslationsWithoutUsingPromptContent() {
        DemoMockLlmProvider provider = new DemoMockLlmProvider();
        LlmRequest request = request(
            Map.of("translationMode", "alignedBatch", "sourceSegmentCount", 2),
            LlmResponseFormat.JSON_OBJECT
        );

        LlmResult first = provider.generate(request);
        LlmResult second = provider.generate(request);

        assertThat(first.content()).isEqualTo(second.content());
        assertThat(first.content())
            .isEqualTo("{\"segments\":[{\"index\":0,\"text\":\"这是第 1 段本地演示翻译，用于验证时间轴对齐。\"},{\"index\":1,\"text\":\"这是第 2 段本地演示翻译，用于验证时间轴对齐。\"}]}")
            .doesNotContain("private prompt content");
        assertThat(first.metadata()).containsEntry("demo", true).containsEntry("externalCalls", 0);
    }

    @Test
    void returnsValidDemoLearningPackageAndPlainTextTranslation() {
        DemoMockLlmProvider provider = new DemoMockLlmProvider();

        assertThat(provider.generate(request(Map.of("sourceSegmentCount", 1), LlmResponseFormat.JSON_OBJECT)).content())
            .contains("\"summary\"")
            .contains("\"keyPoints\"")
            .contains("\"glossary\"")
            .contains("\"qa\"")
            .contains("本地演示");
        assertThat(provider.generate(request(Map.of("segmentIndex", 0), LlmResponseFormat.TEXT)).content())
            .isEqualTo("这是由本地 Demo Provider 生成的中文演示翻译。");
    }

    @Test
    void isDisabledByDefaultAndDoesNotReplaceAnExistingRealProvider() {
        new ApplicationContextRunner()
            .withUserConfiguration(DemoMockLlmConfiguration.class)
            .run(context -> assertThat(context).doesNotHaveBean(DemoMockLlmProvider.class));

        new ApplicationContextRunner()
            .withUserConfiguration(DemoMockLlmConfiguration.class)
            .withPropertyValues("courselingo.ai.llm.demo-mock.enabled=true")
            .run(context -> assertThat(context).hasSingleBean(DemoMockLlmProvider.class));

        new ApplicationContextRunner()
            .withUserConfiguration(ExistingProviderConfiguration.class, DemoMockLlmConfiguration.class)
            .withPropertyValues("courselingo.ai.llm.demo-mock.enabled=true")
            .run(context -> {
                assertThat(context).hasSingleBean(LlmProvider.class);
                assertThat(context).doesNotHaveBean(DemoMockLlmProvider.class);
                assertThat(context.getBean(LlmProvider.class).providerName()).isEqualTo("existing-real-provider");
            });
    }

    @Test
    void demoImplementationContainsNoNetworkingOrCredentialHandling() throws IOException {
        String source = Files.readString(Path.of(
            "src/main/java/com/example/courselingo/ai/llm/DemoMockLlmProvider.java"
        ));

        assertThat(source)
            .doesNotContain("HttpClient", "WebClient", "RestTemplate", "OkHttp", "Authorization", "apiKey")
            .doesNotContain("request.messages()", "System.getenv");
    }

    private static LlmRequest request(Map<String, Object> metadata, LlmResponseFormat format) {
        return new LlmRequest(
            "req_demo",
            "task_demo",
            List.of(new LlmMessage(LlmRole.USER, "private prompt content")),
            Duration.ofSeconds(5),
            0.0,
            1024,
            metadata,
            format
        );
    }

    @Configuration(proxyBeanMethods = false)
    static class ExistingProviderConfiguration {

        @Bean
        LlmProvider existingProvider() {
            return new LlmProvider() {
                @Override
                public LlmResult generate(LlmRequest request) {
                    throw new UnsupportedOperationException("not used");
                }

                @Override
                public String providerName() {
                    return "existing-real-provider";
                }
            };
        }
    }
}
