package com.example.courselingo.infrastructure;

import com.fasterxml.jackson.databind.module.SimpleModule;
import com.fasterxml.jackson.datatype.jsr310.ser.LocalDateTimeSerializer;
import java.time.format.DateTimeFormatter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class UtcJacksonConfiguration {

    private static final DateTimeFormatter UTC_LOCAL_DATE_TIME = DateTimeFormatter.ofPattern(
        "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'"
    );

    @Bean
    SimpleModule utcLocalDateTimeSerializationModule() {
        SimpleModule module = new SimpleModule("utc-local-date-time");
        module.addSerializer(java.time.LocalDateTime.class, new LocalDateTimeSerializer(UTC_LOCAL_DATE_TIME));
        return module;
    }
}
