package com.example.courselingo.systemmodel;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class SystemModelActivationTest {
    @Test
    void disabledLayerStartsWithoutNewMasterKey() {
        new ApplicationContextRunner()
                .withUserConfiguration(SystemModelRuntimeConfiguration.class)
                .withBean(SystemModelSecretCipher.class, () -> new SystemModelSecretCipher(null))
                .run(
                        context -> {
                            assertThat(context).hasNotFailed();
                            assertThat(context).doesNotHaveBean(SystemModelRegistry.class);
                        });
    }

    @Test
    void enabledLayerFailsAtStartupBeforeAnyEncryptOrDecrypt() {
        new ApplicationContextRunner()
                .withUserConfiguration(SystemModelRuntimeConfiguration.class)
                .withBean(SystemModelSecretCipher.class, () -> new SystemModelSecretCipher(null))
                .withPropertyValues(
                        "courselingo.ai.system-models.enabled=true", "spring.flyway.enabled=true")
                .run(
                        context -> {
                            assertThat(context).hasFailed();
                            assertThat(context.getStartupFailure())
                                    .hasRootCauseInstanceOf(BusinessException.class);
                            Throwable root = context.getStartupFailure();
                            while (root.getCause() != null) root = root.getCause();
                            assertThat(((BusinessException) root).errorCode())
                                    .isEqualTo(ErrorCode.SYSTEM_MODEL_MASTER_KEY_MISSING);
                        });
    }
}
