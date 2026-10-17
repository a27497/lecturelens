package com.example.courselingo.systemmodel;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.example.courselingo.ai.asr.*;
import com.example.courselingo.ai.llm.*;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.modelrouting.*;
import com.example.courselingo.task.runner.AsrPipelineTestHarness;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.mock.env.MockEnvironment;

import java.net.*;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

import javax.sound.sampled.*;

@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@EnabledIfEnvironmentVariable(named = "SYSTEM_MODEL_TEST_JDBC_URL", matches = ".+")
class SystemModelAsrMySqlTest {
    private static final String FEATURE = "ASR_TRANSCRIPTION";
    private static final String KEY_A = "synthetic-asr-a-key-1264",
            KEY_B = "synthetic-asr-b-key-9857";
    private static final ObjectMapper JSON = new ObjectMapper();
    private final SystemModelSecretCipher cipher =
            new SystemModelSecretCipher(SystemModelSecretCipherTest.TEST_KEY);
    private SystemModelMySqlFixture db;
    private SystemModelRegistry registry;
    private SystemModelExecutionService executions;
    private SystemModelHttpClient http;
    private SystemModelAsrProvider runtime;
    private SystemModelUrlPolicy urls;
    private long user;
    @TempDir Path temporary;
    private Path audio;

    @BeforeAll
    void database() throws Exception {
        db = new SystemModelMySqlFixture();
    }

    @AfterAll
    void cleanup() throws Exception {
        if (db != null) db.close();
    }

    @BeforeEach
    void prepare() throws Exception {
        urls =
                new SystemModelUrlPolicy(
                        host -> new InetAddress[] {InetAddress.getByName("8.8.8.8")});
        registry = registry(defaultEnvironment(), cipher);
        registry.initialize();
        if (!registry.catalog().bindings().isEmpty()) {
            var clear = new HashMap<String, Long>();
            registry.catalog().bindings().keySet().forEach(key -> clear.put(key, null));
            registry.bindings(
                    new SystemModelCommands.Bindings(registry.currentVersion(), clear), 1);
        }
        executions = new SystemModelExecutionService(db.jdbc, registry, db.transactions);
        http = mock(SystemModelHttpClient.class);
        runtime = runtime(executions);
        user = db.user();
        audio = temporary.resolve("short.wav");
        try (var stream =
                new AudioInputStream(
                        new java.io.ByteArrayInputStream(new byte[32000]),
                        new AudioFormat(16000, 16, 1, true, false),
                        16000)) {
            AudioSystem.write(stream, AudioFileFormat.Type.WAVE, audio.toFile());
        }
    }

    private MockEnvironment defaultEnvironment() {
        return new MockEnvironment()
                .withProperty("courselingo.ai.asr.provider", "mock")
                .withProperty("courselingo.ai.asr.mock.default-text", "Frozen mock transcript");
    }

    private SystemModelRegistry registry(MockEnvironment env, SystemModelSecretCipher key) {
        var routing = new AiModelRoutingProperties();
        routing.setEnabled(false);
        return new SystemModelRegistry(
                db.jdbc,
                db.transactions,
                key,
                urls,
                new SystemModelEnvironment(
                                env,
                                new AiModelRouter(routing),
                                new OpenAiCompatibleLlmProperties(),
                                key)
                        .capture());
    }

    private SystemModelAsrProvider runtime(SystemModelExecutionService service) {
        return new SystemModelAsrProvider(
                service,
                List.of(
                        AsrAdapterFactories.bailian(http, urls),
                        AsrAdapterFactories.siliconFlow(http, urls)));
    }

    private record Target(long provider, long model) {}

    private Target target(SystemModelProtocol protocol, String key) {
        String endpoint =
                protocol == SystemModelProtocol.BAILIAN_ASR
                        ? "https://bailian.example/api/v1/services/aigc/multimodal-generation/generation"
                        : "https://silicon.example/custom-prefix";
        long provider =
                registry.saveProvider(
                                null,
                                new SystemModelCommands.Provider(
                                        registry.currentVersion(),
                                        protocol.name(),
                                        protocol,
                                        endpoint,
                                        true,
                                        key,
                                        false),
                                user)
                        .providers()
                        .getLast()
                        .id();
        long model =
                registry.saveModel(
                                null,
                                provider,
                                new SystemModelCommands.Model(
                                        registry.currentVersion(),
                                        protocol == SystemModelProtocol.BAILIAN_ASR
                                                ? "qwen-audio-3.1-asr-flash"
                                                : "test/asr-model",
                                        Set.of("ASR"),
                                        new SystemModelViews.Parameters(null, null, 5000L, 2),
                                        true),
                                user)
                        .models()
                        .getLast()
                        .id();
        return new Target(provider, model);
    }

