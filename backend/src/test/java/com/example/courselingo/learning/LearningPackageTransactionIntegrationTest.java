package com.example.courselingo.learning;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.example.courselingo.ai.llm.LlmProvider;
import com.example.courselingo.ai.llm.LlmRequest;
import com.example.courselingo.ai.llm.LlmResult;
import com.example.courselingo.learning.domain.LearningPackage;
import com.example.courselingo.learning.mapper.LearningPackageMapper;
import com.example.courselingo.learning.service.GenerateLearningPackageCommand;
import com.example.courselingo.learning.service.LearningPackageResponseParser;
import com.example.courselingo.learning.service.LearningPackageService;
import com.example.courselingo.learning.service.LearningPackageServiceImpl;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.subtitle.domain.SubtitleTranslationSegment;
import com.example.courselingo.subtitle.mapper.SubtitleSegmentMapper;
import com.example.courselingo.subtitle.mapper.SubtitleTranslationSegmentMapper;
import java.time.Clock;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;
import javax.sql.DataSource;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseBuilder;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseType;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringJUnitConfig(LearningPackageTransactionIntegrationTest.Config.class)
class LearningPackageTransactionIntegrationTest {

    @Autowired
    private LearningPackageService service;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private FakeLearningState state;

    @BeforeEach
    void createSchema() {
        jdbc.execute("CREATE TABLE IF NOT EXISTS analysis_task (id VARCHAR(64) PRIMARY KEY, user_id BIGINT, status VARCHAR(32), deleted_at TIMESTAMP, content_revision BIGINT DEFAULT 0)");
        jdbc.execute("CREATE TABLE IF NOT EXISTS task_generation (task_id VARCHAR(64), scope VARCHAR(128), generation_id VARCHAR(64), PRIMARY KEY(task_id,scope))");
        jdbc.update("DELETE FROM task_generation");
        jdbc.update("DELETE FROM analysis_task");
        jdbc.update("INSERT INTO analysis_task(id,user_id,status) VALUES ('task_learning_tx',42,'SUCCEEDED')");
        jdbc.execute("DROP TABLE IF EXISTS learning_package_probe");
        jdbc.execute("CREATE TABLE learning_package_probe (id BIGINT PRIMARY KEY, title VARCHAR(255) NOT NULL)");
        jdbc.update("INSERT INTO learning_package_probe (id, title) VALUES (1, 'existing package')");
        state.failInsert = false;
    }

    @Test
    void insertFailureRollsBackDeleteAndKeepsExistingPackage() {
        state.failInsert = true;

        assertThatThrownBy(() -> service.generateLearningPackage(command()))
            .isInstanceOf(RuntimeException.class);

        assertThat(titles()).containsExactly("existing package");
    }

    @Test
    void successfulGenerationAtomicallyReplacesExistingPackage() {
        int saved = service.generateLearningPackage(command());

        assertThat(saved).isEqualTo(1);
        assertThat(titles()).containsExactly("微服务课程资料");
    }

    private List<String> titles() {
        return jdbc.queryForList("SELECT title FROM learning_package_probe ORDER BY id", String.class);
    }

    private static GenerateLearningPackageCommand command() {
        return new GenerateLearningPackageCommand("task_learning_tx", 42L, "en", "zh-CN", "request_tx");
    }

    @Configuration
    @EnableTransactionManagement(proxyTargetClass = true)
    static class Config {
        @Bean
        com.example.courselingo.task.service.GenerationFence generationFence(JdbcTemplate jdbc, PlatformTransactionManager manager) {
            return new com.example.courselingo.task.service.GenerationFence(jdbc, manager);
        }


        @Bean
        DataSource dataSource() {
            return new EmbeddedDatabaseBuilder().setType(EmbeddedDatabaseType.H2)
                .setName("learning-tx;MODE=MySQL;DB_CLOSE_DELAY=-1").build();
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        FakeLearningState fakeLearningState() {
            return new FakeLearningState();
        }

        @Bean
        LearningPackageService learningPackageService(JdbcTemplate jdbc, FakeLearningState state) {
            SubtitleSegmentMapper sources = mock(SubtitleSegmentMapper.class);
            when(sources.selectByTaskIdAndUserId("task_learning_tx", 42L)).thenReturn(List.of(
                source(0, "Spring Boot introduces microservices."),
                source(1, "Docker runs the service containers.")
            ));
            SubtitleTranslationSegmentMapper translations = mock(SubtitleTranslationSegmentMapper.class);
            when(translations.selectByTaskIdUserIdAndTargetLanguage("task_learning_tx", 42L, "zh-CN"))
                .thenReturn(List.of(
                    translation(0, "Spring Boot 介绍微服务。"),
                    translation(1, "Docker 运行服务容器。")
                ));
            LearningPackageMapper packages = mock(LearningPackageMapper.class);
            AtomicLong ids = new AtomicLong(10L);
            when(packages.deleteByTaskIdUserIdAndTargetLanguage(any(), any(), any())).thenAnswer(ignored ->
                jdbc.update("DELETE FROM learning_package_probe"));
            when(packages.insert(any(LearningPackage.class))).thenAnswer(invocation -> {
                LearningPackage row = invocation.getArgument(0);
                long id = ids.incrementAndGet();
                row.setId(id);
                int inserted = jdbc.update(
                    "INSERT INTO learning_package_probe (id, title) VALUES (?, ?)", id, row.getTitle()
                );
                if (state.failInsert) throw new IllegalStateException("fictional package insert failure");
                return inserted;
            });
            LlmProvider provider = new LlmProvider() {
                @Override
                public LlmResult generate(LlmRequest request) {
                    assertThat(org.springframework.transaction.support.TransactionSynchronizationManager.isActualTransactionActive()).isFalse();
                    return new LlmResult(
                        "fake-learning", "fictional-model",
                        """
                        {"title":"微服务课程资料","summary":"课程介绍微服务与容器运行。",\
                         "keyPoints":["Spring Boot 介绍微服务"],"glossary":[],"qa":[]}
                        """,
                        "stop", null, Duration.ofMillis(1), Map.of()
                    );
                }

                @Override
                public String providerName() {
                    return "fake-learning";
                }
            };
            return new LearningPackageServiceImpl(
                sources, translations, packages, provider, Clock.systemUTC(), new LearningPackageResponseParser()
            );
        }

        private static SubtitleSegment source(int index, String text) {
            SubtitleSegment row = new SubtitleSegment();
            row.setTaskId("task_learning_tx");
            row.setUserId(42L);
            row.setSegmentIndex(index);
            row.setStartMillis(index * 1_000L);
            row.setEndMillis(index * 1_000L + 900L);
            row.setLanguage("en");
            row.setText(text);
            row.setProvider("fake");
            row.setCreatedAt(LocalDateTime.now(Clock.systemUTC()));
            row.setUpdatedAt(row.getCreatedAt());
            return row;
        }

        private static SubtitleTranslationSegment translation(int index, String text) {
            SubtitleTranslationSegment row = new SubtitleTranslationSegment();
            row.setTaskId("task_learning_tx");
            row.setUserId(42L);
            row.setSegmentIndex(index);
            row.setStartMillis(index * 1_000L);
            row.setEndMillis(index * 1_000L + 900L);
            row.setSourceLanguage("en");
            row.setTargetLanguage("zh-CN");
            row.setTranslatedText(text);
            row.setProvider("fake");
            row.setCreatedAt(LocalDateTime.now(Clock.systemUTC()));
            row.setUpdatedAt(row.getCreatedAt());
            return row;
        }
    }

    static final class FakeLearningState {
        private boolean failInsert;
    }
}
