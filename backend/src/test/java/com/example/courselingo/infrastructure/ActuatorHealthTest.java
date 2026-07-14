package com.example.courselingo.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.Status;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ActuatorHealthTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void contextStartsWithActuatorHealthEndpoint() throws Exception {
        mockMvc.perform(get("/actuator/health"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("UP"))
            .andExpect(jsonPath("$.components").doesNotExist())
            .andExpect(jsonPath("$.details").doesNotExist());
    }

    @Test
    void actuatorInfoEndpointIsExposed() throws Exception {
        mockMvc.perform(get("/actuator/info"))
            .andExpect(status().isOk());
    }

    @Test
    void actuatorEnvEndpointIsNotExposed() throws Exception {
        mockMvc.perform(get("/actuator/env"))
            .andExpect(status().isNotFound());
    }

    @Test
    void courseLingoHealthIndicatorOnlyReportsApplicationReadiness() {
        CourseLingoHealthIndicator indicator = new CourseLingoHealthIndicator();

        Health health = indicator.health();

        assertThat(health.getStatus()).isEqualTo(Status.UP);
        assertThat(health.getDetails()).containsEntry("app", "courselingo-backend");
        assertThat(health.getDetails()).containsEntry("status", "ready");
        assertThat(health.getDetails()).doesNotContainKeys("password", "token", "secret", "host");
    }
}
