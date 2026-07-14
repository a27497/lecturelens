package com.example.courselingo.vision.analysis;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.courselingo.ai.llm.OpenAiCompatibleChatCompletionRequest;
import com.example.courselingo.ai.llm.OpenAiCompatibleClientResponse;
import com.example.courselingo.ai.llm.OpenAiCompatibleLlmClient;
import com.example.courselingo.modelrouting.AiModelRoute;
import com.example.courselingo.modelrouting.AiModelStage;
import com.example.courselingo.modelrouting.ModelCapability;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.awt.Color;
import java.awt.image.BufferedImage;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Map;
import java.util.Set;
import javax.imageio.ImageIO;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class OpenAiCompatibleVisionProviderTest {

    @TempDir
    private Path tempDir;

    @Test
    void buildsOpenAiCompatibleVisionRequestAndParsesJsonResponse() throws Exception {
        String content = "{\\\"screenType\\\":\\\"PPT\\\","
            + "\\\"summary\\\":\\\"A slide title is visible\\\","
            + "\\\"detectedElements\\\":[\\\"title\\\",\\\"diagram\\\"]}";
        CapturingClient client = new CapturingClient("{\"choices\":[{\"message\":{\"content\":\"" + content + "\"}}]}");
        OpenAiCompatibleVisionProvider provider = new OpenAiCompatibleVisionProvider(
            new VisionAnalysisProperties(),
            client,
            key -> "VISION_TEST_KEY".equals(key) ? "test-api-key" : "",
            new ObjectMapper()
        );

        VisionAnalysisResult result = provider.analyze(new VisionAnalysisRequest(
            "task_1",
            9L,
            12_345L,
            imagePath(),
            "CourseLingo OCR",
            "",
            route()
        ));

        assertThat(result.status()).isEqualTo(VisionAnalysisStatus.SUCCEEDED);
        assertThat(result.screenType()).isEqualTo("PPT");
        assertThat(result.summary()).isEqualTo("A slide title is visible");
        assertThat(result.detectedElements()).containsExactly("title", "diagram");
        assertThat(client.request.headers()).containsEntry("Authorization", "Bearer test-api-key");
        assertThat(client.request.body())
            .contains("\"model\":\"qwen-vl\"")
            .contains("\"image_url\"")
            .contains("data:image/jpeg;base64,")
            .contains("CourseLingo OCR")
            .doesNotContain("test-api-key")
            .doesNotContain("objectKey");
    }

    @Test
    void missingApiKeyReturnsFailedWithoutCallingClient() throws Exception {
        CapturingClient client = new CapturingClient("{}");
        OpenAiCompatibleVisionProvider provider = new OpenAiCompatibleVisionProvider(
            new VisionAnalysisProperties(),
            client,
            key -> "",
            new ObjectMapper()
        );

        VisionAnalysisResult result = provider.analyze(new VisionAnalysisRequest(
            "task_1",
            9L,
            12_345L,
            imagePath(),
            "",
            "",
            route()
        ));

        assertThat(result.status()).isEqualTo(VisionAnalysisStatus.FAILED);
        assertThat(result.errorCode()).isEqualTo("VISION_PROVIDER_FAILED");
        assertThat(client.request).isNull();
    }

    @Test
    void providerHttpAuthFailureMapsToSafeErrorCode() throws Exception {
        CapturingClient client = new CapturingClient(401, "{\"error\":\"bad key\"}");
        OpenAiCompatibleVisionProvider provider = new OpenAiCompatibleVisionProvider(
            new VisionAnalysisProperties(),
            client,
            key -> "test-api-key",
            new ObjectMapper()
        );

        VisionAnalysisResult result = provider.analyze(new VisionAnalysisRequest(
            "task_1",
            9L,
            12_345L,
            imagePath(),
            "",
            "",
            route()
        ));

        assertThat(result.status()).isEqualTo(VisionAnalysisStatus.FAILED);
        assertThat(result.errorCode()).isEqualTo("VISION_PROVIDER_AUTH_FAILED");
        assertThat(result.errorMessage()).isEqualTo("Vision provider request failed");
    }

    @Test
    void retriesRetryableProviderFailuresWithinRouteLimit() throws Exception {
        String content = "{\\\"screenType\\\":\\\"BROWSER\\\","
            + "\\\"summary\\\":\\\"A web page is visible\\\","
            + "\\\"detectedElements\\\":[\\\"navigation\\\"]}";
        SequenceClient client = new SequenceClient(
            new OpenAiCompatibleClientResponse(500, "{\"error\":\"temporary\"}", Map.of(), Duration.ofMillis(10)),
            new OpenAiCompatibleClientResponse(200, "{\"choices\":[{\"message\":{\"content\":\"" + content + "\"}}]}", Map.of(), Duration.ofMillis(10))
        );
        OpenAiCompatibleVisionProvider provider = new OpenAiCompatibleVisionProvider(
            new VisionAnalysisProperties(),
            client,
            key -> "test-api-key",
            new ObjectMapper()
        );

        VisionAnalysisResult result = provider.analyze(new VisionAnalysisRequest(
            "task_1",
            9L,
            12_345L,
            imagePath(),
            "",
            "",
            route(2)
        ));

        assertThat(result.status()).isEqualTo(VisionAnalysisStatus.SUCCEEDED);
        assertThat(result.screenType()).isEqualTo("BROWSER");
        assertThat(client.calls).isEqualTo(2);
    }

    private Path imagePath() throws Exception {
        Path path = tempDir.resolve("frame.jpg");
        BufferedImage image = new BufferedImage(32, 18, BufferedImage.TYPE_INT_RGB);
        var graphics = image.createGraphics();
        try {
            graphics.setColor(Color.WHITE);
            graphics.fillRect(0, 0, 32, 18);
            graphics.setColor(Color.BLACK);
            graphics.drawString("CL", 4, 12);
        } finally {
            graphics.dispose();
        }
        ImageIO.write(image, "jpg", path.toFile());
        return path;
    }

    private static AiModelRoute route() {
        return route(1);
    }

    private static AiModelRoute route(int maxAttempts) {
        return new AiModelRoute(
            AiModelStage.VISION_FRAME_ANALYSIS,
            "qwen-vl",
            "Qwen VL",
            OpenAiCompatibleVisionProvider.PROVIDER_NAME,
            "https://example.test/v1",
            "qwen-vl",
            "VISION_TEST_KEY",
            Set.of(ModelCapability.VISION, ModelCapability.JSON_OUTPUT),
            0.0,
            1200,
            Duration.ofSeconds(60),
            maxAttempts
        );
    }

    private static final class CapturingClient implements OpenAiCompatibleLlmClient {
        private final int statusCode;
        private final String body;
        private OpenAiCompatibleChatCompletionRequest request;

        private CapturingClient(String body) {
            this(200, body);
        }

        private CapturingClient(int statusCode, String body) {
            this.statusCode = statusCode;
            this.body = body;
        }

        @Override
        public OpenAiCompatibleClientResponse complete(OpenAiCompatibleChatCompletionRequest request) {
            this.request = request;
            return new OpenAiCompatibleClientResponse(statusCode, body, Map.of(), Duration.ofMillis(10));
        }
    }

    private static final class SequenceClient implements OpenAiCompatibleLlmClient {
        private final OpenAiCompatibleClientResponse[] responses;
        private int calls;

        private SequenceClient(OpenAiCompatibleClientResponse... responses) {
            this.responses = responses;
        }

        @Override
        public OpenAiCompatibleClientResponse complete(OpenAiCompatibleChatCompletionRequest request) {
            int index = Math.min(calls, responses.length - 1);
            calls++;
            return responses[index];
        }
    }
}
