package com.example.courselingo.systemmodel;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.baomidou.mybatisplus.core.MybatisConfiguration;
import com.baomidou.mybatisplus.extension.spring.MybatisSqlSessionFactoryBean;
import com.example.courselingo.ai.asr.*;
import com.example.courselingo.ai.llm.*;
import com.example.courselingo.ai.record.mapper.AiCallRecordMapper;
import com.example.courselingo.ai.record.service.*;
import com.example.courselingo.common.metrics.BusinessMetrics;
import com.example.courselingo.dispatch.BoundedTaskExecutor;
import com.example.courselingo.modelrouting.*;
import com.example.courselingo.mq.AnalysisTaskMessage;
import com.example.courselingo.subtitle.diagnostic.TranslationCallDiagnostics;
import com.example.courselingo.subtitle.mapper.*;
import com.example.courselingo.subtitle.service.*;
import com.example.courselingo.task.claim.*;
import com.example.courselingo.task.mapper.*;
import com.example.courselingo.task.progress.TaskProgressSnapshotService;
import com.example.courselingo.task.runner.*;
import com.example.courselingo.task.service.*;
import com.example.courselingo.vision.keyframe.VideoKeyframeEvidenceLifecycleService;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.*;
import java.util.*;
import java.util.concurrent.Callable;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.IntFunction;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.mybatis.spring.SqlSessionTemplate;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.*;
import org.springframework.mock.env.MockEnvironment;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

/** Real MySQL + mapper + transaction + task runner; only model transport and unrelated boundaries are synthetic. */
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@EnabledIfEnvironmentVariable(named = "SYSTEM_MODEL_TEST_JDBC_URL", matches = ".+")
class LegacyTranslationMySqlTest {
    private static final String SOURCE = "first part. second part. third part.";
    private static final ObjectMapper JSON = new ObjectMapper();
    private SystemModelMySqlFixture db;
    private SqlSessionTemplate sql;
    private AiModelRouter router;
    private SystemModelExecutionService executions;
    private SystemModelUrlPolicy urls;
    private long user;
    private String task;
    private SystemModelExecutionRef ref;
    private final AtomicInteger calls = new AtomicInteger();
    private IntFunction<OpenAiCompatibleClientResponse> responses;
    private SubtitleTranslationProperties properties;

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement(proxyTargetClass = true)
    @ComponentScan(basePackages = {"com.example.courselingo.subtitle.service", "com.example.courselingo.task.runner"},
        useDefaultFilters = false, includeFilters = @ComponentScan.Filter(type = FilterType.REGEX, pattern = {
            ".*\\.SubtitleTranslationPersistenceService", ".*\\.TranslateSubtitleSegmentsStep", ".*\\.WriteAiCallRecordStep"}))
    @Import({SubtitleTranslationServiceImpl.class, SubtitleTranslationResponseParser.class, AiCallRecordServiceImpl.class,
        AiCallRecordSanitizer.class, AnalysisTaskStateServiceImpl.class, AnalysisTaskStateMachine.class})
    static class Beans {}