    private void bind(long model) {
        registry.bindings(
                new SystemModelCommands.Bindings(registry.currentVersion(), Map.of(FEATURE, model)),
                user);
    }

    private SystemModelExecutionRef freeze() {
        return executions.freezePipeline(db.task(user), user);
    }

    private SpeechToTextResult call(SystemModelExecutionRef ref) {
        return runtime.forExecution(ref).transcribe(request(ref));
    }

    private SpeechToTextRequest request(SystemModelExecutionRef ref) {
        return new SpeechToTextRequest(
                audio, "en", "mock-asr-request", ref.taskId(), Duration.ofSeconds(5));
    }

    private static OpenAiCompatibleClientResponse response(int status, String body) {
        return new OpenAiCompatibleClientResponse(status, body, Map.of(), Duration.ofMillis(1));
    }

    private static String payload(URI uri) {
        return uri.getHost().equals("bailian.example")
                ? "{\"output\":{\"text\":\"Bailian transcript\"}}"
                : "{\"text\":\"Silicon transcript\"}";
    }

    @Test
    void concurrentChunksRetriesAndMergeStayOnAWhileNewTaskUsesBThenRollbackCreatesC()
            throws Exception {
        var a = target(SystemModelProtocol.BAILIAN_ASR, KEY_A);
        var b = target(SystemModelProtocol.SILICONFLOW_ASR, KEY_B);
        var unaffected = new HashMap<>(registry.catalog().effective());
        unaffected.remove(FEATURE);
        bind(a.model());
        var refA = freeze();
        var activeA = new AtomicReference<>(refA);
        var activeB = new AtomicReference<SystemModelExecutionRef>();
        var bothStarted = new CountDownLatch(2);
        var release = new CountDownLatch(1);
        var sequence = new AtomicInteger();
        var observations = new CopyOnWriteArrayList<String>();
        when(http.post(any(), anyMap(), anyString(), any(byte[].class), any()))
                .thenAnswer(
                        invocation -> {
                            URI uri = invocation.getArgument(0);
                            Map<String, String> headers = invocation.getArgument(1);
                            if (uri.getHost().equals("bailian.example")) {
                                assertThat(headers.get("Authorization"))
                                        .isEqualTo("Bearer " + KEY_A);
                                int attempt = sequence.incrementAndGet();
                                bothStarted.countDown();
                                assertThat(release.await(10, TimeUnit.SECONDS)).isTrue();
                                observations.add("A:" + uri);
                                observe(
                                        activeA.get(),
                                        uri,
                                        "bailian",
                                        attempt == 1 ? 429 : 200,
                                        "runtime-switch");
                                if (attempt == 1) return response(429, KEY_A);
                            } else {
                                assertThat(headers.get("Authorization"))
                                        .isEqualTo("Bearer " + KEY_B);
                                observations.add("B:" + uri);
                                observe(activeB.get(), uri, "siliconflow", 200, "runtime-switch");
                            }
                            return response(200, payload(uri));
                        });
        try (var workers = Executors.newSingleThreadExecutor()) {
            var running =
                    workers.submit(
                            () ->
                                    AsrPipelineTestHarness.run(
                                            runtime, refA, temporary.resolve("A"), audio));
            try {
                assertThat(bothStarted.await(10, TimeUnit.SECONDS)).isTrue();
                // No notification consumer is installed: the task-start DB fence is authoritative.
                registry.notifier(
                        ignored -> {
                            throw new IllegalStateException("notification dropped");
                        });
                bind(b.model());
                var refB = freeze();
                activeB.set(refB);
                var resultB =
                        AsrPipelineTestHarness.run(runtime, refB, temporary.resolve("B"), audio);
                assertThat(refB.configVersion()).isGreaterThan(refA.configVersion());
                assertThat(resultB.provider()).isEqualTo("siliconflow");
                assertThat(resultB.metadata())
                        .containsEntry("systemModelConfigVersion", refB.configVersion());
                release.countDown();
                var resultA = running.get(10, TimeUnit.SECONDS);
                assertThat(resultA.provider()).isEqualTo("bailian");
                assertThat(resultA.metadata())
                        .containsEntry("chunkCount", 2)
                        .containsEntry("systemModelSnapshotId", refA.snapshotId())
                        .containsEntry("systemModelConfigVersion", refA.configVersion());
                assertThat(sequence.get()).isEqualTo(3);
                assertThat(observations).filteredOn(v -> v.startsWith("A:")).hasSize(3);
                assertThat(observations).filteredOn(v -> v.startsWith("B:")).hasSize(2);
                assertThat(executions.pipeline(refA.taskId(), user)).isEqualTo(refA);
                registry.rollback(
                        new SystemModelCommands.Rollback(
                                registry.currentVersion(), FEATURE, refA.configVersion()),
                        user);
                var refC = freeze();
                activeA.set(refC);
                assertThat(refC.configVersion()).isGreaterThan(refB.configVersion());
                assertThat(call(refC).provider()).isEqualTo("bailian");
                var effective = new HashMap<>(registry.catalog().effective());
                effective.remove(FEATURE);
                assertThat(effective).isEqualTo(unaffected);
                assertThat(executions.query(refA.snapshotId()).configVersion())
                        .isEqualTo(refA.configVersion());
            } finally {
                release.countDown();
            }
        }
    }

