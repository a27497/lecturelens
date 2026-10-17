package com.example.courselingo.systemmodel;

import com.example.courselingo.ai.llm.TranslationFailure;

import com.example.courselingo.subtitle.pipeline.*;
import com.example.courselingo.subtitle.service.SubtitleTranslationProperties;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import java.util.UUID;
import static org.assertj.core.api.Assertions.*;

@EnabledIfEnvironmentVariable(named="SYSTEM_MODEL_TEST_JDBC_URL",matches=".+")
class PipelinePolicyMySqlTest {
    @Test void immutablePolicyIsOwnedFrozenAndCascadesWithoutStoringCredentials() throws Exception {
        try(var db=new SystemModelMySqlFixture()) {
            long user=db.user();String task=db.task(user), snapshot=UUID.randomUUID().toString();
            db.jdbc.update("UPDATE analysis_task SET status='CREATED' WHERE id=?",task);
            db.jdbc.update("""
                INSERT INTO system_model_execution_snapshot(id,task_id,user_id,operation_type,operation_id,config_version,resolved_config_json)
                VALUES (?,?,?,'PIPELINE',?,0,'{}')
                """,snapshot,task,user,task);
            var settings=new PipelineTranslationProperties();settings.setEnabled(true);
            var legacy=new SubtitleTranslationProperties();
            var store=new PipelinePolicyService(db.jdbc,settings,legacy);
            var ref=new SystemModelExecutionRef(snapshot,0,task,user);
            store.freeze(ref);
            var first=store.find(task,user).orElseThrow();
            settings.setOutputMax(2048);legacy.getFullText().setMaxTokens(1);settings.setEnabled(false);
            assertThat(store.find(task,user).orElseThrow()).isEqualTo(first);
            assertThat(first.policy().outputMax()).isEqualTo(8192);
            assertThat(store.find(task,user+1)).isEmpty();
            assertThat(db.jdbc.queryForObject("SELECT policy_json FROM pipeline_policy_snapshot WHERE task_id=?",String.class,task))
                .doesNotContain("apiKey","ciphertext","credential","Bearer");
            assertThatThrownBy(()->db.jdbc.update("UPDATE pipeline_policy_snapshot SET engine_version='changed' WHERE task_id=?",task))
                .hasMessageContaining("immutable");
            db.jdbc.update("DELETE FROM analysis_task WHERE id=? AND user_id=?",task,user);
            assertThat(db.jdbc.queryForObject("SELECT COUNT(*) FROM pipeline_policy_snapshot WHERE task_id=?",Integer.class,task)).isZero();
        }
    }
    @Test void disabledLayerDoesNotCreatePoliciesAndCrossOwnerFreezeFails() throws Exception {
        try(var db=new SystemModelMySqlFixture()) {
            long user=db.user();String task=db.task(user);
            var settings=new PipelineTranslationProperties();var store=new PipelinePolicyService(db.jdbc,settings,new SubtitleTranslationProperties());
            store.freeze(null);
            assertThat(store.find(task,user)).isEmpty();
            settings.setEnabled(true);
            assertThatThrownBy(()->store.freeze(new SystemModelExecutionRef("absent",0,task,user+1)))
                .isInstanceOf(TranslationFailure.class);
            assertThat(store.find(task,user)).isEmpty();
        }
    }
}