    @BeforeAll
    void databaseAndFrozenRouting() throws Exception {
        db = new SystemModelMySqlFixture();
        var config = new MybatisConfiguration();
        config.setMapUnderscoreToCamelCase(true);
        for (var mapper : List.of(SubtitleSegmentMapper.class, SubtitleTranslationSegmentMapper.class,
                TaskFullTextResultMapper.class, AnalysisTaskMapper.class, TaskLogMapper.class, AiCallRecordMapper.class))
            config.addMapper(mapper);
        var factory = new MybatisSqlSessionFactoryBean();
        factory.setDataSource(db.dataSource);
        factory.setConfiguration(config);
        sql = new SqlSessionTemplate(factory.getObject());

        urls = new SystemModelUrlPolicy(host -> new java.net.InetAddress[]{java.net.InetAddress.getByName("8.8.8.8")});
        var routing = new AiModelRoutingProperties();
        var profile = new AiModelProfile();
        profile.setProviderType("openai-compatible"); profile.setBaseUrl("https://api.deepseek.com");
        profile.setModelName("synthetic-model"); profile.setApiKeyEnvName("SYNTHETIC_TEST_MODEL");
        profile.setCapabilities(Set.of(ModelCapability.TEXT_CHAT, ModelCapability.JSON_OUTPUT, ModelCapability.VISION));
        routing.setProfiles(Map.of("test", profile));
        var stages = new EnumMap<AiModelStage, String>(AiModelStage.class);
        for (var stage : AiModelStage.values()) stages.put(stage, "test");
        routing.setRoutes(stages); router = new AiModelRouter(routing);
        var cipher = new SystemModelSecretCipher(SystemModelSecretCipherTest.TEST_KEY);
        var llm = new OpenAiCompatibleLlmProperties(); llm.setEnabled(true); llm.setApiKey("synthetic-fixture-only");
        var env = new MockEnvironment().withProperty("courselingo.subtitle.translation.full-text.enabled", "true");
        var registry = new SystemModelRegistry(db.jdbc, db.transactions, cipher, urls,
            new SystemModelEnvironment(env, router, llm, cipher).capture());
        registry.initialize();
        long admin = db.user();
        long provider = registry.saveProvider(null, new SystemModelCommands.Provider(registry.currentVersion(), "translation-test",
            SystemModelProtocol.OPENAI_CHAT, "https://api.deepseek.com", true, "synthetic-fixture-only", false), admin).providers().getLast().id();
        long model = registry.saveModel(null, provider, new SystemModelCommands.Model(registry.currentVersion(), "synthetic-model",
            Set.of("TEXT_CHAT", "JSON_OUTPUT"), null, true), admin).models().getLast().id();
        registry.bindings(new SystemModelCommands.Bindings(registry.currentVersion(), Map.of("TRANSLATION_FULL_TEXT", model)), admin);
        executions = new SystemModelExecutionService(db.jdbc, registry, db.transactions);
    }

    @AfterAll void cleanup() throws Exception { if (db != null) db.close(); }

    @BeforeEach
    void newTask() {
        user = db.user(); task = db.task(user);
        db.jdbc.update("UPDATE analysis_task SET status='QUEUED',source_language='en' WHERE id=?", task);
        db.jdbc.update("INSERT INTO subtitle_segment(task_id,user_id,segment_index,start_millis,end_millis,text,language) VALUES(?,?,0,0,30000,?,'en')", task, user, SOURCE);
        ref = executions.freezePipeline(task, user);
        calls.set(0); responses = n -> response("stop", valid(), 2, 3);
        properties = new SubtitleTranslationProperties();
        properties.getFullText().setEnabled(true);
        properties.getFullText().setBatchConcurrency(1);
        properties.getFullText().setSingleSegmentMaxPieceChars(12);
        properties.getFullText().setSingleSegmentMinPieceChars(5);
    }

    @Test
    void completedOutputCommitsWithTaskAndRecordAndDuplicateDeliveryDoesNotCallAgain() {
        application((runner, message) -> {
            runner.run(message);
            assertThat(status()).isEqualTo("SUCCEEDED");
            assertThat(count("subtitle_translation_segment")).isEqualTo(1);
            assertThat(count("task_full_text_result")).isEqualTo(1);
            assertThat(count("translation_call_diagnostic")).isEqualTo(1);
            assertThat(db.jdbc.queryForObject("SELECT provider_reason FROM translation_call_diagnostic WHERE task_id=?", String.class, task)).isEqualTo("PASSED");
            var record = callRecord();
            assertThat(record.get("status")).isEqualTo("SUCCEEDED");
            assertThat(((Number)record.get("total_tokens")).intValue()).isEqualTo(5);
            assertDuplicateDoesNotMutate(runner, message, 1);
        });
    }