    @Test
    void concurrentExpectedVersionSavesHaveExactlyOneWinner() throws Exception {
        var a = target(SystemModelProtocol.BAILIAN_ASR, KEY_A);
        var b = target(SystemModelProtocol.SILICONFLOW_ASR, KEY_B);
        long version = registry.currentVersion();
        var start = new CountDownLatch(1);
        try (var workers = Executors.newFixedThreadPool(2)) {
            var results = new ArrayList<Future<Boolean>>();
            for (var target : List.of(a, b))
                results.add(
                        workers.submit(
                                () -> {
                                    start.await();
                                    try {
                                        registry.bindings(
                                                new SystemModelCommands.Bindings(
                                                        version, Map.of(FEATURE, target.model())),
                                                user);
                                        return true;
                                    } catch (BusinessException failure) {
                                        assertThat(failure.errorCode())
                                                .isEqualTo(ErrorCode.SYSTEM_MODEL_CONFIG_CONFLICT);
                                        return false;
                                    }
                                }));
            start.countDown();
            assertThat(
                            List.of(
                                    results.get(0).get(10, TimeUnit.SECONDS),
                                    results.get(1).get(10, TimeUnit.SECONDS)))
                    .containsExactlyInAnyOrder(true, false);
            assertThat(registry.currentVersion()).isEqualTo(version + 1);
        }
    }

    @ParameterizedTest
    @ValueSource(strings = {"BAILIAN_ASR", "SILICONFLOW_ASR"})
    void realAdaptersSerializeFrozenEndpointModelAndCredentialsWithoutMakingNetworkCalls(
            String protocol) throws Exception {
        var t = target(SystemModelProtocol.valueOf(protocol), KEY_A);
        bind(t.model());
        var ref = freeze();
        when(http.post(any(), anyMap(), anyString(), any(byte[].class), any()))
                .thenAnswer(
                        invocation -> {
                            URI uri = invocation.getArgument(0);
                            Map<String, String> headers = invocation.getArgument(1);
                            String body =
                                    new String(
                                            (byte[]) invocation.getArgument(3),
                                            java.nio.charset.StandardCharsets.UTF_8);
                            assertThat(headers.get("Authorization")).isEqualTo("Bearer " + KEY_A);
                            assertThat(body)
                                    .contains(
                                            protocol.equals("BAILIAN_ASR")
                                                    ? "qwen-audio-3.1-asr-flash"
                                                    : "test/asr-model");
                            assertThat(uri.getPath())
                                    .isEqualTo(
                                            protocol.equals("BAILIAN_ASR")
                                                    ? "/api/v1/services/aigc/multimodal-generation/generation"
                                                    : "/v1/audio/transcriptions");
                            assertThat(invocation.<Duration>getArgument(4))
                                    .isEqualTo(Duration.ofSeconds(5));
                            observe(ref, uri, protocol, 200, "serialization");
                            return response(200, payload(uri));
                        });
        assertThat(call(ref).fullText()).endsWith("transcript");
        String stored =
                db.jdbc.queryForObject(
                        "SELECT resolved_config_json FROM system_model_execution_snapshot WHERE"
                                + " id=?",
                        String.class,
                        ref.snapshotId());
        assertThat(stored).doesNotContain(KEY_A, "ciphertext", "v1.");
        String history = JSON.writeValueAsString(registry.version(ref.configVersion()));
        String execution = JSON.writeValueAsString(executions.query(ref.snapshotId()));
        assertThat(history + execution)
                .contains("hasKey", "keyLast4")
                .doesNotContain(KEY_A, "ciphertext");
        for (var provider : registry.load(ref.configVersion()).providers())
            assertThat(history + execution).doesNotContain(provider.ciphertext());
    }

