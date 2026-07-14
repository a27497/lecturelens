package com.example.courselingo.dispatch;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(BoundedTaskExecutorProperties.class)
public class BoundedTaskExecutorConfiguration {
}
