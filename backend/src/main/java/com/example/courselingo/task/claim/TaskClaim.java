package com.example.courselingo.task.claim;

import java.time.Instant;

public record TaskClaim(
    String taskId,
    String requestId,
    Instant claimedAt,
    Instant expiresAt
) {
}
