package com.example.courselingo.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import java.time.Instant;
import java.time.LocalDateTime;
import org.junit.jupiter.api.Test;

class UtcJacksonConfigurationTest {

    @Test
    void legacyLocalDateTimeSerializationAlwaysIncludesUtcZ() throws Exception {
        ObjectMapper mapper = new ObjectMapper().registerModule(
            new UtcJacksonConfiguration().utcLocalDateTimeSerializationModule()
        );

        assertThat(mapper.writeValueAsString(LocalDateTime.of(2026, 7, 31, 3, 47, 20, 69_000_000)))
            .isEqualTo("\"2026-07-31T03:47:20.069Z\"");
    }

    @Test
    void representativeApiPayloadUsesUtcContractForEveryTimeField() throws Exception {
        ObjectMapper mapper = new ObjectMapper()
            .registerModule(new JavaTimeModule())
            .registerModule(new UtcJacksonConfiguration().utcLocalDateTimeSerializationModule())
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
        ApiTimes payload = new ApiTimes(
            LocalDateTime.of(2026, 7, 31, 3, 47, 20, 69_000_000),
            LocalDateTime.of(2026, 7, 31, 4, 0, 0),
            Instant.parse("2026-07-31T04:01:02Z")
        );

        assertThat(mapper.writeValueAsString(payload))
            .contains("\"createdAt\":\"2026-07-31T03:47:20.069Z\"")
            .contains("\"updatedAt\":\"2026-07-31T04:00:00.000Z\"")
            .contains("\"eventAt\":\"2026-07-31T04:01:02Z\"");
    }

    private record ApiTimes(LocalDateTime createdAt, LocalDateTime updatedAt, Instant eventAt) {
    }
}
