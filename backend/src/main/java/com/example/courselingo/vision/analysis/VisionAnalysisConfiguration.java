package com.example.courselingo.vision.analysis;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(VisionAnalysisProperties.class)
public class VisionAnalysisConfiguration {

    @Bean
    HighValueKeyframeSelector highValueKeyframeSelector() {
        return new HighValueKeyframeSelector();
    }

    @Bean
    VisionModelProvider visionModelProvider(VisionAnalysisProperties properties) {
        return new OpenAiCompatibleVisionProvider(properties);
    }
}