    @ParameterizedTest
    @ValueSource(ints = {400, 401, 403, 404, 408, 429, 500})
    void httpFailuresAreExplicitAndNeverFallBackToConfiguredMock(int status) {
        var t = target(SystemModelProtocol.SILICONFLOW_ASR, KEY_A);
        bind(t.model());
        var ref = freeze();
        when(http.post(any(), anyMap(), anyString(), any(byte[].class), any()))
                .thenReturn(response(status, KEY_A));
        assertThatThrownBy(() -> call(ref))
                .isInstanceOfSatisfying(
                        AsrProviderException.class,
                        failure -> {
                            assertThat(failure.statusCode()).contains(status);
                            assertThat(failure.retryable())
                                    .isEqualTo(status == 408 || status == 429 || status >= 500);
                            assertThat(failure.getCause()).isNull();
                            assertThat(failure).hasMessageNotContaining(KEY_A);
                        });
        verify(http).post(any(), anyMap(), anyString(), any(byte[].class), any());
    }

    @ParameterizedTest
    @ValueSource(strings = {"BAILIAN_ASR", "SILICONFLOW_ASR"})
    void invalidJsonAndTimeoutDoNotUseMockOrExposePayload(String protocol) {
        bind(target(SystemModelProtocol.valueOf(protocol), KEY_A).model());
        var ref = freeze();
        when(http.post(any(), anyMap(), anyString(), any(byte[].class), any()))
                .thenReturn(response(200, KEY_A));
        assertThatThrownBy(() -> call(ref))
                .isInstanceOf(AsrProviderException.class)
                .hasMessageNotContaining(KEY_A)
                .hasNoCause();
        when(http.post(any(), anyMap(), anyString(), any(byte[].class), any()))
                .thenThrow(
                        new SystemModelCallFailure(
                                "TIMEOUT", LlmProviderFailureCategory.TIMEOUT, null, true));
        assertThatThrownBy(() -> call(ref))
                .isInstanceOfSatisfying(
                        AsrProviderException.class,
                        failure -> assertThat(failure.retryable()).isTrue())
                .hasNoCause();
    }

    @ParameterizedTest
    @ValueSource(strings = {"REDIRECT_FORBIDDEN", "RESPONSE_TOO_LARGE"})
    void boundedTransportRejectionIsNonRetryableForBothAdapters(String category) {
        for (var protocol :
                List.of(SystemModelProtocol.BAILIAN_ASR, SystemModelProtocol.SILICONFLOW_ASR)) {
            bind(target(protocol, KEY_A).model());
            var ref = freeze();
            when(http.post(any(), anyMap(), anyString(), any(byte[].class), any()))
                    .thenThrow(
                            new SystemModelCallFailure(
                                    category,
                                    LlmProviderFailureCategory.OUTPUT_INVALID,
                                    null,
                                    false));
            assertThatThrownBy(() -> call(ref))
                    .isInstanceOfSatisfying(
                            AsrCallFailure.class,
                            failure -> {
                                assertThat(failure.category().name()).isEqualTo(category);
                                assertThat(failure.retryable()).isFalse();
                            })
                    .hasNoCause();
        }
    }

    @Test
    void invalidBailianModelFailsWithoutHttpOrFallback() {
        var t = target(SystemModelProtocol.BAILIAN_ASR, KEY_A);
        registry.saveModel(
                t.model(),
                t.provider(),
                new SystemModelCommands.Model(
                        registry.currentVersion(), "unverified-model", Set.of("ASR"), null, true),
                user);
        bind(t.model());
        assertThatThrownBy(() -> call(freeze()))
                .isInstanceOfSatisfying(
                        AsrCallFailure.class,
                        failure ->
                                assertThat(failure.category())
                                        .isEqualTo(AsrCallFailure.Category.INVALID_REQUEST));
        verifyNoInteractions(http);
    }

