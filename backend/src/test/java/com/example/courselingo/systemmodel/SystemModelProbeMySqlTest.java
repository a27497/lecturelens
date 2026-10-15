package com.example.courselingo.systemmodel;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.courselingo.ai.llm.*;
import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.entity.UserRole;
import com.example.courselingo.auth.service.AdminAuthorizationService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.web.GlobalExceptionHandler;
import com.example.courselingo.modelrouting.*;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.support.StaticListableBeanFactory;
import org.springframework.mock.env.MockEnvironment;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;

import java.net.*;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;

@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@EnabledIfEnvironmentVariable(named = "SYSTEM_MODEL_TEST_JDBC_URL", matches = ".+")
class SystemModelProbeMySqlTest {
    private static final String KEY = "synthetic-probe-key-4268";
    private static final String ALLOW =
            "https://api.deepseek.com,https://bailian.example,https://silicon.example";
    private static final ObjectMapper JSON = new ObjectMapper();
    private final SystemModelSecretCipher cipher =
            new SystemModelSecretCipher(SystemModelSecretCipherTest.TEST_KEY);
    private SystemModelMySqlFixture db;
    private SystemModelRegistry registry;
    private SystemModelUrlPolicy urls;
    private SystemModelHttpClient http;
    private SystemModelProbeService probes;
    private long user;
    private SystemModelEnvironment.Captured defaults;

    @BeforeAll
    void database() throws Exception {
        db = new SystemModelMySqlFixture();
    }

    @AfterAll
    void cleanup() throws Exception {
        if (db != null) db.close();
    }

    @BeforeEach
    void prepare() {
        urls =
                new SystemModelUrlPolicy(
                        host -> new InetAddress[] {InetAddress.getByName("8.8.8.8")});
        var routing = new AiModelRoutingProperties();
        routing.setEnabled(false);
        defaults =
                new SystemModelEnvironment(
                                new MockEnvironment()
                                        .withProperty("courselingo.ai.asr.provider", "mock"),
                                new AiModelRouter(routing),
                                new OpenAiCompatibleLlmProperties(),
                                cipher)
                        .capture();
        registry = new SystemModelRegistry(db.jdbc, db.transactions, cipher, urls, defaults);
        registry.initialize();
        if (!registry.catalog().bindings().isEmpty()) {
            var clear = new HashMap<String, Long>();
            registry.catalog().bindings().keySet().forEach(k -> clear.put(k, null));
            registry.bindings(
                    new SystemModelCommands.Bindings(registry.currentVersion(), clear), 1);
        }
        http = mock(SystemModelHttpClient.class);
        probes = new SystemModelProbeService(registry, urls, http, ALLOW, Duration.ofSeconds(2), 2);
        user = db.user();
    }

    @AfterEach
    void closeProbe() {
        if (probes != null) probes.close();
    }

    private long target(SystemModelProtocol protocol) {
        String url =
                switch (protocol) {
                    case OPENAI_CHAT -> "https://api.deepseek.com";
                    case BAILIAN_ASR ->
                            "https://bailian.example/api/v1/services/aigc/multimodal-generation/generation";
                    case SILICONFLOW_ASR -> "https://silicon.example/custom-prefix";
                };
        long p =
                registry.saveProvider(
                                null,
                                new SystemModelCommands.Provider(
                                        registry.currentVersion(),
                                        "probe-provider",
                                        protocol,
                                        url,
                                        true,
                                        KEY,
                                        false),
                                user)
                        .providers()
                        .getLast()
                        .id();
        return registry.saveModel(
                        null,
                        p,
                        new SystemModelCommands.Model(
                                registry.currentVersion(),
                                protocol == SystemModelProtocol.BAILIAN_ASR
                                        ? "qwen-audio-3.1-asr-flash"
                                        : "test-model",
                                protocol == SystemModelProtocol.OPENAI_CHAT
                                        ? Set.of("TEXT_CHAT", "JSON_OUTPUT")
                                        : Set.of("ASR"),
                                null,
                                true),
                        user)
                .models()
                .getLast()
                .id();
    }

    private static OpenAiCompatibleClientResponse response(int status, String body) {
        return new OpenAiCompatibleClientResponse(status, body, Map.of(), Duration.ofMillis(1));
    }

