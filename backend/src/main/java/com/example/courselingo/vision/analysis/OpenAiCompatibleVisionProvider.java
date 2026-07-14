package com.example.courselingo.vision.analysis;

import com.example.courselingo.ai.llm.JavaHttpOpenAiCompatibleLlmClient;
import com.example.courselingo.ai.llm.OpenAiCompatibleChatCompletionRequest;
import com.example.courselingo.ai.llm.OpenAiCompatibleClientResponse;
import com.example.courselingo.ai.llm.OpenAiCompatibleLlmClient;
import com.example.courselingo.modelrouting.AiModelRoute;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.ByteArrayOutputStream;
import java.net.URI;
import java.net.URISyntaxException;
import java.nio.file.Files;
import java.time.Duration;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.function.Function;

public class OpenAiCompatibleVisionProvider implements VisionModelProvider {

    public static final String PROVIDER_NAME = "openai-compatible-vision";
    private static final String CHAT_COMPLETIONS_PATH = "/chat/completions";
    private static final String DEFAULT_API_PATH_PREFIX = "/v1";

    private final VisionAnalysisProperties properties;
    private final OpenAiCompatibleLlmClient client;
    private final Function<String, String> environment;
    private final ObjectMapper objectMapper;

    public OpenAiCompatibleVisionProvider(VisionAnalysisProperties properties) {
        this(
            properties,
            new JavaHttpOpenAiCompatibleLlmClient(properties == null ? Duration.ofSeconds(5) : properties.getTimeout()),
            System::getenv,
            new ObjectMapper()
        );
    }

    OpenAiCompatibleVisionProvider(
        VisionAnalysisProperties properties,
        OpenAiCompatibleLlmClient client,
        Function<String, String> environment,
        ObjectMapper objectMapper
    ) {
        this.properties = properties == null ? new VisionAnalysisProperties() : properties;
        this.client = client;
        this.environment = environment == null ? System::getenv : environment;
        this.objectMapper = objectMapper == null ? new ObjectMapper() : objectMapper;
    }

    @Override
    public String providerName() {
        return PROVIDER_NAME;
    }

    @Override
    public VisionAnalysisResult analyze(VisionAnalysisRequest request) {
        long started = System.nanoTime();
        AiModelRoute route = request.route();
        String model = route == null ? "" : route.modelName();
        int maxAttempts = maxAttempts(route);
        VisionAnalysisResult lastFailure = null;
        try {
            OpenAiCompatibleChatCompletionRequest clientRequest = toClientRequest(request);
            for (int attempt = 1; attempt <= maxAttempts; attempt++) {
                OpenAiCompatibleClientResponse response = client.complete(clientRequest);
                if (response.statusCode() >= 200 && response.statusCode() < 300) {
                    return mapSuccess(response, model, elapsedMillis(started));
                }
                lastFailure = VisionAnalysisResult.failed(
                    providerName(),
                    model,
                    elapsedMillis(started),
                    errorCode(response.statusCode()),
                    "Vision provider request failed"
                );
                if (!retryableStatus(response.statusCode())) {
                    break;
                }
            }
            return lastFailure == null
                ? VisionAnalysisResult.failed(providerName(), model, elapsedMillis(started), "VISION_PROVIDER_FAILED", "Vision provider request failed")
                : lastFailure;
        } catch (Exception exception) {
            lastFailure = VisionAnalysisResult.failed(
                providerName(),
                model,
                elapsedMillis(started),
                "VISION_PROVIDER_FAILED",
                safeFailureMessage(exception)
            );
            for (int attempt = 2; attempt <= maxAttempts; attempt++) {
                try {
                    OpenAiCompatibleClientResponse response = client.complete(toClientRequest(request));
                    if (response.statusCode() >= 200 && response.statusCode() < 300) {
                        return mapSuccess(response, model, elapsedMillis(started));
                    }
                    lastFailure = VisionAnalysisResult.failed(
                        providerName(),
                        model,
                        elapsedMillis(started),
                        errorCode(response.statusCode()),
                        "Vision provider request failed"
                    );
                    if (!retryableStatus(response.statusCode())) {
                        break;
                    }
                } catch (Exception retryException) {
                    lastFailure = VisionAnalysisResult.failed(
                        providerName(),
                        model,
                        elapsedMillis(started),
                        "VISION_PROVIDER_FAILED",
                        safeFailureMessage(retryException)
                    );
                }
            }
            return lastFailure;
        }
    }

