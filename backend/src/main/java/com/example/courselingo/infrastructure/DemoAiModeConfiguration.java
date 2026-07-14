package com.example.courselingo.infrastructure;

import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class DemoAiModeConfiguration {

    @Bean
    static BeanFactoryPostProcessor demoAiModeGuard(Environment environment) {
        return beanFactory -> DemoAiModeGuard.validate(environment);
    }
}
