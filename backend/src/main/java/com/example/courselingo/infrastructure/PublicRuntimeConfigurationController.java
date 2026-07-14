package com.example.courselingo.infrastructure;

import com.example.courselingo.common.response.ApiResponse;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PublicRuntimeConfigurationController {

    private final Environment environment;

    public PublicRuntimeConfigurationController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/api/public/runtime-configuration")
    public ApiResponse<PublicRuntimeConfigurationResponse> runtimeConfiguration() {
        return ApiResponse.success(new PublicRuntimeConfigurationResponse(DemoAiModeGuard.isDemoMode(environment)));
    }

    public record PublicRuntimeConfigurationResponse(boolean demoMode) {
    }
}
