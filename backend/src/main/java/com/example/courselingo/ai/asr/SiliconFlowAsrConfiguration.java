package com.example.courselingo.ai.asr;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(SiliconFlowAsrProperties.class)
public class SiliconFlowAsrConfiguration {

    @Bean
    @ConditionalOnProperty(prefix = "courselingo.ai.asr.silicon-flow", name = "enabled", havingValue = "true")
    JavaHttpSiliconFlowAsrClient siliconFlowAsrClient(SiliconFlowAsrProperties properties) {
        return new JavaHttpSiliconFlowAsrClient(properties.getConnectTimeout());
    }

    @Bean
    @ConditionalOnProperty(prefix = "courselingo.ai.asr.silicon-flow", name = "enabled", havingValue = "true")
    SiliconFlowAsrProvider siliconFlowAsrProvider(
        SiliconFlowAsrProperties properties,
        SiliconFlowAsrClient siliconFlowAsrClient
    ) {
        return new SiliconFlowAsrProvider(properties, siliconFlowAsrClient);
    }
}
