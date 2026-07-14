package com.example.courselingo.media;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(MediaPlaybackProperties.class)
public class MediaPlaybackConfiguration {
}
