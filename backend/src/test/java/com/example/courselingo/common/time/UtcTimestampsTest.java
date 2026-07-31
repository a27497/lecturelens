package com.example.courselingo.common.time;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.time.LocalDateTime;
import org.junit.jupiter.api.Test;

class UtcTimestampsTest {

    @Test
    void interpretsLegacyLocalDateTimeAsUtc() {
        assertThat(UtcTimestamps.toInstant(LocalDateTime.of(2026, 7, 31, 3, 47, 20)))
            .isEqualTo(Instant.parse("2026-07-31T03:47:20Z"));
    }

    @Test
    void clampsLegacyUpdatedTimeThatPredatesCreationWithoutChangingStoredValues() {
        LocalDateTime created = LocalDateTime.of(2026, 7, 31, 3, 47, 20);
        LocalDateTime legacyUpdated = LocalDateTime.of(2026, 7, 30, 19, 49, 3);

        assertThat(UtcTimestamps.updatedAt(created, legacyUpdated))
            .isEqualTo(Instant.parse("2026-07-31T03:47:20Z"));
        assertThat(legacyUpdated).isEqualTo(LocalDateTime.of(2026, 7, 30, 19, 49, 3));
    }
}
