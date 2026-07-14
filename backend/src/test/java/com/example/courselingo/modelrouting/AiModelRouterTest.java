package com.example.courselingo.modelrouting;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.courselingo.ai.llm.LlmMessage;
import com.example.courselingo.ai.llm.LlmRequest;
import com.example.courselingo.ai.llm.LlmResponseFormat;
import com.example.courselingo.ai.llm.LlmRole;
import java.time.Duration;
import java.util.EnumSet;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class AiModelRouterTest {

    @Test
    void routesTranslationFullTextToConfiguredProfile() {
        AiModelRouter router = new AiModelRouter(properties());

        AiModelRoute route = router.route(AiModelStage.TRANSLATION_FULL_TEXT);

        assertThat(route.profileCode()).isEqualTo("deepseek-text");
        assertThat(route.modelName()).isEqualTo("deepseek-ai/DeepSeek-V4-Pro");
        assertThat(route.providerType()).isEqualTo("openai-compatible");
    }

    @Test
    void routesSubtitleTranslationToConfiguredProfile() {
        AiModelRouter router = new AiModelRouter(properties());

        AiModelRoute route = router.route(AiModelStage.SUBTITLE_TRANSLATION);

        assertThat(route.profileCode()).isEqualTo("deepseek-text");
    }

    @Test
    void routesLearningPackageToConfiguredProfile() {
        AiModelRouter router = new AiModelRouter(properties());

        AiModelRoute route = router.route(AiModelStage.LEARNING_PACKAGE);

        assertThat(route.profileCode()).isEqualTo("deepseek-text");
    }

    @Test
    void missingRouteFailsFast() {
        AiModelRoutingProperties properties = properties();
        properties.setRoutes(Map.of(AiModelStage.SUBTITLE_TRANSLATION, "deepseek-text"));

        assertThatThrownBy(() -> new AiModelRouter(properties))
            .isInstanceOf(ModelRoutingException.class)
            .hasMessageContaining("TRANSLATION_FULL_TEXT")
            .satisfies(error -> assertSafe(error.getMessage()));
    }

    @Test
    void missingProfileFailsFast() {
        AiModelRoutingProperties properties = properties();
        properties.setRoutes(Map.of(
            AiModelStage.TRANSLATION_FULL_TEXT, "missing-profile",
            AiModelStage.SUBTITLE_TRANSLATION, "deepseek-text",
            AiModelStage.LEARNING_PACKAGE, "deepseek-text",
            AiModelStage.COURSE_QA, "deepseek-text",
            AiModelStage.COURSE_CHAPTER, "deepseek-text"
        ));

        assertThatThrownBy(() -> new AiModelRouter(properties))
            .isInstanceOf(ModelRoutingException.class)
            .hasMessageContaining("missing-profile")
            .satisfies(error -> assertSafe(error.getMessage()));
    }

    @Test
    void disabledProfileFailsFast() {
        AiModelRoutingProperties properties = properties();
        properties.getProfiles().get("deepseek-text").setEnabled(false);

        assertThatThrownBy(() -> new AiModelRouter(properties))
            .isInstanceOf(ModelRoutingException.class)
            .hasMessageContaining("disabled")
            .satisfies(error -> assertSafe(error.getMessage()));
    }

    @Test
    void missingTextChatCapabilityFailsFast() {
        AiModelRoutingProperties properties = properties();
        properties.getProfiles().get("deepseek-text").setCapabilities(EnumSet.of(ModelCapability.JSON_OUTPUT));

        assertThatThrownBy(() -> new AiModelRouter(properties))
            .isInstanceOf(ModelRoutingException.class)
            .hasMessageContaining("TEXT_CHAT")
            .satisfies(error -> assertSafe(error.getMessage()));
    }

    @Test
    void missingJsonOutputCapabilityFailsFast() {
        AiModelRoutingProperties properties = properties();
        properties.getProfiles().get("deepseek-text").setCapabilities(EnumSet.of(ModelCapability.TEXT_CHAT));

        assertThatThrownBy(() -> new AiModelRouter(properties))
            .isInstanceOf(ModelRoutingException.class)
            .hasMessageContaining("JSON_OUTPUT")
            .satisfies(error -> assertSafe(error.getMessage()));
    }

    @Test
    void routedRequestAppliesProfileWithoutLeakingApiKeyEnvValue() {
        AiModelRoutedLlmRequestFactory factory = new AiModelRoutedLlmRequestFactory(new AiModelRouter(properties()));

        LlmRequest routed = factory.apply(AiModelStage.LEARNING_PACKAGE, request());

        assertThat(routed.timeout()).isEqualTo(Duration.ofSeconds(900));
        assertThat(routed.temperature()).isEqualTo(0.0d);
        assertThat(routed.maxTokens()).isEqualTo(32768);
        assertThat(routed.maxAttempts()).isEqualTo(1);
        assertThat(routed.metadata())
            .containsEntry(AiModelRoutedLlmRequestFactory.METADATA_STAGE, "LEARNING_PACKAGE")
            .containsEntry(AiModelRoutedLlmRequestFactory.METADATA_PROFILE_CODE, "deepseek-text")
            .containsEntry(AiModelRoutedLlmRequestFactory.METADATA_MODEL_NAME, "deepseek-ai/DeepSeek-V4-Pro")
            .containsEntry(AiModelRoutedLlmRequestFactory.METADATA_BASE_URL, "https://api.siliconflow.cn/v1");
        assertSafe(routed.metadata().toString());
    }

    @Test
    void disabledRoutingKeepsOldRequestCompatible() {
        AiModelRoutingProperties properties = properties();
        properties.setEnabled(false);
        AiModelRoutedLlmRequestFactory factory = new AiModelRoutedLlmRequestFactory(new AiModelRouter(properties));
        LlmRequest request = request();

        LlmRequest routed = factory.apply(AiModelStage.LEARNING_PACKAGE, request);

        assertThat(routed).isSameAs(request);
    }

    private static AiModelRoutingProperties properties() {
        AiModelRoutingProperties properties = new AiModelRoutingProperties();
        properties.setEnabled(true);
        properties.setRoutes(Map.of(
            AiModelStage.TRANSLATION_FULL_TEXT, "deepseek-text",
            AiModelStage.SUBTITLE_TRANSLATION, "deepseek-text",
            AiModelStage.LEARNING_PACKAGE, "deepseek-text",
            AiModelStage.COURSE_QA, "deepseek-text",
            AiModelStage.COURSE_CHAPTER, "deepseek-text"
        ));
        AiModelProfile profile = new AiModelProfile();
        profile.setDisplayName("DeepSeek Text");
        profile.setProviderType("openai-compatible");
        profile.setBaseUrl("https://api.siliconflow.cn/v1");
        profile.setModelName("deepseek-ai/DeepSeek-V4-Pro");
        profile.setApiKeyEnvName("OPENAI_COMPATIBLE_API_KEY");
        profile.setCapabilities(EnumSet.of(ModelCapability.TEXT_CHAT, ModelCapability.JSON_OUTPUT));
        profile.setTemperature(0.0d);
        profile.setMaxTokens(32768);
        profile.setTimeout(Duration.ofSeconds(900));
        profile.setMaxAttempts(1);
        profile.setEnabled(true);
        properties.setProfiles(Map.of("deepseek-text", profile));
        return properties;
    }

    private static LlmRequest request() {
        return new LlmRequest(
            "req_1",
            "task_1",
            List.of(new LlmMessage(LlmRole.USER, "Build a learning package.")),
            Duration.ofSeconds(30),
            0.7d,
            512,
            2,
            Map.of("safe", true),
            LlmResponseFormat.JSON_OBJECT
        );
    }

    private static void assertSafe(String value) {
        assertThat(value)
            .doesNotContain("api-key-value")
            .doesNotContain("Bearer")
            .doesNotContain("Authorization")
            .doesNotContain("token")
            .doesNotContain("secret");
    }
}
