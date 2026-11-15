package com.example.courselingo.systemmodel;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import static org.assertj.core.api.Assertions.*;

@EnabledIfEnvironmentVariable(named="SYSTEM_MODEL_TEST_JDBC_URL",matches=".+")
class PreparationFlowMySqlTest {
    @Test void laterConfigurationCannotChangeFrozenSourceOnlyMode() throws Exception {
        var live=new java.util.concurrent.atomic.AtomicReference<com.example.courselingo.subtitle.pipeline.PipelineTranslationProperties>();
        try(var f=new PipelineCheckpointFixture(1,true,p->{live.set(p);p.setMaterialsSourceOnly(true);p.getAsr().setEnabled(true);})) {
            var first=f.policies.find(f.task,f.user).orElseThrow();
            assertThat(first.policy().flow().sourceOnly()).isTrue();
            assertThat(first.policy().flow().streamingTranslation()).isFalse();assertThat(first.policy().flow().materialsParallel()).isFalse();
            live.get().setMaterialsSourceOnly(false);
            assertThat(f.policies.find(f.task,f.user).orElseThrow()).isEqualTo(first);
            assertThat(first.policy().asr()).isNotNull();
        }
    }
}