    private static String validChat(String content) throws Exception {
        return JSON.writeValueAsString(
                Map.of("choices", List.of(Map.of("message", Map.of("content", content)))));
    }

    private SystemModelProbeService.Result probe(long model) {
        return probes.probe(
                new SystemModelProbeService.Command(registry.currentVersion(), model), user);
    }

    @Test
    void textProbeSendsSmallStrictJsonRequestAndDoesNotWriteVersionsAuditOrExecutions()
            throws Exception {
        long model = target(SystemModelProtocol.OPENAI_CHAT);
        long version = registry.currentVersion();
        long audits = db.jdbc.queryForObject("SELECT COUNT(*) FROM system_model_audit", Long.class);
        when(http.post(any(), anyMap(), anyString(), any(byte[].class), any()))
                .thenAnswer(
                        call -> {
                            assertThat(call.<URI>getArgument(0).toString())
                                    .isEqualTo("https://api.deepseek.com/chat/completions");
                            Map<String, String> headers = call.getArgument(1);
                            assertThat(headers.get("Authorization")).isEqualTo("Bearer " + KEY);
                            var body = JSON.readTree((byte[]) call.getArgument(3));
                            assertThat(body.path("response_format").path("type").asText())
                                    .isEqualTo("json_object");
                            assertThat(body.path("max_tokens").asInt()).isEqualTo(32);
                            assertThat(body.path("messages").size()).isEqualTo(1);
                            assertThat(call.<Duration>getArgument(4))
                                    .isEqualTo(Duration.ofSeconds(2));
                            return response(200, validChat("{\"ok\":true}"));
                        });
        var result = probe(model);
        assertThat(result.ok()).isTrue();
        assertThat(result.version()).isEqualTo(version);
        assertThat(result.finalUrl()).isEqualTo("https://api.deepseek.com/chat/completions");
        assertThat(JSON.writeValueAsString(result))
                .doesNotContain(KEY, "choices", "content", "ciphertext");
        assertThat(registry.currentVersion()).isEqualTo(version);
        assertThat(db.jdbc.queryForObject("SELECT COUNT(*) FROM system_model_audit", Long.class))
                .isEqualTo(audits);
        assertThat(
                        db.jdbc.queryForObject(
                                "SELECT COUNT(*) FROM system_model_execution_snapshot", Long.class))
                .isZero();
        observe(result);
    }

    @Test
    void qwenProbeUsesTheSameNonThinkingOptionsAsTheRuntimeJsonPath() throws Exception {
        long model = target(SystemModelProtocol.OPENAI_CHAT);
        long provider =
                registry.catalog().models().stream()
                        .filter(m -> m.id() == model)
                        .findFirst()
                        .orElseThrow()
                        .providerId();
        registry.saveModel(
                model,
                provider,
                new SystemModelCommands.Model(
                        registry.currentVersion(),
                        "Qwen/Qwen3-8B",
                        Set.of("TEXT_CHAT", "JSON_OUTPUT"),
                        null,
                        true),
                user);
        when(http.post(any(), anyMap(), anyString(), any(byte[].class), any()))
                .thenAnswer(
                        call -> {
                            assertThat(
                                            JSON.readTree((byte[]) call.getArgument(3))
                                                    .path("enable_thinking")
                                                    .asBoolean(true))
                                    .isFalse();
                            return response(200, validChat("{\"ok\":true}"));
                        });
        assertThat(probe(model).ok()).isTrue();
    }