    @Test
    void emptyLengthRecoversWithinExistingSplitAndAllUsageSurvivesInMysql() {
        responses = n -> n == 1 ? response("length", "", 903, 3073) : response("stop", valid(), 2, 3);
        application((runner, message) -> {
            runner.run(message);
            assertThat(status()).isEqualTo("SUCCEEDED");
            assertThat(calls.get()).isEqualTo(4);
            assertThat(count("subtitle_translation_segment")).isEqualTo(1);
            assertThat(count("task_full_text_result")).isEqualTo(1);
            var failed = db.jdbc.queryForMap("SELECT http_status,finish_reason,provider_reason,total_tokens,validation_category,config_version FROM translation_call_diagnostic WHERE task_id=? AND provider_reason='OUTPUT_TRUNCATED'", task);
            assertThat(((Number)failed.get("http_status")).intValue()).isEqualTo(200);
            assertThat(failed.get("finish_reason")).isEqualTo("length");
            assertThat(((Number)failed.get("total_tokens")).intValue()).isEqualTo(3976);
            assertThat(failed.get("validation_category")).isNull();
            assertThat(((Number)failed.get("config_version")).longValue()).isEqualTo(ref.configVersion());
            var record = callRecord();
            assertThat(record.get("status")).isEqualTo("SUCCEEDED");
            assertThat(((Number)record.get("batch_count")).intValue()).isEqualTo(4);
            assertThat(((Number)record.get("retry_count")).intValue()).isEqualTo(3);
            assertThat(((Number)record.get("prompt_tokens")).intValue()).isEqualTo(909);
            assertThat(((Number)record.get("completion_tokens")).intValue()).isEqualTo(3082);
            assertThat(((Number)record.get("total_tokens")).intValue()).isEqualTo(3991);
            assertThat(db.jdbc.queryForObject("SELECT SUM(total_tokens) FROM translation_call_diagnostic WHERE task_id=?", Long.class, task)).isEqualTo(3991);
            assertDuplicateDoesNotMutate(runner, message, 4);
        });
    }

    @ParameterizedTest
    @ValueSource(strings = {"", "{bad", "[]"})
    void actuallyInvalidOutputFailsWithoutBlindRetryOrPartialPublication(String content) {
        responses = n -> response("stop", content, 2, 3);
        application((runner, message) -> {
            assertThatThrownBy(() -> runner.run(message)).isInstanceOf(com.example.courselingo.common.exception.BusinessException.class);
            assertThat(status()).isEqualTo("FAILED");
            assertThat(calls.get()).isEqualTo(1);
            assertNoPublication();
            var record = callRecord();
            assertThat(record.get("status")).isEqualTo("FAILED");
            assertThat(record.get("error_code")).isEqualTo("OUTPUT_INVALID");
            assertThat(record.get("error_message").toString()).contains("httpStatus=200", "check=");
            assertThat(record.get("retryable").toString()).isIn("false", "0");
            assertDuplicateDoesNotMutate(runner, message, 1);
        });
    }

    @Test
    void depthExhaustionIsFailedAndAllTruncatedCallsRemainRecorded() {
        properties.getFullText().setSingleSegmentMaxDepth(1);
        responses = n -> response("length", "", 903, 3073);
        application((runner, message) -> {
            assertThatThrownBy(() -> runner.run(message)).isInstanceOf(com.example.courselingo.common.exception.BusinessException.class);
            assertThat(calls.get()).isEqualTo(2);
            assertThat(status()).isEqualTo("FAILED"); assertNoPublication();
            assertThat(callRecord().get("error_message").toString()).contains("reason=TRUNCATED", "check=OUTPUT_TRUNCATED", "httpStatus=200");
            assertThat(count("translation_call_diagnostic")).isEqualTo(2);
            assertThat(db.jdbc.queryForObject("SELECT SUM(total_tokens) FROM translation_call_diagnostic WHERE task_id=? AND provider_reason='OUTPUT_TRUNCATED'", Long.class, task)).isEqualTo(7952);
            assertDuplicateDoesNotMutate(runner, message, 2);
        });
    }

