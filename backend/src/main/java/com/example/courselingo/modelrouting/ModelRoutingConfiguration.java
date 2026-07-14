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
    AiModelRoutedLlmRequestFactory aiModelRoutedLlmRequestFactory(AiModelRouter router) {
        return new AiModelRoutedLlmRequestFactory(router);
    }
}