    @ParameterizedTest
    @ValueSource(strings = {"BAILIAN_ASR", "SILICONFLOW_ASR"})
    void asrUsesAuthorizedBundledFixtureAndNeverReturnsTranscript(String protocol)
            throws Exception {
        long model = target(SystemModelProtocol.valueOf(protocol));
        when(http.post(any(), anyMap(), anyString(), any(byte[].class), any()))
                .thenAnswer(
                        call -> {
                            URI uri = call.getArgument(0);
                            assertThat(uri.getPath())
                                    .isEqualTo(
                                            protocol.equals("BAILIAN_ASR")
                                                    ? "/api/v1/services/aigc/multimodal-generation/generation"
                                                    : "/v1/audio/transcriptions");
                            var body = (byte[]) call.getArgument(3);
                            assertThat(body.length).isBetween(32044, 60000);
                            if (protocol.equals("BAILIAN_ASR")) {
                                String data =
                                        JSON.readTree(body)
                                                .path("input")
                                                .path("messages")
                                                .path(0)
                                                .path("content")
                                                .path(0)
                                                .path("input_audio")
                                                .path("data")
                                                .asText();
                                byte[] audio =
                                        Base64.getDecoder()
                                                .decode(data.substring(data.indexOf(',') + 1));
                                assertThat(
                                                java.util.HexFormat.of()
                                                        .formatHex(
                                                                java.security.MessageDigest
                                                                        .getInstance("SHA-256")
                                                                        .digest(audio)))
                                        .isEqualTo(probes.policy().asrFixtureSha256());
                            } else
                                assertThat(
                                                new String(
                                                        body,
                                                        java.nio.charset.StandardCharsets
                                                                .ISO_8859_1))
                                        .contains("RIFF", "WAVE");
                            return response(
                                    200,
                                    protocol.equals("BAILIAN_ASR")
                                            ? "{\"output\":{\"text\":\"private-probe-transcript\"}}"
                                            : "{\"text\":\"private-probe-transcript\"}");
                        });
        var result = probe(model);
        assertThat(result.ok()).isTrue();
        assertThat(JSON.writeValueAsString(result)).doesNotContain("private-probe-transcript", KEY);
        observe(result);
    }

    @ParameterizedTest
    @ValueSource(ints = {400, 401, 403, 404, 408, 429, 500})
    void vendorErrorsOnlyReturnClosedCategoryAndElapsedTime(int status) {
        long model = target(SystemModelProtocol.OPENAI_CHAT);
        when(http.post(any(), anyMap(), anyString(), any(byte[].class), any()))
                .thenReturn(response(status, KEY));
        var result = probe(model);
        assertThat(result.ok()).isFalse();
        assertThat(result.category())
                .isEqualTo(
                        switch (status) {
                            case 401, 403 -> "AUTHENTICATION";
                            case 404 -> "MODEL_NOT_FOUND";
                            case 408 -> "TIMEOUT";
                            case 429 -> "RATE_LIMIT";
                            case 500 -> "SERVER_ERROR";
                            default -> "INVALID_REQUEST";
                        });
        assertThat(result.elapsedMillis()).isGreaterThanOrEqualTo(0);
        verify(http).post(any(), anyMap(), anyString(), any(byte[].class), any());
    }

    @ParameterizedTest
    @ValueSource(strings = {"{", "[]", "{} trailing", "{\"x\":1,\"x\":2}"})
    void invalidJsonIsNotReportedAsConnected(String content) throws Exception {
        long model = target(SystemModelProtocol.OPENAI_CHAT);
        when(http.post(any(), anyMap(), anyString(), any(byte[].class), any()))
                .thenReturn(response(200, validChat(content)));
        assertThat(probe(model).category()).isEqualTo("OUTPUT_INVALID");
    }

    @ParameterizedTest
    @ValueSource(strings = {"TIMEOUT", "REDIRECT_FORBIDDEN", "RESPONSE_TOO_LARGE", "NETWORK"})
    void boundedHttpErrorsAreSanitized(String category) {
        long model = target(SystemModelProtocol.OPENAI_CHAT);
        when(http.post(any(), anyMap(), anyString(), any(byte[].class), any()))
                .thenThrow(
                        new SystemModelCallFailure(
                                category, LlmProviderFailureCategory.NETWORK, null, false));
        assertThat(probe(model).category()).isEqualTo(category);
    }

    @Test
    void missingWhitelistAndDifferentOriginsNeverSendRequests() {
        long model = target(SystemModelProtocol.OPENAI_CHAT);
        for (String origins :
                List.of(
                        "",
                        "https://api.deepseek.com.evil.example",
                        "http://api.deepseek.com",
                        "https://api.deepseek.com:8443")) {
            try (var denied =
                    new SystemModelProbeService(
                            registry, urls, http, origins, Duration.ofSeconds(1), 2)) {
                assertThat(
                                denied.probe(
                                                new SystemModelProbeService.Command(
                                                        registry.currentVersion(), model),
                                                user)
                                        .category())
                        .isEqualTo("ORIGIN_NOT_ALLOWED");
            }
        }
        verify(http, never()).post(any(), anyMap(), anyString(), any(byte[].class), any());
    }

