package com.example.courselingo.systemmodel;

import com.example.courselingo.ai.llm.*;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.modelrouting.AiModelRouter;
import com.example.courselingo.vision.analysis.VisionAnalysisProperties;
import com.example.courselingo.vision.analysis.VisionModelProvider;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.sql.init.dependency.DependsOnDatabaseInitialization;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.core.env.Environment;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

import java.time.Duration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "courselingo.ai.system-models",
        name = "enabled",
        havingValue = "true")
@EnableConfigurationProperties(OpenAiCompatibleLlmProperties.class)
public class SystemModelRuntimeConfiguration {
    @Bean
    SystemModelActivation systemModelActivation(
            SystemModelSecretCipher cipher, Environment environment) {
        if (!cipher.configured())
            throw new BusinessException(ErrorCode.SYSTEM_MODEL_MASTER_KEY_MISSING);
        if (!environment.getProperty("spring.flyway.enabled", Boolean.class, false))
            throw new BusinessException(
                    ErrorCode.SYSTEM_MODEL_CONFIG_UNAVAILABLE,
                    "System model configuration requires Flyway migrations");
        if (environment.getProperty("courselingo.ai.llm.langchain4j.enabled", Boolean.class, false))
            throw new BusinessException(
                    ErrorCode.SYSTEM_MODEL_CONFIG_INVALID,
                    "Disable LangChain4j before enabling the system configuration layer");
        return new SystemModelActivation();
    }

    record SystemModelActivation() {}

    @Bean
    SystemModelUrlPolicy systemModelUrlPolicy() {
        return new SystemModelUrlPolicy();
    }

    @Bean
    @DependsOnDatabaseInitialization
    SystemModelRegistry systemModelRegistry(
            SystemModelActivation activation,
            JdbcTemplate jdbc,
            PlatformTransactionManager transactions,
            SystemModelSecretCipher cipher,
            SystemModelUrlPolicy urls,
            Environment environment,
            AiModelRouter router,
            OpenAiCompatibleLlmProperties properties) {
        var registry =
                new SystemModelRegistry(
                        jdbc,
                        transactions,
                        cipher,
                        urls,
                        new SystemModelEnvironment(environment, router, properties, cipher)
                                .capture());
        registry.initialize();
        return registry;
    }

    @Bean
    SystemModelExecutionService systemModelExecutionService(
            SystemModelRegistry registry,
            JdbcTemplate jdbc,
            PlatformTransactionManager transactions) {
        return new SystemModelExecutionService(jdbc, registry, transactions);
    }

    @Bean(destroyMethod = "close")
    SystemModelHttpClient systemModelHttpClient() {
        return new SystemModelHttpClient(2 * 1024 * 1024);
    }

    @Bean
    @Primary
    LlmProvider systemModelLlmProvider(
            SystemModelExecutionService executions,
            SystemModelHttpClient http,
            SystemModelUrlPolicy urls) {
        return new SystemModelLlmProvider(
                executions,
                http,
                urls,
                new JavaHttpOpenAiCompatibleLlmClient(Duration.ofSeconds(5)));
    }

    @Bean
    @Primary
    VisionModelProvider systemModelVisionProvider(
            SystemModelExecutionService executions,
            SystemModelHttpClient http,
            VisionAnalysisProperties properties,
            SystemModelUrlPolicy urls) {
        return new SystemModelVisionProvider(executions, http, properties, urls);
    }

    @Bean
    com.example.courselingo.ai.asr.AsrAdapterFactory bailianAsrAdapterFactory(
            SystemModelHttpClient http, SystemModelUrlPolicy urls) {
        return com.example.courselingo.ai.asr.AsrAdapterFactories.bailian(http, urls);
    }

    @Bean
    com.example.courselingo.ai.asr.AsrAdapterFactory siliconFlowAsrAdapterFactory(
            SystemModelHttpClient http, SystemModelUrlPolicy urls) {
        return com.example.courselingo.ai.asr.AsrAdapterFactories.siliconFlow(http, urls);
    }

    @Bean
    @Primary
    com.example.courselingo.ai.asr.SpeechToTextProvider systemModelAsrProvider(
            SystemModelExecutionService executions,
            java.util.List<com.example.courselingo.ai.asr.AsrAdapterFactory> factories) {
        return new SystemModelAsrProvider(executions, factories);
    }

    @Bean(destroyMethod = "close")
    SystemModelVersionNotifications systemModelVersionNotifications(
            SystemModelRegistry registry,
            org.springframework.beans.factory.ObjectProvider<
                            org.springframework.data.redis.core.StringRedisTemplate>
                    templates,
            org.springframework.beans.factory.ObjectProvider<
                            org.springframework.data.redis.connection.RedisConnectionFactory>
                    factories) {
        return new SystemModelVersionNotifications(
                registry, templates.getIfAvailable(), factories.getIfAvailable());
    }
}
