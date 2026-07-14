package com.example.courselingo.infrastructure;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component
public class CourseLingoHealthIndicator implements HealthIndicator {

    @Override
    public Health health() {
        return Health.up()
            .withDetail("app", "courselingo-backend")
            .withDetail("status", "ready")
            .build();
    }
}