    @Test
    void mixedDnsIsBlockedEvenForWhitelistedOrigin() {
        long model = target(SystemModelProtocol.OPENAI_CHAT);
        var mixed =
                new SystemModelUrlPolicy(
                        host ->
                                new InetAddress[] {
                                    InetAddress.getByName("8.8.8.8"),
                                    InetAddress.getByName("169.254.169.254")
                                });
        try (var denied =
                new SystemModelProbeService(
                        registry, mixed, http, ALLOW, Duration.ofSeconds(1), 2)) {
            assertThat(
                            denied.probe(
                                            new SystemModelProbeService.Command(
                                                    registry.currentVersion(), model),
                                            user)
                                    .category())
                    .isEqualTo("ADDRESS_FORBIDDEN");
        }
        verify(http, never()).post(any(), anyMap(), anyString(), any(byte[].class), any());
    }

    @Test
    void staleExpectedVersionIs409BeforeAnyRequest() {
        long model = target(SystemModelProtocol.OPENAI_CHAT);
        assertThatThrownBy(
                        () ->
                                probes.probe(
                                        new SystemModelProbeService.Command(
                                                registry.currentVersion() - 1, model),
                                        user))
                .isInstanceOfSatisfying(
                        BusinessException.class,
                        e ->
                                assertThat(e.errorCode())
                                        .isEqualTo(ErrorCode.SYSTEM_MODEL_CONFIG_CONFLICT));
        verify(http, never()).post(any(), anyMap(), anyString(), any(byte[].class), any());
    }

    @Test
    void statusIsLocalMaskedAndReflectsModeAndMissingRoute() throws Exception {
        long model = target(SystemModelProtocol.OPENAI_CHAT);
        registry.bindings(
                new SystemModelCommands.Bindings(
                        registry.currentVersion(), Map.of("TRANSLATION_FULL_TEXT", model)),
                user);
        var status =
                new SystemModelStatusService(registry, new MockEnvironment())
                        .inspect(registry.currentVersion());
        assertThat(status.features())
                .filteredOn(f -> f.key().equals("TRANSLATION_FULL_TEXT"))
                .singleElement()
                .satisfies(
                        f -> {
                            assertThat(f.source()).isEqualTo("DATABASE");
                            assertThat(f.active()).isTrue();
                            assertThat(f.finalUrl())
                                    .isEqualTo("https://api.deepseek.com/chat/completions");
                            assertThat(f.configurationStatus()).isEqualTo("READY");
                        });
        assertThat(status.features())
                .filteredOn(f -> f.key().equals("SUBTITLE_TRANSLATION"))
                .singleElement()
                .satisfies(f -> assertThat(f.active()).isFalse());
        assertThat(status.features())
                .filteredOn(f -> f.key().equals("VISION_FRAME_ANALYSIS"))
                .singleElement()
                .satisfies(f -> assertThat(f.active()).isFalse());
        assertThat(status.features())
                .filteredOn(f -> f.key().equals("FUSION_SUMMARY"))
                .singleElement()
                .satisfies(f -> assertThat(f.connected()).isFalse());
        String safe = JSON.writeValueAsString(status);
        assertThat(safe).doesNotContain(KEY, "ciphertext");
        for (var p : registry.load(status.version()).providers())
            assertThat(safe).doesNotContain(p.ciphertext());
        verify(http, never()).post(any(), anyMap(), anyString(), any(byte[].class), any());
    }

