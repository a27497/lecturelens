package com.example.courselingo.ai.asr;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(MockAsrProperties.class)
public class MockAsrConfiguration {

    @Bean
    @ConditionalOnProperty(prefix = "courselingo.ai.asr.mock", name = "enabled", havingValue = "true")
    MockAsrProvider mockAsrProvider(MockAsrProperties properties) {
        return new MockAsrProvider(properties);
    }
}