    @Test
    void mysqlWriteFailureRollsBackBothArtifactsButKeepsDiagnosticsAndFailedTask() {
        db.jdbc.update("INSERT INTO subtitle_translation_segment(task_id,user_id,segment_index,start_millis,end_millis,source_language,target_language,translated_text,provider) VALUES(?,?,0,0,30000,'en','zh-CN','旧合成译文','test')", task, user);
        db.jdbc.update("INSERT INTO task_full_text_result(task_id,user_id,source_language,target_language,source_full_text,translated_full_text,provider,created_at,updated_at) VALUES(?,?,'en','zh-CN','old synthetic','旧合成译文','test',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)", task, user);
        var oldSegment = db.jdbc.queryForMap("SELECT * FROM subtitle_translation_segment WHERE task_id=?", task);
        var oldFull = db.jdbc.queryForMap("SELECT * FROM task_full_text_result WHERE task_id=?", task);
        long revision = db.jdbc.queryForObject("SELECT content_revision FROM analysis_task WHERE id=?", Long.class, task);
        db.jdbc.execute("CREATE TRIGGER reject_translation_full BEFORE INSERT ON task_full_text_result FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic transaction rejection'");
        try {
            application((runner, message) -> {
                assertThatThrownBy(() -> runner.run(message)).isInstanceOf(com.example.courselingo.common.exception.BusinessException.class);
                assertThat(status()).isEqualTo("FAILED");
                assertThat(db.jdbc.queryForMap("SELECT * FROM subtitle_translation_segment WHERE task_id=?", task)).isEqualTo(oldSegment);
                assertThat(db.jdbc.queryForMap("SELECT * FROM task_full_text_result WHERE task_id=?", task)).isEqualTo(oldFull);
                assertThat(db.jdbc.queryForObject("SELECT content_revision FROM analysis_task WHERE id=?", Long.class, task)).isEqualTo(revision);
                assertThat(count("translation_call_diagnostic")).isEqualTo(1);
                assertThat(callRecord().get("status")).isEqualTo("FAILED");
                assertThat(callRecord().get("error_code")).isNotEqualTo("OUTPUT_INVALID");
            });
        } finally { db.jdbc.execute("DROP TRIGGER reject_translation_full"); }
    }