    @Test
    void wrongMasterKeyIsVisibleInStatusAndProbeWithoutExposingCiphertext() {
        long model = target(SystemModelProtocol.OPENAI_CHAT);
        registry.bindings(
                new SystemModelCommands.Bindings(
                        registry.currentVersion(), Map.of("COURSE_QA", model)),
                user);
        byte[] wrong = new byte[32];
        Arrays.fill(wrong, (byte) 9);
        var broken =
                new SystemModelRegistry(
                        db.jdbc,
                        db.transactions,
                        new SystemModelSecretCipher(Base64.getEncoder().encodeToString(wrong)),
                        urls,
                        defaults);
        assertThat(
                        new SystemModelStatusService(broken, new MockEnvironment())
                                .inspect(registry.currentVersion())
                                .features())
                .filteredOn(f -> f.key().equals("COURSE_QA"))
                .singleElement()
                .satisfies(f -> assertThat(f.configurationStatus()).isEqualTo("KEY_UNAVAILABLE"));
        try (var service =
                new SystemModelProbeService(broken, urls, http, ALLOW, Duration.ofSeconds(1), 2)) {
            assertThat(
                            service.probe(
                                            new SystemModelProbeService.Command(
                                                    registry.currentVersion(), model),
                                            user)
                                    .category())
                    .isEqualTo("KEY_UNAVAILABLE");
        }
        verify(http, never()).post(any(), anyMap(), anyString(), any(byte[].class), any());
    }

    @Test
    void newApisRequireAdminAndResponsesNeverContainStoredCiphertextOrVendorMessage()
            throws Exception {
        long model = target(SystemModelProtocol.OPENAI_CHAT);
        when(http.post(any(), anyMap(), anyString(), any(byte[].class), any()))
                .thenReturn(response(401, KEY));
        var authorization =
                new AdminAuthorizationService(
                        header -> {
                            if (header == null)
                                throw new BusinessException(ErrorCode.COMMON_UNAUTHORIZED);
                            return new CurrentUserResponse(
                                    user,
                                    "test@example.invalid",
                                    "ACTIVE",
                                    header.equals("admin") ? UserRole.ADMIN : UserRole.USER);
                        });
        class Interceptors extends InterceptorRegistry {
            List<Object> all() {
                return getInterceptors();
            }
        }
        var interceptors = new Interceptors();
        new SystemModelAdminWebConfiguration(
                        new StaticListableBeanFactory(
                                        Map.of("adminAuthorizationService", authorization))
                                .getBeanProvider(AdminAuthorizationService.class))
                .addInterceptors(interceptors);
        var mvc =
                MockMvcBuilders.standaloneSetup(
                                new SystemModelOperationsController(
                                        new SystemModelStatusService(
                                                registry, new MockEnvironment()),
                                        probes))
                        .setControllerAdvice(new GlobalExceptionHandler())
                        .addInterceptors(
                                interceptors.all().stream()
                                        .map(i -> (HandlerInterceptor) i)
                                        .toArray(HandlerInterceptor[]::new))
                        .build();
        String base = "/api/admin/system-models";
        var requests =
                List.of(
                        get(base + "/status")
                                .param("version", Long.toString(registry.currentVersion())),
                        get(base + "/probe-policy"),
                        post(base + "/probes")
                                .contentType("application/json")
                                .content(
                                        JSON.writeValueAsString(
                                                new SystemModelProbeService.Command(
                                                        registry.currentVersion(), model))));
        for (var request : requests) {
            mvc.perform(request).andExpect(status().isUnauthorized());
            mvc.perform(request.header("Authorization", "user")).andExpect(status().isForbidden());
            String body =
                    mvc.perform(
                                    request.with(
                                            mockRequest -> {
                                                mockRequest.removeHeader("Authorization");
                                                mockRequest.addHeader("Authorization", "admin");
                                                return mockRequest;
                                            }))
                            .andExpect(status().isOk())
                            .andReturn()
                            .getResponse()
                            .getContentAsString();
            assertThat(body).doesNotContain(KEY, "ciphertext");
            for (var p : registry.load(registry.currentVersion()).providers())
                assertThat(body).doesNotContain(p.ciphertext());
        }
        verify(http).post(any(), anyMap(), anyString(), any(byte[].class), any());
    }

    private static synchronized void observe(SystemModelProbeService.Result result)
            throws Exception {
        String directory = System.getenv("SYSTEM_MODEL_VERIFICATION_DIR");
        if (directory == null || directory.isBlank()) return;
        Path path = Path.of(directory).resolve("probes.jsonl");
        Files.createDirectories(path.getParent());
        Files.writeString(
                path,
                JSON.writeValueAsString(result) + "\n",
                StandardOpenOption.CREATE,
                StandardOpenOption.APPEND);
    }
}
