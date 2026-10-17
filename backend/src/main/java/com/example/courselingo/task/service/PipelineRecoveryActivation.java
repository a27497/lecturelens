package com.example.courselingo.task.service;

import com.example.courselingo.subtitle.pipeline.PipelineTranslationProperties;
import jakarta.annotation.PostConstruct;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

/** v2 recovery messages must never be consumed by a legacy worker. */
@Component
public class PipelineRecoveryActivation {
    private final PipelineTranslationProperties properties;
    private final Environment environment;
    public PipelineRecoveryActivation(PipelineTranslationProperties properties,Environment environment){this.properties=properties;this.environment=environment;}
    @PostConstruct public void validate() {
        if(!properties.isEnabled() || !properties.isCheckpointEnabled())return;
        boolean isolated=environment.getProperty("courselingo.pipeline.translation-v2.isolated-runtime",Boolean.class,false);
        String topic=environment.getProperty("courselingo.mq.rocketmq.analysis-topic","");
        String group=environment.getProperty("courselingo.mq.rocketmq.consumer-group","");
        if(!isolated || !topic.startsWith("lecturelens-p21-") || !group.startsWith("lecturelens-p21-"))
            throw new IllegalStateException("Checkpointed pipeline requires an isolated runtime and lecturelens-p21- topic/group");
    }
}
