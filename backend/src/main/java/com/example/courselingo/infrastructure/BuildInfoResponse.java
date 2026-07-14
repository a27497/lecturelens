package com.example.courselingo.infrastructure;

import java.time.Instant;
import java.util.List;

public record BuildInfoResponse(
    String application,
    Instant time,
    String gitCommit,
    String javaVersion,
    List<String> activeProfiles
) {
}
