package com.example.courselingo.systemmodel;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
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
import com.example.courselingo.subtitle.domain.*;
import com.example.courselingo.subtitle.mapper.*;
import com.example.courselingo.subtitle.service.*;
import com.example.courselingo.vision.analysis.*;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.support.StaticListableBeanFactory;
import org.springframework.mock.env.MockEnvironment;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;

import java.nio.file.Path;
import java.time.Clock;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@EnabledIfEnvironmentVariable(named = "SYSTEM_MODEL_TEST_JDBC_URL", matches = ".+")
class SystemModelRuntimeMySqlTest {
    private static final String ENV_KEY = "synthetic-env-text-key-5531",
            VISION_KEY = "synthetic-env-vision-key-6942";
    private static final String KEY_A = "synthetic-provider-a-key-1984",
            KEY_B = "synthetic-provider-b-key-2756";
    private static final ObjectMapper JSON = new ObjectMapper();
    private SystemModelMySqlFixture db;
    private SystemModelRegistry registry;
    private SystemModelExecutionService executions;
    private AiModelRouter router;
    private SystemModelUrlPolicy urls;
    private long user;
    private String task;
    private final SystemModelSecretCipher cipher =
            new SystemModelSecretCipher(SystemModelSecretCipherTest.TEST_KEY);

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
                        host ->
                                new java.net.InetAddress[] {
                                    java.net.InetAddress.getByName("8.8.8.8")
                                });
        var routing = new AiModelRoutingProperties();
        var profile = new AiModelProfile();
        profile.setProviderType("openai-compatible");
        profile.setBaseUrl("https://legacy.example/v1");
        profile.setModelName("legacy-model");
        profile.setApiKeyEnvName("TEST_VISION_KEY");
        profile.setCapabilities(
                Set.of(
                        ModelCapability.TEXT_CHAT,
                        ModelCapability.JSON_OUTPUT,
                        ModelCapability.VISION));
        routing.setProfiles(Map.of("legacy", profile));
        var stages = new EnumMap<AiModelStage, String>(AiModelStage.class);
        for (var stage : AiModelStage.values()) stages.put(stage, "legacy");
        routing.setRoutes(stages);
        router = new AiModelRouter(routing);
        registry = registry(true, true, cipher);
        registry.initialize();
        if (!registry.catalog().bindings().isEmpty()) {
            var clear = new LinkedHashMap<String, Long>();
            registry.catalog().bindings().keySet().forEach(key -> clear.put(key, null));
            registry.bindings(
                    new SystemModelCommands.Bindings(registry.currentVersion(), clear), 1);
        }
        executions = new SystemModelExecutionService(db.jdbc, registry, db.transactions);
        user = db.user();
        task = db.task(user);
    }

    @Test
    void disablingRejectsActiveSnapshotsAndDoesNotRebindFinishedPipelineRetries() {
        executions.freezePipeline(task, user);
        var guard = new SystemModelDisabledTaskGuard(db.jdbc);
        assertThatThrownBy(() -> guard.requireLegacyTask(task))
                .isInstanceOf(BusinessException.class).hasNoCause();
        guard.requireLegacyTask(db.task(user));
        db.jdbc.update("UPDATE analysis_task SET status='QUEUED' WHERE id=?", task);
        assertThatThrownBy(() -> new SystemModelDisabledTaskGuard(db.jdbc))
                .isInstanceOf(BusinessException.class).hasNoCause();
        db.jdbc.update("UPDATE analysis_task SET status='CANCELED' WHERE id=?", task);
        assertThat(db.jdbc.queryForObject("SELECT count(*) FROM system_model_execution_snapshot WHERE task_id=?", Long.class, task)).isEqualTo(1L);
    }

    @Test
    void missingSnapshotTableAfterV25CannotAuthorizeLegacyExecution() {
        executions.freezePipeline(task, user);
        db.jdbc.execute("RENAME TABLE system_model_execution_snapshot TO preserved_review_snapshot");
        try {
            assertThatThrownBy(() -> new SystemModelDisabledTaskGuard(db.jdbc))
                    .isInstanceOf(BusinessException.class).hasNoCause();
            var guard = new SystemModelDisabledTaskGuard(db.jdbc, false);
            assertThatThrownBy(() -> guard.requireLegacyTask(task))
                    .isInstanceOf(BusinessException.class).hasNoCause();
        } finally {
            db.jdbc.execute("RENAME TABLE preserved_review_snapshot TO system_model_execution_snapshot");
        }
        assertThat(executions.pipeline(task, user).taskId()).isEqualTo(task);
    }

    @Test
    void revokedSnapshotReadPermissionCannotMasqueradeAsLegacySchema() throws Exception {
        executions.freezePipeline(task, user);
        String account = "scope_guard_" + UUID.randomUUID().toString().replace("-", "").substring(0, 12);
        db.jdbc.execute("CREATE USER '" + account + "'@'%' IDENTIFIED BY 'synthetic-guard-test-only'");
        try {
            db.jdbc.execute("GRANT SELECT ON `" + db.database + "`.analysis_task TO '" + account + "'@'%'");
            var restricted = new org.springframework.jdbc.datasource.DriverManagerDataSource(db.url, account, "synthetic-guard-test-only");
            try (var connection = restricted.getConnection();
                    var tables = connection.getMetaData().getTables(connection.getCatalog(), null, "system_model_execution_snapshot", new String[]{"TABLE"})) {
                assertThat(tables.next()).isFalse();
            }
            var guard = new SystemModelDisabledTaskGuard(new org.springframework.jdbc.core.JdbcTemplate(restricted), false);
            assertThatThrownBy(() -> guard.requireLegacyTask(task))
                    .isInstanceOf(BusinessException.class).hasNoCause();
        } finally { db.jdbc.execute("DROP USER '" + account + "'@'%'"); }
    }

    private SystemModelRegistry registry(
            boolean full, boolean real, SystemModelSecretCipher encryption) {
        var properties = new OpenAiCompatibleLlmProperties();
        properties.setEnabled(real);
        properties.setApiKey(ENV_KEY);
        properties.setModel("legacy-model");
        var env =
                new MockEnvironment()
                        .withProperty(
                                "courselingo.subtitle.translation.full-text.enabled",
                                Boolean.toString(full))
                        .withProperty(
                                "courselingo.ai.llm.demo-mock.enabled", Boolean.toString(!real))
                        .withProperty("TEST_VISION_KEY", VISION_KEY);
        return new SystemModelRegistry(
                db.jdbc,
                db.transactions,
                encryption,
                urls,
                new SystemModelEnvironment(env, router, properties, encryption).capture());
    }

    private record Target(long provider, long model) {}

    private Target target(String name, String base, String key) {
        var providers =
                registry.saveProvider(
                                null,
                                new SystemModelCommands.Provider(
                                        registry.currentVersion(),
                                        name,
                                        SystemModelProtocol.OPENAI_CHAT,
                                        base,
                                        true,
                                        key,
                                        false),
                                user)
                        .providers();
        long provider = providers.getLast().id();
        var models =
                registry.saveModel(
                                null,
                                provider,
                                new SystemModelCommands.Model(
                                        registry.currentVersion(),
                                        name,
                                        Set.of("TEXT_CHAT", "JSON_OUTPUT", "VISION"),
                                        null,
                                        true),
                                user)
                        .models();
        return new Target(provider, models.getLast().id());
    }

    private void bind(String feature, long model) {
        registry.bindings(
                new SystemModelCommands.Bindings(registry.currentVersion(), Map.of(feature, model)),
                user);
    }

    private LlmRequest request(SystemModelExecutionRef ref, AiModelStage stage) {
        return new AiModelRoutedLlmRequestFactory(router, executions)
                .apply(
                        stage,
                        new LlmRequest(
                                        "req_" + UUID.randomUUID(),
                                        ref.taskId(),
                                        List.of(
                                                new LlmMessage(
                                                        LlmRole.USER,
                                                        "Return JSON: {\"ok\":true}")),
                                        Duration.ofSeconds(10),
                                        0d,
                                        64,
                                        1,
                                        Map.of(),
                                        LlmResponseFormat.JSON_OBJECT)
                                .withExecution(ref));
    }

    private static OpenAiCompatibleClientResponse response(int status, String content) {
        try {
            return new OpenAiCompatibleClientResponse(
                    status,
                    status == 200
                            ? JSON.writeValueAsString(
                                    Map.of(
                                            "choices",
                                            List.of(
                                                    Map.of(
                                                            "message",
                                                            Map.of("content", content),
                                                            "finish_reason",
                                                            "stop")),
                                            "usage",
                                            Map.of(
                                                    "prompt_tokens",
                                                    2,
                                                    "completion_tokens",
                                                    3,
                                                    "total_tokens",
                                                    5)))
                            : content,
                    Map.of(),
                    Duration.ofMillis(1));
        } catch (Exception failure) {
            throw new AssertionError(failure);
        }
    }

    @Test
    void enabledRuntimeBootstrapsAndSelectsRoutingProviders() {
        new org.springframework.boot.test.context.runner.ApplicationContextRunner()
                .withUserConfiguration(SystemModelRuntimeConfiguration.class,
                        com.example.courselingo.ai.asr.BailianAsrConfiguration.class,
                        com.example.courselingo.ai.asr.SiliconFlowAsrConfiguration.class,
                        com.example.courselingo.ai.asr.MockAsrConfiguration.class)
                .withBean(SystemModelSecretCipher.class, () -> cipher)
                .withBean(org.springframework.jdbc.core.JdbcTemplate.class, () -> db.jdbc)
                .withBean(
                        org.springframework.transaction.PlatformTransactionManager.class,
                        () -> db.transactions)
                .withBean(AiModelRouter.class, () -> router)
                .withBean(VisionAnalysisProperties.class, VisionAnalysisProperties::new)
                .withBean("legacyLlm", LlmProvider.class, DemoMockLlmProvider::new)
                .withBean(
                        "legacyVision",
                        VisionModelProvider.class,
                        () -> new OpenAiCompatibleVisionProvider(new VisionAnalysisProperties()))
                .withPropertyValues(
                        "courselingo.ai.system-models.enabled=true", "spring.flyway.enabled=true",
                        "courselingo.ai.asr.provider=mock", "courselingo.ai.asr.bailian.enabled=true",
                        "courselingo.ai.asr.silicon-flow.enabled=true")
                .run(
                        context -> {
                            assertThat(context).hasNotFailed();
                            assertThat(context.getBean(LlmProvider.class))
                                    .isInstanceOf(SystemModelLlmProvider.class);
                            assertThat(context.getBeansOfType(com.example.courselingo.ai.asr.AsrAdapterFactory.class)).hasSize(2);
                            assertThat(context).hasSingleBean(com.example.courselingo.ai.asr.SpeechToTextProvider.class);
                            assertThat(context.getBean(com.example.courselingo.ai.asr.SpeechToTextProvider.class))
                                    .isInstanceOf(SystemModelAsrProvider.class);
                            assertThat(context.getBean(VisionModelProvider.class))
                                    .isInstanceOf(SystemModelVisionProvider.class);
                            assertThat(
                                            context.getBean(SystemModelRegistry.class)
                                                    .catalog()
                                                    .version())
                                    .isPositive();
                        });
    }

    @Test
    void pipelineCreationAndSnapshotRollbackTogether() {
        long tasksBefore = db.jdbc.queryForObject("SELECT COUNT(*) FROM analysis_task", Long.class);
        long snapshotsBefore =
                db.jdbc.queryForObject(
                        "SELECT COUNT(*) FROM system_model_execution_snapshot", Long.class);
        var transaction =
                new org.springframework.transaction.support.TransactionTemplate(db.transactions);
        assertThatThrownBy(
                        () ->
                                transaction.executeWithoutResult(
                                        status -> {
                                            String created = db.task(user);
                                            executions.freezePipeline(created, user);
                                            throw new BusinessException(
                                                    ErrorCode.SYSTEM_MODEL_CONFIG_INVALID);
                                        }))
                .isInstanceOf(BusinessException.class);
        assertThat(db.jdbc.queryForObject("SELECT COUNT(*) FROM analysis_task", Long.class))
                .isEqualTo(tasksBefore);
        assertThat(
                        db.jdbc.queryForObject(
                                "SELECT COUNT(*) FROM system_model_execution_snapshot", Long.class))
                .isEqualTo(snapshotsBefore);
    }

    @Test
    void changingOnlyFullTranslationPreservesEveryOtherEffectiveRouteAndRollback() {
        var before = registry.catalog().effective();
        Target a = target("translation-a", "https://api.deepseek.com", KEY_A);
        bind("TRANSLATION_FULL_TEXT", a.model());
        long original = registry.currentVersion();
        var current = registry.catalog().effective();
        before.forEach(
                (key, value) -> {
                    if (!key.equals("TRANSLATION_FULL_TEXT"))
                        assertThat(current.get(key)).isEqualTo(value);
                });
        Target b = target("translation-b", "https://other.example/v1", KEY_B);
        bind("TRANSLATION_FULL_TEXT", b.model());
        registry.rollback(
                new SystemModelCommands.Rollback(
                        registry.currentVersion(), "TRANSLATION_FULL_TEXT", original),
                user);
        var next = executions.freezePipeline(db.task(user), user);
        assertThat(executions.route(next, "TRANSLATION_FULL_TEXT").modelId()).isEqualTo(a.model());
        assertThat(next.configVersion()).isGreaterThan(original);
    }

    @ParameterizedTest
    @ValueSource(strings = {"normal", "revision_before", "owner_before", "delete_before", "revision_after"})
    void scopedQaUsesFrozenModelAndAuthorityFences(String race) throws Exception {
        var a = target("scoped-qa-a", "https://api.deepseek.com", KEY_A);
        var b = target("scoped-qa-b", "https://other.example/v1", KEY_B);
        bind("COURSE_QA", a.model());
        var fence = new com.example.courselingo.task.service.GenerationFence(db.jdbc, db.transactions);
        var sources = new com.example.courselingo.evidence.CourseEvidenceService(db.jdbc, JSON, fence, db.transactions);
        db.jdbc.update("INSERT INTO subtitle_segment(task_id,user_id,segment_index,start_millis,end_millis,language,text) VALUES (?,?,0,0,1000,'en','Selected algorithm stopping condition.'),(?,?,1,1000,2000,'en','FORBIDDEN_OUTSIDE_SELECTION sorting arrays.')", task, user, task, user);
        long revision = sources.ensureSnapshot(task, user);
        String selected = sources.current(task, user).stream().filter(e -> e.rawText().startsWith("Selected")).findFirst().orElseThrow().evidenceId();
        var scope = new com.example.courselingo.evidence.LearningScope(1, "segments", "strict", revision, List.of(selected));
        var retriever = new com.example.courselingo.qa.service.CourseQaEvidenceRetriever(
                mock(com.example.courselingo.fusion.mapper.VideoSegmentMapper.class),
                mock(com.example.courselingo.subtitle.mapper.SubtitleSegmentMapper.class),
                mock(com.example.courselingo.subtitle.mapper.SubtitleTranslationSegmentMapper.class),
                mock(com.example.courselingo.vision.ocr.mapper.VideoKeyframeOcrMapper.class));
        retriever.configureEvidence(sources);
        var dense = mock(com.example.courselingo.qa.service.DenseEvidenceClient.class);
        when(dense.enabled()).thenReturn(true);
        Runnable revise = () -> new org.springframework.transaction.support.TransactionTemplate(db.transactions)
                .executeWithoutResult(status -> fence.sourceChanging(task, user));
        when(dense.retrieve(anyString(), eq(user), anyList(), anyString(), nullable(Long.class), nullable(Long.class), anyInt()))
                .thenAnswer(call -> {
                    List<com.example.courselingo.evidence.CourseEvidence> pool = call.getArgument(2);
                    assertThat(pool).extracting(com.example.courselingo.evidence.CourseEvidence::evidenceId).containsExactly(selected);
                    switch (race) {
                        case "revision_before" -> revise.run();
                        case "owner_before" -> db.jdbc.update("UPDATE analysis_task SET user_id=? WHERE id=?", db.user(), task);
                        case "delete_before" -> db.jdbc.update("UPDATE analysis_task SET deleted_at=CURRENT_TIMESTAMP WHERE id=?", task);
                        default -> bind("COURSE_QA", b.model());
                    }
                    return pool;
                });
        retriever.configureDenseRetrieval(dense);
        var receipts = new ArrayList<OpenAiCompatibleChatCompletionRequest>();
        OpenAiCompatibleLlmClient wire = request -> {
            receipts.add(request);
            assertThat(request.body()).contains("scoped-qa-a", "Selected algorithm").doesNotContain("FORBIDDEN_OUTSIDE_SELECTION");
            assertThat(request.headers().get("Authorization")).isEqualTo("Bearer " + KEY_A);
            if (race.equals("revision_after")) revise.run();
            return response(200, "{\"answer\":\"An algorithm needs a stopping condition.\",\"citedEvidenceIndexes\":[0]}");
        };
        var provider = new SystemModelLlmProvider(executions, wire, urls, wire);
        var users = mock(com.example.courselingo.auth.service.CurrentUserService.class);
        when(users.currentUser(any())).thenReturn(new CurrentUserResponse(user, "test@example.invalid", "ACTIVE"));
        var tasks = mock(com.example.courselingo.task.mapper.AnalysisTaskMapper.class);
        var entity = new com.example.courselingo.task.entity.AnalysisTask();
        entity.setId(task); entity.setUserId(user); entity.setStatus("SUCCEEDED"); entity.setTargetLanguage("zh-CN");
        when(tasks.selectByIdAndUserId(task, user)).thenReturn(entity);
        var configuration = new com.baomidou.mybatisplus.core.MybatisConfiguration();
        configuration.addMapper(com.example.courselingo.qa.mapper.CourseQaRecordMapper.class);
        var factory = new com.baomidou.mybatisplus.extension.spring.MybatisSqlSessionFactoryBean();
        factory.setDataSource(db.dataSource); factory.setConfiguration(configuration);
        var records = new org.mybatis.spring.SqlSessionTemplate(factory.getObject())
                .getMapper(com.example.courselingo.qa.mapper.CourseQaRecordMapper.class);
        var rate = mock(com.example.courselingo.qa.service.CourseQaRateLimitService.class);
        when(rate.checkAndConsume(user)).thenReturn(com.example.courselingo.qa.service.CourseQaRateLimitResult.allowed(10, 9));
        var qa = new com.example.courselingo.qa.service.CourseQaServiceImpl(users, tasks, retriever, records, provider, null, rate,
                Clock.systemUTC(), new com.example.courselingo.qa.service.CourseQaResponseParser(), new AiModelRoutedLlmRequestFactory(router, executions));
        qa.configureSystemModels(executions); qa.configureGenerationFence(fence);
        var input = new com.example.courselingo.qa.dto.CourseQaAskRequest("algorithm stopping condition", scope);
        if (race.equals("normal")) {
            var result = qa.ask(task, "Bearer test", input);
            assertThat(result.learning_scope()).isEqualTo(scope);
            assertThat(result.usage().model()).isEqualTo("scoped-qa-a");
            assertThat(result.evidence()).extracting(com.example.courselingo.qa.dto.CourseQaEvidenceItem::evidenceId).containsExactly(selected);
            assertThat(receipts).hasSize(1);
            var record = records.selectById(Long.parseLong(result.recordId()));
            assertThat(record.getInvocationState()).isEqualTo("RESPONSE_RECEIVED");
            assertThat(record.getExecutionSnapshotId()).isNotBlank();
            var historical = executions.query(record.getExecutionSnapshotId());
            assertThat(historical.routes().get("COURSE_QA").model()).isEqualTo("scoped-qa-a");
            assertThat(registry.currentVersion()).isGreaterThan(historical.configVersion());
            var beans = new StaticListableBeanFactory(Map.of("registry", registry, "executions", executions));
            var usage = new CourseModelUsageService(db.jdbc, beans.getBeanProvider(SystemModelRegistry.class), beans.getBeanProvider(SystemModelExecutionService.class)).read(task, user);
            assertThat(usage.current().routes()).filteredOn(r -> r.feature().equals("COURSE_QA")).singleElement().satisfies(r -> assertThat(r.model()).isEqualTo("scoped-qa-b"));
            assertThat(usage.qa()).singleElement().satisfies(q -> assertThat(q.selection().routes().getFirst().model()).isEqualTo("scoped-qa-a"));
        } else {
            assertThatThrownBy(() -> qa.ask(task, "Bearer test", input)).isInstanceOf(RuntimeException.class);
            assertThat(records.selectByTaskIdAndUserId(task, user, 20)).noneMatch(record -> "SUCCEEDED".equals(record.getStatus()));
            assertThat(receipts).hasSize(race.equals("revision_after") ? 1 : 0);
        }
    }

    @ParameterizedTest
    @ValueSource(strings = {"success", "no_usage", "provider_failure", "parse_failure", "no_evidence", "missing_provider", "preparation_failure", "cancel_after", "revision_after", "delete_after", "transfer_after"})
    void qaUsageFactsRetainTheExactRequestAcrossOutcomes(String scenario) throws Exception {
        var a = target("usage-a", "https://api.deepseek.com", KEY_A);
        var b = target("usage-b", "https://other.example/v1", KEY_B);
        bind("COURSE_QA", a.model());
        var fence = new com.example.courselingo.task.service.GenerationFence(db.jdbc, db.transactions);
        var requests = new ArrayList<LlmRequest>();
        long otherOwner = db.user();
        LlmProvider provider = new LlmProvider() {
            public String providerName() { return "deterministic-test"; }
            public String modelNameForDiagnostics() { return "deterministic-model"; }
            public LlmResult generate(LlmRequest request) {
                requests.add(request);
                bind("COURSE_QA", b.model());
                assertThat(executions.route(request.execution(), "COURSE_QA").model()).isEqualTo("usage-a");
                switch (scenario) {
                    case "provider_failure" -> throw new IllegalStateException("synthetic failure before a result");
                    case "cancel_after" -> db.jdbc.update("UPDATE analysis_task SET status='CANCELED' WHERE id=?", task);
                    case "revision_after" -> new org.springframework.transaction.support.TransactionTemplate(db.transactions).executeWithoutResult(status -> fence.sourceChanging(task, user));
                    case "delete_after" -> db.jdbc.update("UPDATE analysis_task SET deleted_at=CURRENT_TIMESTAMP WHERE id=?", task);
                    case "transfer_after" -> db.jdbc.update("UPDATE analysis_task SET user_id=? WHERE id=?", otherOwner, task);
                    default -> { }
                }
                return new LlmResult("deterministic-test", "usage-a",
                        scenario.equals("parse_failure") ? "invalid-json" : "{\"answer\":\"Synthetic answer\",\"citedEvidenceIndexes\":[0]}",
                        "stop", scenario.equals("no_usage") ? null : new LlmUsage(11, 7, 18), Duration.ofMillis(1), Map.of());
            }
        };
        var routed = scenario.equals("preparation_failure") ? new AiModelRoutedLlmRequestFactory(router, executions) {
            @Override public LlmRequest apply(AiModelStage stage, LlmRequest request) { throw new IllegalStateException("synthetic preparation failure"); }
        } : new AiModelRoutedLlmRequestFactory(router, executions);
        var harness = qaHarness(scenario.equals("missing_provider") ? null : provider, fence, routed, scenario.equals("no_evidence"));
        boolean success = Set.of("success", "no_usage", "no_evidence").contains(scenario);
        var question = new com.example.courselingo.qa.dto.CourseQaAskRequest("Explain the synthetic course passage");
        if (success) harness.service().ask(task, "Bearer test", question);
        else assertThatThrownBy(() -> harness.service().ask(task, "Bearer test", question)).isInstanceOf(RuntimeException.class);
        var records = harness.records().selectByTaskIdAndUserId(task, user, 20);
        var beans = new StaticListableBeanFactory(Map.of("registry", registry, "executions", executions));
        var usage = new CourseModelUsageService(db.jdbc, beans.getBeanProvider(SystemModelRegistry.class), beans.getBeanProvider(SystemModelExecutionService.class));
        if (Set.of("delete_after", "transfer_after").contains(scenario)) {
            assertThat(records).isEmpty();
            assertThatThrownBy(() -> usage.read(task, user)).isInstanceOf(BusinessException.class);
            if (scenario.equals("transfer_after")) {
                assertThat(usage.read(task, otherOwner).qa()).isEmpty();
                assertThat(usage.read(task, otherOwner).calls()).isEmpty();
                assertThat(usage.read(task, otherOwner).pipeline()).isEmpty();
            }
            return;
        }
        assertThat(records).hasSize(1);
        var record = records.getFirst();
        String expected = scenario.equals("no_evidence") ? "SKIPPED_NO_EVIDENCE"
                : Set.of("missing_provider", "preparation_failure").contains(scenario) ? "NOT_STARTED"
                : scenario.equals("provider_failure") ? "DISPATCHED" : "RESPONSE_RECEIVED";
        assertThat(record.getInvocationState()).isEqualTo(expected);
        assertThat(record.getStatus()).isEqualTo(success ? "SUCCEEDED" : "FAILED");
        assertThat(executions.query(record.getExecutionSnapshotId()).routes().get("COURSE_QA").model()).isEqualTo("usage-a");
        if (requests.isEmpty()) assertThat(Set.of("no_evidence", "missing_provider", "preparation_failure")).contains(scenario);
        else assertThat(record.getExecutionSnapshotId()).isEqualTo(requests.getFirst().execution().snapshotId());
        if (Set.of("no_evidence", "missing_provider").contains(scenario)) assertThat(record.getAiCallRecordId()).isNull();
        else {
            var call = harness.calls().selectById(record.getAiCallRecordId());
            assertThat(call.getTaskId()).isEqualTo(task); assertThat(call.getUserId()).isEqualTo(user);
            assertThat(call.getStatus()).isEqualTo(success ? "SUCCEEDED" : "FAILED");
        }
        assertThat(record.getTotalTokens()).isEqualTo(expected.equals("RESPONSE_RECEIVED") && !scenario.equals("no_usage") ? 18 : null);
        assertThat(usage.read(task, user).qa()).singleElement().satisfies(q -> {
            assertThat(q.recordId()).isEqualTo(String.valueOf(record.getId()));
            assertThat(q.selection().snapshotId()).isEqualTo(record.getExecutionSnapshotId());
            assertThat(q.totalTokens()).isEqualTo(record.getTotalTokens());
        });
    }

    @Test
    void managedQaWithARealCallLedgerAcceptsUnknownPreDispatchModelIdentity() throws Exception {
        var a = target("managed-qa-ledger", "https://api.deepseek.com", KEY_A); bind("COURSE_QA", a.model());
        var receipts = new AtomicInteger();
        OpenAiCompatibleLlmClient wire = request -> { receipts.incrementAndGet(); return response(200, "{\"answer\":\"Synthetic answer\",\"citedEvidenceIndexes\":[0]}"); };
        var provider = new SystemModelLlmProvider(executions, wire, urls, wire);
        var harness = qaHarness(provider, new com.example.courselingo.task.service.GenerationFence(db.jdbc, db.transactions), new AiModelRoutedLlmRequestFactory(router, executions), false);
        var result = harness.service().ask(task, "Bearer test", new com.example.courselingo.qa.dto.CourseQaAskRequest("Explain the synthetic course passage"));
        var record = harness.records().selectById(Long.valueOf(result.recordId()));
        assertThat(receipts.get()).isEqualTo(1);
        assertThat(record.getInvocationState()).isEqualTo("RESPONSE_RECEIVED");
        assertThat(record.getModel()).isEqualTo("managed-qa-ledger");
        assertThat(harness.calls().selectById(record.getAiCallRecordId()).getModel()).isNull();
    }

    @Test
    void concurrentQaRequestsKeepDistinctSnapshotAndCallReferencesWhenBReturnsBeforeA() throws Exception {
        var a = target("concurrent-a", "https://api.deepseek.com", KEY_A);
        var b = target("concurrent-b", "https://other.example/v1", KEY_B);
        bind("COURSE_QA", a.model());
        var entered = new CountDownLatch(1); var release = new CountDownLatch(1);
        var refs = new ConcurrentHashMap<String, SystemModelExecutionRef>();
        LlmProvider provider = new LlmProvider() {
            public String providerName() { return "deterministic-test"; }
            public String modelNameForDiagnostics() { return "deterministic-model"; }
            public LlmResult generate(LlmRequest request) {
                String model = executions.route(request.execution(), "COURSE_QA").model(); refs.put(model, request.execution());
                if (model.equals("concurrent-a")) {
                    entered.countDown();
                    try { if (!release.await(10, TimeUnit.SECONDS)) throw new AssertionError("release timeout"); }
                    catch (InterruptedException error) { throw new AssertionError(error); }
                }
                return new LlmResult("deterministic-test", model, "{\"answer\":\"" + model + "\",\"citedEvidenceIndexes\":[0]}", "stop", null, Duration.ofMillis(1), Map.of());
            }
        };
        var harness = qaHarness(provider, new com.example.courselingo.task.service.GenerationFence(db.jdbc, db.transactions), new AiModelRoutedLlmRequestFactory(router, executions), false);
        var question = new com.example.courselingo.qa.dto.CourseQaAskRequest("Explain the synthetic course passage");
        try (var worker = Executors.newSingleThreadExecutor()) {
            var first = worker.submit(() -> harness.service().ask(task, "Bearer test", question));
            try {
                assertThat(entered.await(10, TimeUnit.SECONDS)).isTrue(); bind("COURSE_QA", b.model());
                var second = harness.service().ask(task, "Bearer test", question); release.countDown();
                var resultA = first.get(10, TimeUnit.SECONDS);
                for (var result : List.of(resultA, second)) {
                    var record = harness.records().selectById(Long.valueOf(result.recordId()));
                    assertThat(record.getExecutionSnapshotId()).isEqualTo(refs.get(result.usage().model()).snapshotId());
                    assertThat(record.getInvocationState()).isEqualTo("RESPONSE_RECEIVED");
                }
                var rows = harness.records().selectByTaskIdAndUserId(task, user, 20);
                assertThat(rows).hasSize(2);
                assertThat(rows).extracting(com.example.courselingo.qa.domain.CourseQaRecord::getExecutionSnapshotId).doesNotHaveDuplicates();
                assertThat(rows).extracting(com.example.courselingo.qa.domain.CourseQaRecord::getAiCallRecordId).doesNotHaveDuplicates();
            } finally { release.countDown(); }
        }
    }

    private QaHarness qaHarness(LlmProvider provider, com.example.courselingo.task.service.GenerationFence fence, AiModelRoutedLlmRequestFactory routed, boolean noEvidence) throws Exception {
        var config = new com.baomidou.mybatisplus.core.MybatisConfiguration();
        config.addMapper(com.example.courselingo.qa.mapper.CourseQaRecordMapper.class);
        config.addMapper(com.example.courselingo.ai.record.mapper.AiCallRecordMapper.class);
        var factory = new com.baomidou.mybatisplus.extension.spring.MybatisSqlSessionFactoryBean(); factory.setDataSource(db.dataSource); factory.setConfiguration(config);
        var session = new org.mybatis.spring.SqlSessionTemplate(factory.getObject());
        var records = session.getMapper(com.example.courselingo.qa.mapper.CourseQaRecordMapper.class);
        var calls = session.getMapper(com.example.courselingo.ai.record.mapper.AiCallRecordMapper.class);
        var users = mock(com.example.courselingo.auth.service.CurrentUserService.class);
        when(users.currentUser(any())).thenReturn(new CurrentUserResponse(user, "synthetic@example.invalid", "ACTIVE"));
        var tasks = mock(com.example.courselingo.task.mapper.AnalysisTaskMapper.class);
        var entity = new com.example.courselingo.task.entity.AnalysisTask(); entity.setId(task); entity.setUserId(user); entity.setTargetLanguage("zh-CN"); entity.setStatus("SUCCEEDED");
        when(tasks.selectByIdAndUserId(task, user)).thenReturn(entity);
        var evidence = mock(com.example.courselingo.qa.service.CourseQaEvidenceRetriever.class);
        when(evidence.retrieve(eq(task), eq(user), anyString(), anyString())).thenReturn(noEvidence ? List.of() : List.of(new com.example.courselingo.qa.dto.CourseQaEvidenceItem("SUBTITLE", "synthetic", 0L, 1000L, "00:00", "Synthetic course passage", null, null)));
        var rate = mock(com.example.courselingo.qa.service.CourseQaRateLimitService.class);
        when(rate.checkAndConsume(user)).thenReturn(com.example.courselingo.qa.service.CourseQaRateLimitResult.allowed(10, 9));
        var service = new com.example.courselingo.qa.service.CourseQaServiceImpl(users, tasks, evidence, records, provider,
                new com.example.courselingo.ai.record.service.AiCallRecordServiceImpl(calls, Clock.systemUTC(), new com.example.courselingo.ai.record.service.AiCallRecordSanitizer()), rate, Clock.systemUTC(), new com.example.courselingo.qa.service.CourseQaResponseParser(), routed);
        service.configureSystemModels(executions); service.configureGenerationFence(fence);
        return new QaHarness(service, records, calls);
    }
    private record QaHarness(com.example.courselingo.qa.service.CourseQaServiceImpl service, com.example.courselingo.qa.mapper.CourseQaRecordMapper records, com.example.courselingo.ai.record.mapper.AiCallRecordMapper calls) {}

    @Test
    void runningAUsesOldVersionWhileNewBUsesNewVersion() throws Exception {
        Target a = target("translation-a", "https://api.deepseek.com", KEY_A);
        Target b = target("translation-b", "https://other.example/v1", KEY_B);
        bind("TRANSLATION_FULL_TEXT", a.model());
        var snapshotA = executions.freezePipeline(task, user);
        db.jdbc.update("UPDATE analysis_task SET status='RUNNING' WHERE id=?", task);
        var started = new CountDownLatch(1);
        var release = new CountDownLatch(1);
        var receipts = new CopyOnWriteArrayList<OpenAiCompatibleChatCompletionRequest>();
        OpenAiCompatibleLlmClient mock =
                req -> {
                    receipts.add(req);
                    observeRequest("text-version-switch", req);
                    if (req.headers().get("Authorization").endsWith(KEY_A)) {
                        started.countDown();
                        try {
                            if (!release.await(5, TimeUnit.SECONDS))
                                throw new AssertionError("release timeout");
                        } catch (InterruptedException e) {
                            throw new AssertionError(e);
                        }
                    }
                    return response(200, "{\"ok\":true}");
                };
        var provider = new SystemModelLlmProvider(executions, mock, urls, mock);
        try (var worker = Executors.newSingleThreadExecutor()) {
            var running =
                    worker.submit(
                            () ->
                                    provider.generate(
                                            request(
                                                    snapshotA,
                                                    AiModelStage.TRANSLATION_FULL_TEXT)));
            try {
                assertThat(started.await(5, TimeUnit.SECONDS)).isTrue();
                bind("TRANSLATION_FULL_TEXT", b.model());
                var snapshotB = executions.freezePipeline(db.task(user), user);
                var resultB =
                        provider.generate(request(snapshotB, AiModelStage.TRANSLATION_FULL_TEXT));
                release.countDown();
                var resultA = running.get(5, TimeUnit.SECONDS);
                observeVersion("A", snapshotA, resultA);
                observeVersion("B", snapshotB, resultB);
                assertThat(resultA.model()).isEqualTo("translation-a");
                assertThat(resultB.model()).isEqualTo("translation-b");
                assertThat(resultA.metadata().get("systemModel.configVersion"))
                        .isEqualTo(snapshotA.configVersion());
                assertThat(snapshotB.configVersion()).isGreaterThan(snapshotA.configVersion());
                assertThat(receipts.get(0).uri().toString())
                        .isEqualTo("https://api.deepseek.com/chat/completions");
                assertThat(receipts.get(1).uri().toString())
                        .isEqualTo("https://other.example/v1/chat/completions");
                assertThat(receipts.get(0).headers().get("Authorization"))
                        .isEqualTo("Bearer " + KEY_A);
                assertThat(receipts.get(1).headers().get("Authorization"))
                        .isEqualTo("Bearer " + KEY_B);
                assertThat(executions.pipeline(task, user)).isEqualTo(snapshotA);
                assertThat(executions.query(snapshotA.snapshotId()).configVersion())
                        .isEqualTo(snapshotA.configVersion());
                String stored =
                        db.jdbc.queryForObject(
                                "SELECT resolved_config_json FROM system_model_execution_snapshot"
                                        + " WHERE id=?",
                                String.class,
                                snapshotA.snapshotId());
                assertThat(stored).doesNotContain(KEY_A, KEY_B, "ciphertext");
            } finally {
                release.countDown();
            }
        }
    }

    @Test
    void keyRotationAndDeletingCurrentObjectsDoNotChangeExistingExecution() {
        Target a = target("translation-a", "https://api.deepseek.com", KEY_A);
        bind("TRANSLATION_FULL_TEXT", a.model());
        var frozen = executions.freezePipeline(task, user);
        registry.saveProvider(
                a.provider(),
                new SystemModelCommands.Provider(
                        registry.currentVersion(),
                        "rotated",
                        SystemModelProtocol.OPENAI_CHAT,
                        "https://api.deepseek.com",
                        true,
                        KEY_B,
                        false),
                user);
        assertThat(executions.credential(frozen, "TRANSLATION_FULL_TEXT")).isEqualTo(KEY_A);
        var later = executions.freezePipeline(db.task(user), user);
        assertThat(executions.credential(later, "TRANSLATION_FULL_TEXT")).isEqualTo(KEY_B);
        var clear = new LinkedHashMap<String, Long>();
        clear.put("TRANSLATION_FULL_TEXT", null);
        registry.bindings(new SystemModelCommands.Bindings(registry.currentVersion(), clear), user);
        registry.delete("MODEL", a.model(), registry.currentVersion(), user);
        registry.delete("PROVIDER", a.provider(), registry.currentVersion(), user);
        assertThat(executions.credential(frozen, "TRANSLATION_FULL_TEXT")).isEqualTo(KEY_A);
    }

    @Test
    void missedRedisNotificationStillFreezesCurrentDatabaseVersion() {
        Target a = target("translation-a", "https://api.deepseek.com", KEY_A);
        var stale = registry(true, true, cipher);
        stale.initialize();
        stale.catalog();
        registry.notifier(
                version -> {
                    throw new IllegalStateException("simulated notification loss");
                });
        bind("TRANSLATION_FULL_TEXT", a.model());
        var otherExecutions = new SystemModelExecutionService(db.jdbc, stale, db.transactions);
        var ref = otherExecutions.freezePipeline(task, user);
        assertThat(ref.configVersion()).isEqualTo(registry.currentVersion());
        assertThat(otherExecutions.route(ref, "TRANSLATION_FULL_TEXT").modelId())
                .isEqualTo(a.model());
    }

    @Test
    void concurrentSavesHaveExactlyOneWinner() throws Exception {
        long expected = registry.currentVersion();
        var start = new CountDownLatch(1);
        var results = new CopyOnWriteArrayList<Boolean>();
        try (var workers = Executors.newFixedThreadPool(2)) {
            var futures = new ArrayList<Future<?>>();
            for (int i = 0; i < 2; i++)
                futures.add(
                        workers.submit(
                                () -> {
                                    try {
                                        start.await();
                                        registry.saveProvider(
                                                null,
                                                new SystemModelCommands.Provider(
                                                        expected,
                                                        "concurrent",
                                                        SystemModelProtocol.OPENAI_CHAT,
                                                        "https://example.com",
                                                        true,
                                                        KEY_A,
                                                        false),
                                                user);
                                        results.add(true);
                                    } catch (BusinessException conflict) {
                                        assertThat(conflict.errorCode())
                                                .isEqualTo(ErrorCode.SYSTEM_MODEL_CONFIG_CONFLICT);
                                        results.add(false);
                                    } catch (InterruptedException e) {
                                        throw new AssertionError(e);
                                    }
                                }));
            start.countDown();
            for (var future : futures) future.get(10, TimeUnit.SECONDS);
        }
        assertThat(results).containsExactlyInAnyOrder(true, false);
        assertThat(registry.currentVersion()).isEqualTo(expected + 1);
    }

    @ParameterizedTest
    @ValueSource(ints = {401, 404, 429, 500})
    void providerErrorsFailWithoutFallbackOrRawBody(int status) {
        Target a = target("error-model", "https://api.deepseek.com", KEY_A);
        bind("TRANSLATION_FULL_TEXT", a.model());
        var ref = executions.freezePipeline(task, user);
        var calls = new AtomicInteger();
        OpenAiCompatibleLlmClient mock =
                req -> {
                    calls.incrementAndGet();
                    return response(status, KEY_A + " provider-private-error");
                };
        var provider =
                new SystemModelLlmProvider(
                        executions,
                        mock,
                        urls,
                        req -> {
                            throw new AssertionError("legacy fallback");
                        });
        assertThatThrownBy(
                        () -> provider.generate(request(ref, AiModelStage.TRANSLATION_FULL_TEXT)))
                .isInstanceOf(SystemModelCallFailure.class)
                .hasNoCause()
                .hasMessageNotContaining(KEY_A)
                .hasMessageNotContaining("provider-private-error");
        assertThat(calls.get()).isEqualTo(1);
    }

    @ParameterizedTest
    @ValueSource(strings = {"not JSON", "[]", "", "```json\n{}\n```"})
    void invalidStructuredOutputNeverDowngradesToText(String output) {
        Target a = target("json-model", "https://api.deepseek.com", KEY_A);
        bind("TRANSLATION_FULL_TEXT", a.model());
        var ref = executions.freezePipeline(task, user);
        var calls = new AtomicInteger();
        OpenAiCompatibleLlmClient mock =
                req -> {
                    calls.incrementAndGet();
                    assertThat(req.body()).contains("json_object");
                    return response(200, output);
                };
        assertThatThrownBy(
                        () ->
                                new SystemModelLlmProvider(executions, mock, urls, mock)
                                        .generate(request(ref, AiModelStage.TRANSLATION_FULL_TEXT)))
                .isInstanceOf(SystemModelCallFailure.class)
                .hasMessageContaining("OUTPUT_INVALID")
                .hasNoCause();
        assertThat(calls.get()).isEqualTo(1);
    }

    @Test
    void cannotDecryptDoesNotUseEnvironmentCredentials() {
        Target a = target("locked-model", "https://api.deepseek.com", KEY_A);
        bind("TRANSLATION_FULL_TEXT", a.model());
        var ref = executions.freezePipeline(task, user);
        var wrongKey = new byte[32];
        Arrays.fill(wrongKey, (byte) 9);
        var otherCipher = new SystemModelSecretCipher(Base64.getEncoder().encodeToString(wrongKey));
        var wrong = registry(true, true, otherCipher);
        var other = new SystemModelExecutionService(db.jdbc, wrong, db.transactions);
        OpenAiCompatibleLlmClient never =
                req -> {
                    throw new AssertionError("network must not be reached");
                };
        assertThatThrownBy(
                        () ->
                                new SystemModelLlmProvider(other, never, urls, never)
                                        .generate(request(ref, AiModelStage.TRANSLATION_FULL_TEXT)))
                .isInstanceOf(BusinessException.class)
                .extracting("errorCode")
                .isEqualTo(ErrorCode.SYSTEM_MODEL_KEY_DECRYPTION_FAILED);
    }

    @Test
    void noBindingUsesExistingEnvironmentUrlAndMockMode() {
        var receipts = new ArrayList<OpenAiCompatibleChatCompletionRequest>();
        OpenAiCompatibleLlmClient mock =
                req -> {
                    receipts.add(req);
                    observeRequest("legacy-environment", req);
                    return response(200, "{\"ok\":true}");
                };
        var ref = executions.freezePipeline(task, user);
        new SystemModelLlmProvider(executions, mock, urls, mock)
                .generate(request(ref, AiModelStage.COURSE_QA));
        assertThat(receipts.getFirst().uri().toString())
                .isEqualTo("https://legacy.example/v1/chat/completions");
        assertThat(receipts.getFirst().headers().get("Authorization"))
                .isEqualTo("Bearer " + ENV_KEY);
        registry = registry(true, false, cipher);
        registry.initialize();
        executions = new SystemModelExecutionService(db.jdbc, registry, db.transactions);
        var mocked = executions.freezePipeline(db.task(user), user);
        new SystemModelLlmProvider(
                        executions,
                        req -> {
                            throw new AssertionError("external mock call");
                        },
                        urls,
                        mock)
                .generate(request(mocked, AiModelStage.COURSE_QA));
        assertThat(receipts).hasSize(1);
    }

    @Test
    void wrongOwnerCancelledDeletedAndForgedVersionCannotResolve() {
        var ref = executions.freezePipeline(task, user);
        assertThatThrownBy(() -> executions.pipeline(task, user + 10000))
                .isInstanceOf(BusinessException.class);
        assertThatThrownBy(
                        () ->
                                executions.route(
                                        new SystemModelExecutionRef(
                                                ref.snapshotId(),
                                                ref.configVersion() + 1,
                                                task,
                                                user),
                                        "COURSE_QA"))
                .isInstanceOf(BusinessException.class);
        db.jdbc.update("UPDATE analysis_task SET status='CANCELED' WHERE id=?", task);
        assertThatThrownBy(() -> executions.route(ref, "COURSE_QA"))
                .isInstanceOf(BusinessException.class);
        db.jdbc.update(
                "UPDATE analysis_task SET status='SUCCEEDED',deleted_at=NOW() WHERE id=?", task);
        assertThatThrownBy(() -> executions.route(ref, "COURSE_QA"))
                .isInstanceOf(BusinessException.class);
    }

    @Test
    void actualFullAndSegmentTranslationHitIndependentBindings() {
        Target full = target("full-text", "https://api.deepseek.com", KEY_A);
        Target segment = target("segments", "https://other.example/v1", KEY_B);
        registry.bindings(
                new SystemModelCommands.Bindings(
                        registry.currentVersion(),
                        Map.of(
                                "TRANSLATION_FULL_TEXT",
                                full.model(),
                                "SUBTITLE_TRANSLATION",
                                segment.model())),
                user);
        for (boolean mode : List.of(true, false)) {
            registry = registry(mode, true, cipher);
            registry.initialize();
            executions = new SystemModelExecutionService(db.jdbc, registry, db.transactions);
            String taskId = db.task(user);
            var ref = executions.freezePipeline(taskId, user);
            var receipts = new ArrayList<OpenAiCompatibleChatCompletionRequest>();
            OpenAiCompatibleLlmClient http =
                    req -> {
                        receipts.add(req);
                        observeRequest("translation-modes", req);
                        return response(
                                200,
                                mode
                                        ? "{\"segments\":[{\"index\":0,\"text\":\"你好，世界。\"}]}"
                                        : "你好，世界。");
                    };
            var provider = new SystemModelLlmProvider(executions, http, urls, http);
            var sources = mock(SubtitleSegmentMapper.class);
            var translations = mock(SubtitleTranslationSegmentMapper.class);
            var texts = mock(TaskFullTextResultMapper.class);
            var source = new SubtitleSegment();
            source.setId(1L);
            source.setTaskId(taskId);
            source.setUserId(user);
            source.setSegmentIndex(0);
            source.setLanguage("en");
            source.setText("Hello world.");
            source.setStartMillis(0L);
            source.setEndMillis(1000L);
            when(sources.selectByTaskIdAndUserId(taskId, user)).thenReturn(List.of(source));
            when(translations.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
            when(texts.insert(any(TaskFullTextResult.class))).thenReturn(1);
            var properties = new SubtitleTranslationProperties();
            properties.getFullText().setEnabled(mode);
            var service =
                    new SubtitleTranslationServiceImpl(
                            sources,
                            translations,
                            texts,
                            provider,
                            Clock.systemUTC(),
                            new SubtitleTranslationResponseParser(),
                            properties,
                            new AiModelRoutedLlmRequestFactory(router, executions));
            service.configureSystemModels(executions);
            assertThat(
                            service.translateTaskSubtitles(
                                    new TranslateSubtitleCommand(
                                            taskId, user, "en", "zh-CN", "translation-test", ref)))
                    .isEqualTo(1);
            assertThat(receipts).hasSize(1);
            assertThat(receipts.getFirst().body()).contains(mode ? "full-text" : "segments");
            assertThat(receipts.getFirst().headers().get("Authorization"))
                    .isEqualTo("Bearer " + (mode ? KEY_A : KEY_B));
        }
    }

    @Test
    void visualCallsUseFrozenIndependentKeyAndExactEndpoint(@TempDir Path directory)
            throws Exception {
        Target visual = target("vision-model", "https://api.deepseek.com", KEY_B);
        // Extra declarations must not break the existing vision capability adapter.
        registry.saveModel(visual.model(), visual.provider(), new SystemModelCommands.Model(
                registry.currentVersion(), "vision-model", Set.of("TEXT_CHAT", "JSON_OUTPUT", "VISION", "ASR"),
                null, true), user);
        bind("VISION_FRAME_ANALYSIS", visual.model());
        var ref = executions.freezePipeline(task, user);
        var image = directory.resolve("frame.png");
        javax.imageio.ImageIO.write(
                new java.awt.image.BufferedImage(16, 16, java.awt.image.BufferedImage.TYPE_INT_RGB),
                "png",
                image.toFile());
        var receipts = new ArrayList<OpenAiCompatibleChatCompletionRequest>();
        OpenAiCompatibleLlmClient http =
                req -> {
                    receipts.add(req);
                    observeRequest("vision", req);
                    return response(
                            200,
                            "{\"screenType\":\"CODE\",\"summary\":\"visible"
                                    + " example\",\"detectedElements\":[]}");
                };
        var provider =
                new SystemModelVisionProvider(
                        executions, http, new VisionAnalysisProperties(), urls);
        var result =
                provider.analyze(
                        new VisionAnalysisRequest(
                                task, 1L, 0L, image, "", "", executions.visionRoute(ref)));
        assertThat(result.status()).isEqualTo(VisionAnalysisStatus.SUCCEEDED);
        assertThat(receipts.getFirst().uri().toString())
                .isEqualTo("https://api.deepseek.com/chat/completions");
        assertThat(receipts.getFirst().headers().get("Authorization")).isEqualTo("Bearer " + KEY_B);
        assertThat(receipts.getFirst().body()).contains("image_url", "json_object");
    }

    @Test
    void everyManagementEndpointChecksAdminAndQueriesNeverReturnCiphertext() throws Exception {
        Target a = target("history-model", "https://api.deepseek.com", KEY_A);
        bind("TRANSLATION_FULL_TEXT", a.model());
        var ref = executions.freezePipeline(task, user);
        long version = ref.configVersion();
        registry.saveProvider(
                a.provider(),
                new SystemModelCommands.Provider(
                        registry.currentVersion(),
                        "rotated-history",
                        SystemModelProtocol.OPENAI_CHAT,
                        "https://api.deepseek.com",
                        true,
                        KEY_B,
                        false),
                user);
        var auth =
                new AdminAuthorizationService(
                        header -> {
                            if (header == null)
                                throw new BusinessException(ErrorCode.COMMON_UNAUTHORIZED);
                            return new CurrentUserResponse(
                                    user,
                                    "test@example.invalid",
                                    "ACTIVE",
                                    "admin".equals(header) ? UserRole.ADMIN : UserRole.USER);
                        });
        var beans = new StaticListableBeanFactory(Map.of("adminAuthorizationService", auth));
        class Interceptors extends InterceptorRegistry {
            List<Object> all() {
                return getInterceptors();
            }
        }
        var interceptors = new Interceptors();
        new SystemModelAdminWebConfiguration(beans.getBeanProvider(AdminAuthorizationService.class))
                .addInterceptors(interceptors);
        MockMvc mvc =
                MockMvcBuilders.standaloneSetup(
                                new SystemModelAdminController(registry, executions))
                        .setControllerAdvice(new GlobalExceptionHandler())
                        .addInterceptors(
                                interceptors.all().stream()
                                        .map(i -> (HandlerInterceptor) i)
                                        .toArray(HandlerInterceptor[]::new))
                        .build();
        String base = "/api/admin/system-models";
        var requests =
                List.of(
                        get(base + "/catalog"),
                        post(base + "/providers"),
                        patch(base + "/providers/1"),
                        delete(base + "/providers/1").param("expectedVersion", "0"),
                        post(base + "/providers/1/models"),
                        patch(base + "/providers/1/models/1"),
                        delete(base + "/models/1").param("expectedVersion", "0"),
                        put(base + "/bindings"),
                        post(base + "/rollbacks"),
                        get(base + "/versions"),
                        get(base + "/versions/" + version),
                        get(base + "/audit"),
                        get(base + "/executions").param("taskId", task),
                        get(base + "/executions/" + ref.snapshotId()));
        for (var req : requests) {
            mvc.perform(req).andExpect(status().isUnauthorized());
            mvc.perform(req.header("Authorization", "user")).andExpect(status().isForbidden());
        }
        List<String> encrypted = new ArrayList<>();
        for (String stored :
                db.jdbc.queryForList(
                        "SELECT config_json FROM system_model_config_version", String.class))
            encrypted.addAll(JSON.readTree(stored).findValuesAsText("ciphertext"));
        for (String path :
                List.of(
                        "/catalog",
                        "/versions",
                        "/versions/" + version,
                        "/audit",
                        "/executions?taskId=" + task,
                        "/executions/" + ref.snapshotId())) {
            String body =
                    mvc.perform(get(base + path).header("Authorization", "admin"))
                            .andExpect(status().isOk())
                            .andReturn()
                            .getResponse()
                            .getContentAsString();
            assertThat(body)
                    .doesNotContain(
                            KEY_A,
                            KEY_B,
                            ENV_KEY,
                            VISION_KEY,
                            "ciphertext",
                            "config_json",
                            "environmentFingerprint",
                            "credentialId");
            for (String ciphertext : encrypted)
                if (ciphertext != null && ciphertext.startsWith("v1."))
                    assertThat(body).doesNotContain(ciphertext);
        }
    }

    private static void observeRequest(
            String scenario, OpenAiCompatibleChatCompletionRequest request) {
        try {
            var body = JSON.readTree(request.body());
            String header = request.headers().getOrDefault("Authorization", "");
            writeObservation(
                    "requests.jsonl",
                    Map.of(
                            "kind",
                            "MOCK_REQUEST",
                            "scenario",
                            scenario,
                            "finalUrl",
                            request.uri().toString(),
                            "model",
                            body.path("model").asText(),
                            "hasKey",
                            !header.isBlank(),
                            "keyLast4",
                            header.length() < 4 ? "" : header.substring(header.length() - 4),
                            "responseFormat",
                            body.path("response_format").path("type").asText("TEXT"),
                            "hasImage",
                            !body.findValues("image_url").isEmpty()));
        } catch (Exception failure) {
            throw new AssertionError("Cannot record sanitized verification receipt", failure);
        }
    }

    private static void observeVersion(String task, SystemModelExecutionRef ref, LlmResult result) {
        writeObservation(
                "versions.jsonl",
                Map.of(
                        "kind",
                        "MOCK_RESULT",
                        "task",
                        task,
                        "snapshotId",
                        ref.snapshotId(),
                        "frozenVersion",
                        ref.configVersion(),
                        "observedVersion",
                        result.metadata().get("systemModel.configVersion"),
                        "model",
                        result.model(),
                        "finalUrl",
                        result.metadata().get("systemModel.finalUrl")));
    }

    private static synchronized void writeObservation(
            String name, Map<String, Object> observation) {
        String target = System.getenv("SYSTEM_MODEL_VERIFICATION_DIR");
        if (target == null) return;
        try {
            Path directory = Path.of(target);
            java.nio.file.Files.createDirectories(directory);
            java.nio.file.Files.writeString(
                    directory.resolve(name),
                    JSON.writeValueAsString(observation) + "\n",
                    java.nio.file.StandardOpenOption.CREATE,
                    java.nio.file.StandardOpenOption.APPEND);
        } catch (Exception failure) {
            throw new AssertionError("Cannot persist verification receipt", failure);
        }
    }
}