    @Test
    void dnsChangeToMixedPublicAndPrivateAddressesIsRejectedBeforeHttp() {
        bind(target(SystemModelProtocol.SILICONFLOW_ASR, KEY_A).model());
        var ref = freeze();
        var denied =
                new SystemModelUrlPolicy(
                        host ->
                                new InetAddress[] {
                                    InetAddress.getByName("8.8.8.8"),
                                    InetAddress.getByName("127.0.0.1")
                                });
        var provider =
                new SystemModelAsrProvider(
                        executions, List.of(AsrAdapterFactories.siliconFlow(http, denied)));
        assertThatThrownBy(() -> provider.forExecution(ref).transcribe(request(ref)))
                .isInstanceOf(AsrProviderException.class)
                .hasNoCause();
        verifyNoInteractions(http);
    }

    @Test
    void undecryptableCredentialFailsBeforeAnyAdapterHttpAndDoesNotFallback() {
        bind(target(SystemModelProtocol.BAILIAN_ASR, KEY_A).model());
        var ref = freeze();
        var wrong =
                registry(
                        defaultEnvironment(),
                        new SystemModelSecretCipher(
                                Base64.getEncoder()
                                        .encodeToString(
                                                new byte[] {
                                                    1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
                                                    1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1
                                                })));
        var broken = runtime(new SystemModelExecutionService(db.jdbc, wrong, db.transactions));
        assertThatThrownBy(() -> broken.forExecution(ref))
                .isInstanceOf(BusinessException.class)
                .hasMessageNotContaining(KEY_A)
                .hasNoCause();
        verifyNoInteractions(http);
    }

    @Test
    void mockAndDisabledDefaultsAreFrozenAndExplicitProviderWinsLegacyFlags() {
        var mock = freeze();
        assertThat(call(mock).fullText()).isEqualTo("Frozen mock transcript");
        var env =
                defaultEnvironment()
                        .withProperty("courselingo.ai.asr.provider", "none")
                        .withProperty("courselingo.ai.asr.mock.enabled", "true")
                        .withProperty("courselingo.ai.asr.bailian.enabled", "true")
                        .withProperty(
                                "courselingo.ai.asr.mock.default-text", "Changed mock transcript");
        registry(env, cipher).initialize();
        var none = freeze();
        assertThat(executions.route(none, FEATURE).source()).isEqualTo("UNCONFIGURED");
        assertThatThrownBy(() -> call(none)).isInstanceOf(BusinessException.class);
        assertThat(call(mock).fullText()).isEqualTo("Frozen mock transcript");
        verifyNoInteractions(http);
    }

    @ParameterizedTest
    @ValueSource(strings = {"bailian", "siliconflow"})
    void unboundEnvironmentProviderAndEnabledFlagsRetainFrozenKeyAndSettings(String selected) {
        var env =
                new MockEnvironment()
                        .withProperty(
                                "courselingo.ai.asr."
                                        + (selected.equals("bailian") ? "bailian" : "silicon-flow")
                                        + ".enabled",
                                "true")
                        .withProperty("courselingo.ai.asr.bailian.api-key", KEY_A)
                        .withProperty("courselingo.ai.asr.silicon-flow.api-key", KEY_B)
                        .withProperty("courselingo.ai.asr.silicon-flow.model", "legacy-silicon");
        registry(env, cipher).initialize();
        var old = freeze();
        var route = executions.route(old, FEATURE);
        assertThat(route.source()).isEqualTo("ENV");
        assertThat(route.protocol())
                .isEqualTo(
                        selected.equals("bailian")
                                ? SystemModelProtocol.BAILIAN_ASR
                                : SystemModelProtocol.SILICONFLOW_ASR);
        assertThat(executions.credential(old, FEATURE))
                .isEqualTo(selected.equals("bailian") ? KEY_A : KEY_B);
        assertThat(runtime.forExecution(old).providerName()).isEqualTo(selected);
        env.withProperty("courselingo.ai.asr.provider", "mock");
        registry(env, cipher).initialize();
        assertThat(runtime.forExecution(freeze()).providerName()).isEqualTo("mock");
        assertThat(runtime.forExecution(old).providerName()).isEqualTo(selected);
        verifyNoInteractions(http);
    }