    private void application(java.util.function.BiConsumer<AnalysisTaskRunnerImpl, AnalysisTaskMessage> check) {
        var diagnostics = new TranslationCallDiagnostics(db.jdbc, db.transactions);
        var provider = new SystemModelLlmProvider(executions, req -> responses.apply(calls.incrementAndGet()), urls,
            req -> { throw new AssertionError("No legacy/environment fallback allowed"); }, diagnostics);
        new ApplicationContextRunner().withUserConfiguration(Beans.class)
            .withBean(PlatformTransactionManager.class, () -> db.transactions)
            .withBean(GenerationFence.class, () -> new GenerationFence(db.jdbc, db.transactions))
            .withBean(SystemModelExecutionService.class, () -> executions)
            .withBean(AiModelRoutedLlmRequestFactory.class, () -> new AiModelRoutedLlmRequestFactory(router, executions))
            .withBean(LlmProvider.class, () -> provider)
            .withBean(SubtitleTranslationProperties.class, () -> properties)
            .withBean(TranslationCallDiagnostics.class, () -> diagnostics)
            .withBean(SubtitleSegmentMapper.class, () -> sql.getMapper(SubtitleSegmentMapper.class))
            .withBean(SubtitleTranslationSegmentMapper.class, () -> sql.getMapper(SubtitleTranslationSegmentMapper.class))
            .withBean(TaskFullTextResultMapper.class, () -> sql.getMapper(TaskFullTextResultMapper.class))
            .withBean(AnalysisTaskMapper.class, () -> sql.getMapper(AnalysisTaskMapper.class))
            .withBean(TaskLogMapper.class, () -> sql.getMapper(TaskLogMapper.class))
            .withBean(AiCallRecordMapper.class, () -> sql.getMapper(AiCallRecordMapper.class))
            .withBean(TaskProgressSnapshotService.class, () -> mock(TaskProgressSnapshotService.class))
            .withBean(BusinessMetrics.class, BusinessMetrics::noop)
            .run(context -> {
                assertThat(context).hasNotFailed();
                var steps = new ArrayList<PipelineAnalysisTaskStep>();
                var real = context.getBeansOfType(PipelineAnalysisTaskStep.class).values();
                for (var name : PipelineAnalysisTaskStepName.ordered()) {
                    if (name == PipelineAnalysisTaskStepName.TRANSCRIBE) {
                        steps.add(new SyntheticTranscriptStep(SOURCE));
                        continue;
                    }
                    var existing = real.stream().filter(step -> step.name() == name).findFirst();
                    steps.add(existing.orElseGet(() -> new PipelineAnalysisTaskStep() {
                        public PipelineAnalysisTaskStepName name() { return name; }
                        public void execute(PipelineAnalysisTaskStepContext ctx) {}
                    }));
                }
                var bounded = mock(BoundedTaskExecutor.class);
                when(bounded.submitAndWait(anyString(), anyString(), any())).thenAnswer(i -> ((Callable<?>)i.getArgument(2)).call());
                var claims = mock(TaskClaimService.class);
                when(claims.tryAcquire(anyString(), anyString())).thenReturn(TaskClaimResult.acquiredResult());
                var runner = new AnalysisTaskRunnerImpl(sql.getMapper(AnalysisTaskMapper.class), context.getBean(AnalysisTaskStateService.class),
                    new PipelineAnalysisTaskWorkExecutor(steps), bounded, claims, mock(VideoKeyframeEvidenceLifecycleService.class));
                runner.configureSystemModels(executions);
                var message = new AnalysisTaskMessage(task, task, user, "en", "zh-CN", "event-" + task, "trace-" + task, Instant.now());
                check.accept(runner, message);
            });
    }

    private void assertDuplicateDoesNotMutate(AnalysisTaskRunnerImpl runner, AnalysisTaskMessage message, int expectedCalls) {
        var history = db.jdbc.queryForList("SELECT * FROM ai_call_record WHERE task_id=? ORDER BY id", task);
        String terminal = status();
        assertThatThrownBy(() -> runner.run(message)).isInstanceOf(com.example.courselingo.common.exception.BusinessException.class);
        assertThat(calls.get()).isEqualTo(expectedCalls);
        assertThat(status()).isEqualTo(terminal);
        assertThat(db.jdbc.queryForList("SELECT * FROM ai_call_record WHERE task_id=? ORDER BY id", task)).isEqualTo(history);
    }
    private String status() { return db.jdbc.queryForObject("SELECT status FROM analysis_task WHERE id=?", String.class, task); }
    private long count(String table) { return db.jdbc.queryForObject("SELECT COUNT(*) FROM " + table + " WHERE task_id=?", Long.class, task); }
    private void assertNoPublication() { assertThat(count("subtitle_translation_segment")).isZero(); assertThat(count("task_full_text_result")).isZero(); }
    private Map<String,Object> callRecord() { assertThat(count("ai_call_record")).isEqualTo(1); return db.jdbc.queryForMap("SELECT * FROM ai_call_record WHERE task_id=?", task); }
    private static String valid() { return "{\"segments\":[{\"index\":0,\"text\":\"合成中文译文。\"}]}"; }
    private static OpenAiCompatibleClientResponse response(String finish, String content, int prompt, int completion) {
        try {
            return new OpenAiCompatibleClientResponse(200, JSON.writeValueAsString(Map.of("choices", List.of(Map.of("finish_reason", finish,
                "message", Map.of("content", content))), "usage", Map.of("prompt_tokens", prompt, "completion_tokens", completion, "total_tokens", prompt + completion))), Map.of(), Duration.ofMillis(1));
        } catch (Exception ex) { throw new AssertionError(ex); }
    }
}
