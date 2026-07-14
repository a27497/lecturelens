package com.example.courselingo.media;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(FfmpegProperties.class)
public class FfmpegMediaConfiguration {

    @Bean
    FfmpegProcessExecutor ffmpegProcessExecutor() {
        return new ProcessBuilderFfmpegProcessExecutor();
    }
}