    private static int maxAttempts(AiModelRoute route) {
        if (route == null || route.maxAttempts() == null) {
            return 1;
        }
        return Math.max(1, route.maxAttempts());
    }

    private static boolean retryableStatus(int statusCode) {
        return statusCode == 429 || statusCode >= 500;
    }

    private static String safeFailureMessage(Exception exception) {
        String message = exception.getMessage();
        return message == null || message.isBlank() ? "Vision provider request failed" : message;
    }

    OpenAiCompatibleChatCompletionRequest toClientRequest(VisionAnalysisRequest request) throws Exception {
        AiModelRoute route = request.route();
        if (route == null) {
            throw new IllegalArgumentException("vision model route is required");
        }
        String apiKey = environment.apply(route.apiKeyEnvName());
        if (apiKey == null || apiKey.isBlank()) {
            throw new IllegalArgumentException("vision model API key is required");
        }
        return new OpenAiCompatibleChatCompletionRequest(
            fixedChatCompletionsUri(route.baseUrl()),
            Map.of("Authorization", "Bearer " + apiKey.strip()),
            "POST",
            "application/json",
            jsonBody(request),
            requestTimeout(route)
        );
    }

    private String jsonBody(VisionAnalysisRequest request) throws Exception {
        Map<String, Object> imageUrl = Map.of(
            "url",
            "data:image/jpeg;base64," + java.util.Base64.getEncoder().encodeToString(imageBytes(request)),
            "detail",
            "low"
        );
        List<Map<String, Object>> content = List.of(
            Map.of("type", "text", "text", prompt(request)),
            Map.of("type", "image_url", "image_url", imageUrl)
        );
        Map<String, Object> userMessage = Map.of("role", "user", "content", content);
        Map<String, Object> body = new HashMap<>();
        body.put("model", request.route().modelName());
        body.put("messages", List.of(userMessage));
        body.put("temperature", request.route().temperature() == null ? 0.0d : request.route().temperature());
        body.put("max_tokens", request.route().maxTokens() == null ? 1024 : request.route().maxTokens());
        body.put("response_format", Map.of("type", "json_object"));
        body.put("stream", false);
        return objectMapper.writeValueAsString(body);
    }

    private byte[] imageBytes(VisionAnalysisRequest request) throws Exception {
        byte[] original = Files.readAllBytes(request.imagePath());
        java.awt.image.BufferedImage source = javax.imageio.ImageIO.read(new java.io.ByteArrayInputStream(original));
        if (source == null || source.getWidth() <= properties.getMaxImageWidth()) {
            return original;
        }
        int width = properties.getMaxImageWidth();
        int height = Math.max(1, Math.round(source.getHeight() * (width / (float) source.getWidth())));
        java.awt.image.BufferedImage target = new java.awt.image.BufferedImage(width, height, java.awt.image.BufferedImage.TYPE_INT_RGB);
        java.awt.Graphics2D graphics = target.createGraphics();
        try {
            graphics.setRenderingHint(java.awt.RenderingHints.KEY_INTERPOLATION, java.awt.RenderingHints.VALUE_INTERPOLATION_BILINEAR);
            graphics.drawImage(source, 0, 0, width, height, null);
        } finally {
            graphics.dispose();
        }
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        javax.imageio.ImageIO.write(target, "jpg", output);
        return output.toByteArray();
    }

