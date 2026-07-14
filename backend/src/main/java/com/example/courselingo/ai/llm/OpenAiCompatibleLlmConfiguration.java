package com.example.courselingo.ai.llm;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(OpenAiCompatibleLlmProperties.class)
public class OpenAiCompatibleLlmConfiguration {

    @Bean
    @ConditionalOnProperty(prefix = "courselingo.ai.llm.openai-compatible", name = "enabled", havingValue = "true")
    JavaHttpOpenAiCompatibleLlmClient openAiCompatibleLlmClient(OpenAiCompatibleLlmProperties properties) {
        return new JavaHttpOpenAiCompatibleLlmClient(properties.getConnectTimeout());
    }

    @Bean
    @ConditionalOnProperty(prefix = "courselingo.ai.llm.openai-compatible", name = "enabled", havingValue = "true")
    OpenAiCompatibleLlmProvider openAiCompatibleLlmProvider(
        OpenAiCompatibleLlmProperties properties,
        OpenAiCompatibleLlmClient openAiCompatibleLlmClient
    ) {
        return new OpenAiCompatibleLlmProvider(properties, openAiCompatibleLlmClient);
    }
}