    @Test
    void wrongProtocolCapabilitiesAndBoundDisableAreRejected() {
        var t = target(SystemModelProtocol.SILICONFLOW_ASR, KEY_A);
        assertThatThrownBy(
                        () ->
                                registry.bindings(
                                        new SystemModelCommands.Bindings(
                                                registry.currentVersion(),
                                                Map.of("COURSE_QA", t.model())),
                                        user))
                .isInstanceOf(BusinessException.class);
        bind(t.model());
        assertThatThrownBy(
                        () ->
                                registry.saveModel(
                                        t.model(),
                                        t.provider(),
                                        new SystemModelCommands.Model(
                                                registry.currentVersion(),
                                                "bad-capabilities",
                                                Set.of("TEXT_CHAT", "JSON_OUTPUT"),
                                                null,
                                                true),
                                        user))
                .isInstanceOf(BusinessException.class);
        assertThatThrownBy(
                        () ->
                                registry.saveProvider(
                                        t.provider(),
                                        new SystemModelCommands.Provider(
                                                registry.currentVersion(),
                                                "disabled",
                                                SystemModelProtocol.SILICONFLOW_ASR,
                                                "https://silicon.example",
                                                false,
                                                null,
                                                false),
                                        user))
                .isInstanceOf(BusinessException.class);
        assertThatThrownBy(() -> runtime.transcribe(request(freeze())))
                .isInstanceOf(BusinessException.class);
    }

    @Test
    void rotationDeletionAndRollbackToDeploymentDefaultDoNotChangeOldTaskCredentials() {
        long defaultVersion = registry.currentVersion();
        var t = target(SystemModelProtocol.SILICONFLOW_ASR, KEY_A);
        bind(t.model());
        var old = freeze();
        registry.saveProvider(
                t.provider(),
                new SystemModelCommands.Provider(
                        registry.currentVersion(),
                        "rotated",
                        SystemModelProtocol.SILICONFLOW_ASR,
                        "https://silicon.example/custom-prefix",
                        true,
                        KEY_B,
                        false),
                user);
        var rotated = freeze();
        var observed = new ArrayList<String>();
        when(http.post(any(), anyMap(), anyString(), any(byte[].class), any()))
                .thenAnswer(
                        invocation -> {
                            Map<String, String> headers = invocation.getArgument(1);
                            observed.add(headers.get("Authorization"));
                            return response(200, "{\"text\":\"Frozen credential transcript\"}");
                        });
        call(old);
        call(rotated);
        assertThat(observed).containsExactly("Bearer " + KEY_A, "Bearer " + KEY_B);
        registry.rollback(
                new SystemModelCommands.Rollback(
                        registry.currentVersion(), FEATURE, defaultVersion),
                user);
        assertThat(call(freeze()).provider()).isEqualTo("mock");
        registry.delete("MODEL", t.model(), registry.currentVersion(), user);
        registry.delete("PROVIDER", t.provider(), registry.currentVersion(), user);
        call(old);
        assertThat(observed.getLast()).isEqualTo("Bearer " + KEY_A);
    }

    @Test
    void taskScopeAndCancellationAreCheckedByPinnedAdapter() {
        var ref = freeze();
        var pinned = runtime.forExecution(ref);
        assertThatThrownBy(
                        () ->
                                pinned.transcribe(
                                        new SpeechToTextRequest(
                                                audio,
                                                "en",
                                                "req",
                                                "other-task",
                                                Duration.ofSeconds(1))))
                .isInstanceOf(BusinessException.class);
        db.jdbc.update("UPDATE analysis_task SET status='CANCELED' WHERE id=?", ref.taskId());
        assertThatThrownBy(() -> pinned.transcribe(request(ref)))
                .isInstanceOf(BusinessException.class);
        verifyNoInteractions(http);
    }

    private static synchronized void observe(
            SystemModelExecutionRef ref, URI uri, String provider, int status, String scenario)
            throws Exception {
        String directory = System.getenv("SYSTEM_MODEL_VERIFICATION_DIR");
        if (directory == null || directory.isBlank()) return;
        Path path = Path.of(directory).resolve("asr-requests.jsonl");
        Files.createDirectories(path.getParent());
        Files.writeString(
                path,
                JSON.writeValueAsString(
                                Map.of(
                                        "scenario",
                                        scenario,
                                        "snapshotId",
                                        ref.snapshotId(),
                                        "version",
                                        ref.configVersion(),
                                        "provider",
                                        provider,
                                        "finalUrl",
                                        uri.toString(),
                                        "status",
                                        status,
                                        "transport",
                                        "mock"))
                        + "\n",
                StandardOpenOption.CREATE,
                StandardOpenOption.APPEND);
    }
}
