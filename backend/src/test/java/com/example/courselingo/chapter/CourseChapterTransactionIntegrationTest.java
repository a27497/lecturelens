package com.example.courselingo.chapter;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.example.courselingo.ai.llm.LlmProvider;
import com.example.courselingo.ai.llm.LlmRequest;
import com.example.courselingo.ai.llm.LlmResult;
import com.example.courselingo.ai.record.service.AiCallRecordService;
import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.chapter.domain.CourseChapter;
import com.example.courselingo.chapter.dto.CourseChapterEvidenceItem;
import com.example.courselingo.chapter.mapper.CourseChapterMapper;
import com.example.courselingo.chapter.service.CourseChapterEvidenceBuilder;
import com.example.courselingo.chapter.service.CourseChapterEvidenceBundle;
import com.example.courselingo.chapter.service.CourseChapterProperties;
import com.example.courselingo.chapter.service.CourseChapterResponseParser;
import com.example.courselingo.chapter.service.CourseChapterService;
import com.example.courselingo.chapter.service.CourseChapterServiceImpl;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Clock;
import java.time.Duration;
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

@SpringJUnitConfig(CourseChapterTransactionIntegrationTest.Config.class)
class CourseChapterTransactionIntegrationTest {

    @Autowired
    private CourseChapterService service;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private FakeChapterState state;

    @BeforeEach
    void createSchema() {
        jdbc.execute("DROP TABLE IF EXISTS chapter_probe");
        jdbc.execute("CREATE TABLE chapter_probe (id BIGINT PRIMARY KEY, title VARCHAR(255) NOT NULL)");
        jdbc.update("INSERT INTO chapter_probe (id, title) VALUES (1, 'existing chapter')");
        state.reset();
    }

    @Test
    void insertFailureRollsBackDeleteAndKeepsExistingChapters() {
        state.evidence = validEvidence();
        state.content = validResponse();
        state.failInsert = true;

        assertThatThrownBy(() -> service.generate("task_chapter_tx", "Bearer test"))
            .isInstanceOf(RuntimeException.class);

        assertThat(titles()).containsExactly("existing chapter");
    }

    @Test
    void invalidFallbackNeverDeletesExistingChapters() {
        state.evidence = List.of(new CourseChapterEvidenceItem(
            0, 240_000L, 120_000L, "invalid range", "fictional evidence"
        ));
        state.content = "{\"chapters\":[]}";

        assertThatThrownBy(() -> service.generate("task_chapter_tx", "Bearer test"))
            .isInstanceOf(RuntimeException.class);

        assertThat(state.providerCalls).isEqualTo(2);
        assertThat(titles()).containsExactly("existing chapter");
    }

    @Test
    void emptyPrimaryAndRepairUseOneFallbackThenReplaceAtomically() {
        state.evidence = validEvidence();
        state.content = "{\"chapters\":[]}";

        var chapters = service.generate("task_chapter_tx", "Bearer test");

        assertThat(state.providerCalls).isEqualTo(2);
        assertThat(chapters).singleElement().satisfies(chapter -> {
            assertThat(chapter.title()).isEqualTo("第 1 章：课程内容");
            assertThat(chapter.evidence()).hasSize(2);
        });
        assertThat(titles()).containsExactly("第 1 章：课程内容");
    }

    private List<String> titles() {
        return jdbc.queryForList("SELECT title FROM chapter_probe ORDER BY id", String.class);
    }

    private static List<CourseChapterEvidenceItem> validEvidence() {
        return List.of(
            new CourseChapterEvidenceItem(0, 0L, 240_000L, "00:00-04:00", "fictional introduction"),
            new CourseChapterEvidenceItem(1, 240_000L, 480_000L, "04:00-08:00", "fictional conclusion")
        );
    }

    private static String validResponse() {
        return """
            {"chapters":[
              {"title":"第一章","summary":"介绍","startTimeMillis":0,"endTimeMillis":240000,"evidenceIndexes":[0]},
              {"title":"第二章","summary":"总结","startTimeMillis":240000,"endTimeMillis":480000,"evidenceIndexes":[1]}
            ]}
            """;
    }

    @Configuration
    @EnableTransactionManagement(proxyTargetClass = true)
    static class Config {

        @Bean
        DataSource dataSource() {
            return new EmbeddedDatabaseBuilder().setType(EmbeddedDatabaseType.H2)
                .setName("chapter-tx;MODE=MySQL;DB_CLOSE_DELAY=-1").build();
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
        FakeChapterState fakeChapterState() {
            return new FakeChapterState();
        }

        @Bean
        CourseChapterService courseChapterService(JdbcTemplate jdbc, FakeChapterState state) {
            CurrentUserService users = mock(CurrentUserService.class);
            when(users.currentUser("Bearer test")).thenReturn(new CurrentUserResponse(42L, "test@example.invalid", "ACTIVE"));
            AnalysisTaskMapper tasks = mock(AnalysisTaskMapper.class);
            AnalysisTask task = new AnalysisTask();
            task.setId("task_chapter_tx");
            task.setUserId(42L);
            task.setTargetLanguage("zh-CN");
            task.setStatus("SUCCEEDED");
            when(tasks.selectByIdAndUserId("task_chapter_tx", 42L)).thenReturn(task);

            CourseChapterEvidenceBuilder evidenceBuilder = mock(CourseChapterEvidenceBuilder.class);
            when(evidenceBuilder.build(any(), any(), any())).thenAnswer(ignored ->
                new CourseChapterEvidenceBundle(state.evidence, "fictional context"));

            CourseChapterMapper chapters = mock(CourseChapterMapper.class);
            AtomicLong ids = new AtomicLong(10L);
            when(chapters.deleteByTaskIdAndUserId(any(), any())).thenAnswer(ignored ->
                jdbc.update("DELETE FROM chapter_probe"));
            when(chapters.insert(any(CourseChapter.class))).thenAnswer(invocation -> {
                CourseChapter row = invocation.getArgument(0);
                long id = ids.incrementAndGet();
                row.setId(id);
                int inserted = jdbc.update("INSERT INTO chapter_probe (id, title) VALUES (?, ?)", id, row.getTitle());
                if (state.failInsert) throw new IllegalStateException("fictional chapter insert failure");
                return inserted;
            });

            LlmProvider provider = new LlmProvider() {
                @Override
                public LlmResult generate(LlmRequest request) {
                    state.providerCalls++;
                    return new LlmResult(
                        "fake-chapter", "fictional-model", state.content, "stop", null,
                        Duration.ofMillis(1), Map.of()
                    );
                }

                @Override
                public String providerName() {
                    return "fake-chapter";
                }
            };
            return new CourseChapterServiceImpl(
                users, tasks, chapters, evidenceBuilder, new CourseChapterResponseParser(), provider,
                mock(AiCallRecordService.class), null, new CourseChapterProperties(), new ObjectMapper(),
                Clock.systemUTC()
            );
        }
    }

    static final class FakeChapterState {
        private List<CourseChapterEvidenceItem> evidence = List.of();
        private String content = "";
        private boolean failInsert;
        private int providerCalls;

        private void reset() {
            evidence = List.of();
            content = "";
            failInsert = false;
            providerCalls = 0;
        }
    }
}
