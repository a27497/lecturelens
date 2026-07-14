package com.example.courselingo.ai.llm;

import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class DemoMockLlmConfiguration {

    @Bean
    @ConditionalOnMissingBean(LlmProvider.class)
    @ConditionalOnProperty(prefix = "courselingo.ai.llm.demo-mock", name = "enabled", havingValue = "true")
    DemoMockLlmProvider demoMockLlmProvider() {
        return new DemoMockLlmProvider();
    }
}
