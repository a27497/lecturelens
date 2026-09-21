package com.example.courselingo.reliability;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.example.courselingo.ai.llm.LlmProvider;
import com.example.courselingo.ai.record.service.AiCallRecordService;
import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.qa.domain.CourseQaRecord;
import com.example.courselingo.qa.dto.*;
import com.example.courselingo.qa.mapper.CourseQaRecordMapper;
import com.example.courselingo.qa.service.*;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.task.service.GenerationFence;
import java.time.Clock;
import java.util.List;
import javax.sql.DataSource;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.*;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

@SpringJUnitConfig(CourseQaFailureTransactionTest.Config.class)
class CourseQaFailureTransactionTest {
    @Autowired CourseQaService service;
    @Autowired JdbcTemplate jdbc;
    @Autowired PlatformTransactionManager manager;

    @BeforeEach void schema() {
        jdbc.execute("CREATE TABLE IF NOT EXISTS analysis_task(id VARCHAR(64) PRIMARY KEY,user_id BIGINT,status VARCHAR(32),deleted_at TIMESTAMP,content_revision BIGINT DEFAULT 0)");
        jdbc.execute("CREATE TABLE IF NOT EXISTS qa_failure(status VARCHAR(32))");
        jdbc.update("DELETE FROM analysis_task");
        jdbc.update("DELETE FROM qa_failure");
        jdbc.update("INSERT INTO analysis_task(id,user_id,status) VALUES ('qa_task',42,'SUCCEEDED')");
    }

    @Test void modelFailureRemainsQueryableAfterServiceExceptionAndCallerRollback() {
        var caller = new TransactionTemplate(manager);
        caller.executeWithoutResult(status -> {
            assertThatThrownBy(() -> service.ask("qa_task","Bearer test",new CourseQaAskRequest("What is algebra?")))
                .isInstanceOf(RuntimeException.class);
            status.setRollbackOnly();
        });
        assertThat(jdbc.queryForList("SELECT status FROM qa_failure",String.class)).containsExactly("FAILED");
    }

    @Configuration
    @EnableTransactionManagement
    static class Config {
        @Bean DataSource dataSource() {
            return new DriverManagerDataSource("jdbc:h2:mem:qa_failure_tx;DB_CLOSE_DELAY=-1", "sa", "");
        }
        @Bean JdbcTemplate jdbc(DataSource ds) { return new JdbcTemplate(ds); }
        @Bean PlatformTransactionManager manager(DataSource ds) { return new DataSourceTransactionManager(ds); }
        @Bean GenerationFence fence(JdbcTemplate jdbc,PlatformTransactionManager manager) { return new GenerationFence(jdbc,manager); }
        @Bean CourseQaService service(JdbcTemplate jdbc) {
            var users = mock(CurrentUserService.class);
            when(users.currentUser(anyString())).thenReturn(new CurrentUserResponse(42L,"qa@example.com","ACTIVE"));
            var tasks = mock(AnalysisTaskMapper.class);
            var task = new AnalysisTask(); task.setId("qa_task"); task.setUserId(42L); task.setTargetLanguage("zh-CN");
            when(tasks.selectByIdAndUserId("qa_task",42L)).thenReturn(task);
            var retriever = mock(CourseQaEvidenceRetriever.class);
            when(retriever.retrieve(anyString(),anyLong(),anyString(),anyString())).thenReturn(List.of(
                new CourseQaEvidenceItem("SUBTITLE","1",0L,1000L,"00:00","Linear algebra",null,1.0,"ev",0L)));
            var records = mock(CourseQaRecordMapper.class);
            when(records.insert(any(CourseQaRecord.class))).thenAnswer(call -> {
                CourseQaRecord row = call.getArgument(0); row.setId(1L);
                return jdbc.update("INSERT INTO qa_failure VALUES (?)",row.getStatus());
            });
            var rate = mock(CourseQaRateLimitService.class);
            when(rate.checkAndConsume(42L)).thenReturn(CourseQaRateLimitResult.allowed(10,9));
            var provider = mock(LlmProvider.class);
            when(provider.generate(any())).thenAnswer(call -> {
                assertThat(TransactionSynchronizationManager.isActualTransactionActive()).isFalse();
                throw new IllegalStateException("simulated provider timeout");
            });
            return new CourseQaServiceImpl(users,tasks,retriever,records,provider,mock(AiCallRecordService.class),
                rate,Clock.systemUTC(),new CourseQaResponseParser(),null);
        }
    }
}
