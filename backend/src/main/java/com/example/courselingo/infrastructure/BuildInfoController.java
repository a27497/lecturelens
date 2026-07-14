package com.example.courselingo.infrastructure;

import com.example.courselingo.common.response.ApiResponse;
import java.time.Clock;
import java.time.Instant;
import java.util.Arrays;
import java.util.List;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BuildInfoController {

    private static final String DEFAULT_APPLICATION = "courselingo-pro";

    private final Environment environment;
    private final GitCommitResolver gitCommitResolver;
    private final Clock clock;

    @Autowired
    public BuildInfoController(Environment environment, GitCommitResolver gitCommitResolver) {
        this(environment, gitCommitResolver, Clock.systemUTC());
    }

    BuildInfoController(Environment environment, GitCommitResolver gitCommitResolver, Clock clock) {
        this.environment = environment;
        this.gitCommitResolver = gitCommitResolver;
        this.clock = clock == null ? Clock.systemUTC() : clock;
    }

    @GetMapping("/api/debug/build-info")
    ApiResponse<BuildInfoResponse> buildInfo() {
        return ApiResponse.success(new BuildInfoResponse(
            application(),
            Instant.now(clock),
            gitCommitResolver.resolveGitCommit(),
            System.getProperty("java.version"),
            activeProfiles()
        ));
    }

    private String application() {
        String value = environment.getProperty("management.metrics.tags.application");
        if (value == null || value.isBlank()) {
            value = environment.getProperty("spring.application.name");
        }
        return value == null || value.isBlank() ? DEFAULT_APPLICATION : value.strip();
    }

    private List<String> activeProfiles() {
        return Arrays.stream(environment.getActiveProfiles())
            .filter(profile -> profile != null && !profile.isBlank())
            .map(String::strip)
            .toList();
    }
}
