package com.example.courselingo.systemmodel;

import com.example.courselingo.common.exception.BusinessException;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import java.util.UUID;
import static org.assertj.core.api.Assertions.*;

class SystemModelDisabledTaskGuardTest {
    @Test void invalidSwitchCannotSilentlyRemoveTheExecutionFence() {
        var jdbc = org.mockito.Mockito.mock(JdbcTemplate.class);
        new org.springframework.boot.test.context.runner.ApplicationContextRunner()
                .withUserConfiguration(SystemModelDisabledTaskGuard.class)
                .withBean(JdbcTemplate.class, () -> jdbc)
                .withPropertyValues("courselingo.ai.system-models.enabled=invalid")
                .run(context -> assertThat(context).hasFailed());
        assertThatThrownBy(() -> new SystemModelDisabledTaskGuard(jdbc, false, true).requireLegacyTask("pinned"))
                .isInstanceOf(BusinessException.class).hasNoCause();
    }

    @Test void uninitializedStartupDoesNotConnectButExecutionFailsClosed() {
        var jdbc = org.mockito.Mockito.mock(JdbcTemplate.class);
        var guard = new SystemModelDisabledTaskGuard(jdbc, false);
        org.mockito.Mockito.verifyNoInteractions(jdbc);
        org.mockito.Mockito.when(jdbc.queryForObject(org.mockito.ArgumentMatchers.anyString(), org.mockito.ArgumentMatchers.eq(Boolean.class), org.mockito.ArgumentMatchers.eq("pinned")))
                .thenThrow(new org.springframework.dao.DataAccessResourceFailureException("synthetic unavailable database"));
        assertThatThrownBy(() -> guard.requireLegacyTask("pinned"))
                .isInstanceOf(BusinessException.class).hasNoCause();
    }

    @Test void oldSchemaNeedsNoMasterKeyAndPinnedTasksCannotUseLegacyDefaults() {
        var jdbc = new JdbcTemplate(new DriverManagerDataSource(
                "jdbc:h2:mem:" + UUID.randomUUID() + ";DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE", "sa", ""));
        jdbc.execute("CREATE TABLE analysis_task (id varchar PRIMARY KEY, status varchar)");
        var guard = new SystemModelDisabledTaskGuard(jdbc);
        guard.requireLegacyTask("legacy");
        jdbc.execute("CREATE TABLE system_model_execution_snapshot(task_id varchar, operation_type varchar)");
        jdbc.update("INSERT INTO analysis_task VALUES ('pinned','SUCCEEDED')");
        jdbc.update("INSERT INTO system_model_execution_snapshot VALUES ('pinned','PIPELINE')");
        assertThatThrownBy(() -> guard.requireLegacyTask("pinned"))
                .isInstanceOf(BusinessException.class).hasNoCause();
        guard.requireLegacyTask("legacy");
        jdbc.update("UPDATE analysis_task SET status='QUEUED'");
        assertThatThrownBy(() -> new SystemModelDisabledTaskGuard(jdbc))
                .isInstanceOf(BusinessException.class).hasNoCause();
    }
}
