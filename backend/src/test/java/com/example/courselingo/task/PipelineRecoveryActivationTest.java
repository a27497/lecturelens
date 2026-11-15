package com.example.courselingo.task;

import com.example.courselingo.task.service.*;
import com.example.courselingo.subtitle.pipeline.PipelineTranslationProperties;
import com.example.courselingo.mq.AnalysisTaskMessage;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;
import static org.assertj.core.api.Assertions.*;

class PipelineRecoveryActivationTest {
    @Test void defaultDisabledLeavesLegacyRuntimeUsableButRecoveryRequiresIsolatedTopicAndGroup() {
        var config=new PipelineTranslationProperties();var env=new MockEnvironment();
        new PipelineRecoveryActivation(config,env).validate();config.setEnabled(true);
        assertThatThrownBy(()->new PipelineRecoveryActivation(config,env).validate()).isInstanceOf(IllegalStateException.class);
        env.setProperty("courselingo.pipeline.translation-v2.isolated-runtime","true");
        env.setProperty("courselingo.mq.rocketmq.analysis-topic","lecturelens-p21-test");
        env.setProperty("courselingo.mq.rocketmq.consumer-group","lecturelens-p21-test");
        assertThatCode(()->new PipelineRecoveryActivation(config,env).validate()).doesNotThrowAnyException();
        env.setProperty("courselingo.mq.rocketmq.consumer-group","legacy");
        assertThatThrownBy(()->new PipelineRecoveryActivation(config,env).validate()).isInstanceOf(IllegalStateException.class);
    }
    @Test void legacyMessagesRetainTheirWireShapeAndV2EpochIsExplicit() throws Exception {
        var json=new ObjectMapper().findAndRegisterModules();
        var legacy=new AnalysisTaskMessage("t","u",9L,"en","zh-CN","event","trace",java.time.Instant.EPOCH);
        assertThat(json.writeValueAsString(legacy)).doesNotContain("protocolVersion","executionEpoch");
        var v2=json.readValue(json.writeValueAsString(legacy.withExecution(2)),AnalysisTaskMessage.class);
        assertThat(v2.protocol()).isEqualTo(2);assertThat(v2.epoch()).isEqualTo(2);
        assertThat(json.readValue(json.writeValueAsString(legacy),AnalysisTaskMessage.class).protocol()).isEqualTo(1);
    }
}
