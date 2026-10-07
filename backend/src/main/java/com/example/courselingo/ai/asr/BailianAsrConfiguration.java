package com.example.courselingo.ai.asr;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(BailianAsrProperties.class)
public class BailianAsrConfiguration {
    @Bean
    @Conditional(AsrProviderSelection.Bailian.class)
    BailianAsrProvider bailianAsrProvider(BailianAsrProperties properties) {
        return new BailianAsrProvider(properties, new JavaHttpBailianAsrTransport(properties.getConnectTimeout()));
    }
}
