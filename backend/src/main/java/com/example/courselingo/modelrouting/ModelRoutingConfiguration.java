package com.example.courselingo.modelrouting;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(AiModelRoutingProperties.class)
public class ModelRoutingConfiguration {

    @Bean
    AiModelRouter aiModelRouter(AiModelRoutingProperties properties) {
        return new AiModelRouter(properties);
    }

    @Bean
    AiModelRoutedLlmRequestFactory aiModelRoutedLlmRequestFactory(AiModelRouter router,
            org.springframework.beans.factory.ObjectProvider<
                            com.example.courselingo.systemmodel.SystemModelExecutionService>
                    executions) {
        return new AiModelRoutedLlmRequestFactory(router, executions.getIfAvailable());
    }
}
