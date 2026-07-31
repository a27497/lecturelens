package com.example.courselingo.common.time;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;

public final class UtcTimestamps {

    private UtcTimestamps() {
    }

    public static Instant toInstant(LocalDateTime value) {
        return value == null ? null : value.toInstant(ZoneOffset.UTC);
    }

    public static Instant updatedAt(LocalDateTime createdAt, LocalDateTime updatedAt) {
        Instant created = toInstant(createdAt);
        Instant updated = toInstant(updatedAt);
        if (updated == null) {
            return created;
        }
        return created != null && updated.isBefore(created) ? created : updated;
    }
}
