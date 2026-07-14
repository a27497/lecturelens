package com.example.courselingo.upload.service;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(ChunkStagingProperties.class)
public class UploadConfiguration {
}
