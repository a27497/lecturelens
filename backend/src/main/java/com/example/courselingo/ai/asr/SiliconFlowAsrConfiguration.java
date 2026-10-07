package com.example.courselingo.ai.asr;

import org.springframework.context.annotation.Conditional;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(SiliconFlowAsrProperties.class)
public class SiliconFlowAsrConfiguration {

    @Bean
    @Conditional(AsrProviderSelection.SiliconFlow.class)
    JavaHttpSiliconFlowAsrClient siliconFlowAsrClient(SiliconFlowAsrProperties properties) {
        return new JavaHttpSiliconFlowAsrClient(properties.getConnectTimeout());
    }

    @Bean
    @Conditional(AsrProviderSelection.SiliconFlow.class)
    SiliconFlowAsrProvider siliconFlowAsrProvider(
        SiliconFlowAsrProperties properties,
        SiliconFlowAsrClient siliconFlowAsrClient
    ) {
        return new SiliconFlowAsrProvider(properties, siliconFlowAsrClient);
    }
}