    private VisionAnalysisResult mapSuccess(OpenAiCompatibleClientResponse response, String model, long durationMillis) throws Exception {
        JsonNode root = objectMapper.readTree(response.body());
        JsonNode choices = root.path("choices");
        if (!choices.isArray() || choices.isEmpty()) {
            return VisionAnalysisResult.failed(providerName(), model, durationMillis, "VISION_MALFORMED_RESPONSE", "Missing choices");
        }
        String content = choices.get(0).path("message").path("content").asText("");
        JsonNode analysis = objectMapper.readTree(stripJsonFence(content));
        String summary = analysis.path("summary").asText("").strip();
        String screenType = analysis.path("screenType").asText("").strip();
        List<String> elements = elements(analysis.path("detectedElements"));
        if (summary.isBlank() && elements.isEmpty()) {
            return VisionAnalysisResult.empty(providerName(), model, durationMillis);
        }
        return new VisionAnalysisResult(
            VisionAnalysisStatus.SUCCEEDED,
            screenType.isBlank() ? "OTHER" : screenType,
            summary,
            elements,
            providerName(),
            model,
            durationMillis,
            null,
            null
        );
    }

    private List<String> elements(JsonNode node) {
        if (!node.isArray()) {
            return List.of();
        }
        java.util.ArrayList<String> result = new java.util.ArrayList<>();
        for (JsonNode item : node) {
            String value = item.asText("").strip();
            if (!value.isBlank()) {
                result.add(value);
            }
        }
        return List.copyOf(result);
    }

    private static String prompt(VisionAnalysisRequest request) {
        String ocr = request.ocrText() == null || request.ocrText().isBlank()
            ? "No OCR text is available."
            : "OCR text:\n" + request.ocrText().strip();
        return """
            Analyze this course video keyframe. Return compact JSON only:
            {"screenType":"PPT|CODE|TERMINAL|WHITEBOARD|BROWSER|OTHER","summary":"short visual summary","detectedElements":["item"]}
            Do not infer beyond the visible frame.
            """
            + "\n" + ocr;
    }

    private URI fixedChatCompletionsUri(String baseUrl) throws URISyntaxException {
        if (baseUrl == null || baseUrl.isBlank()) {
            throw new IllegalArgumentException("base URL is required");
        }
        URI baseUri = new URI(baseUrl.strip());
        String scheme = baseUri.getScheme();
        if (scheme == null || (!scheme.equalsIgnoreCase("http") && !scheme.equalsIgnoreCase("https"))) {
            throw new IllegalArgumentException("base URL must use http or https");
        }
        String basePath = baseUri.getRawPath();
        if (basePath == null || basePath.isBlank() || "/".equals(basePath)) {
            basePath = DEFAULT_API_PATH_PREFIX;
        }
        String normalizedBasePath = basePath.endsWith("/") ? basePath.substring(0, basePath.length() - 1) : basePath;
        return new URI(
            scheme.toLowerCase(Locale.ROOT),
            baseUri.getRawAuthority(),
            normalizedBasePath + CHAT_COMPLETIONS_PATH,
            null,
            null
        );
    }

    private Duration requestTimeout(AiModelRoute route) {
        if (route != null && route.timeout() != null && !route.timeout().isNegative() && !route.timeout().isZero()) {
            return route.timeout();
        }
        return properties.getTimeout();
    }

    private static String stripJsonFence(String value) {
        String text = value == null ? "" : value.strip();
        if (text.startsWith("```")) {
            text = text.replaceFirst("^```[a-zA-Z]*\\s*", "");
            text = text.replaceFirst("\\s*```$", "");
        }
        return text.strip();
    }

    private static String errorCode(int statusCode) {
        if (statusCode == 401 || statusCode == 403) {
            return "VISION_PROVIDER_AUTH_FAILED";
        }
        if (statusCode == 429) {
            return "VISION_PROVIDER_RATE_LIMIT";
        }
        return "VISION_PROVIDER_HTTP_ERROR";
    }

    private static long elapsedMillis(long startedNanos) {
        return Duration.ofNanos(System.nanoTime() - startedNanos).toMillis();
    }
}
