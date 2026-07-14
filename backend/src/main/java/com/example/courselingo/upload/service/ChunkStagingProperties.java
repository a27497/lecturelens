package com.example.courselingo.upload.service;

import java.nio.file.Path;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "courselingo.upload")
public record ChunkStagingProperties(Path chunkStagingDir) {
}
