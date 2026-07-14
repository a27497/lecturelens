package com.example.courselingo.ai.llm;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(LangChain4jLlmProperties.class)
public class LangChain4jLlmConfiguration {

    @Bean
    @ConditionalOnProperty(prefix = "courselingo.ai.llm.langchain4j", name = "enabled", havingValue = "true")
    DefaultLangChain4jChatModelClient langChain4jChatModelClient(LangChain4jLlmProperties properties) {
        return new DefaultLangChain4jChatModelClient(properties);
    }

    @Bean
    @ConditionalOnProperty(prefix = "courselingo.ai.llm.langchain4j", name = "enabled", havingValue = "true")
    LangChain4jLlmProvider langChain4jLlmProvider(
        LangChain4jLlmProperties properties,
        LangChain4jChatModelClient langChain4jChatModelClient
    ) {
        return new LangChain4jLlmProvider(properties, langChain4jChatModelClient);
    }
}
