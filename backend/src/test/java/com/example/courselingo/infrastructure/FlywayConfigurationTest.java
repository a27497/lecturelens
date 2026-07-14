package com.example.courselingo.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.nio.file.Path;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class FlywayConfigurationTest {

    private static final Path MIGRATION_DIR = Path.of("src", "main", "resources", "db", "migration");

    @Autowired
    private Environment environment;

    @Autowired
    private ObjectProvider<Flyway> flywayProvider;

    @Autowired
    private MockMvc mockMvc;

    @Test
    void contextStartsWithFlywayDisabledByDefault() {
        assertThat(environment.getProperty("spring.flyway.enabled")).isEqualTo("false");
        assertThat(flywayProvider.getIfAvailable()).isNull();
    }

    @Test
    void actuatorHealthStillWorksWhenDatabaseHealthIsDisabledByDefault() throws Exception {
        assertThat(environment.getProperty("management.health.db.enabled")).isEqualTo("false");

        mockMvc.perform(get("/actuator/health"))
            .andExpect(status().isOk());
    }

    @Test
    void migrationDirectoryExists() {
        assertThat(MIGRATION_DIR).isDirectory();
    }
}
