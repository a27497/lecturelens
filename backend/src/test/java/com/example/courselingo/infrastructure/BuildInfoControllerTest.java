package com.example.courselingo.infrastructure;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class BuildInfoControllerTest {

    @Test
    void buildInfoReturnsSafeRuntimeMetadata() throws Exception {
        MockEnvironment environment = new MockEnvironment()
            .withProperty("spring.application.name", "courselingo-pro")
            .withProperty("spring.profiles.active", "e2e,local");
        MockMvc mockMvc = MockMvcBuilders
            .standaloneSetup(new BuildInfoController(environment, () -> "abc1234"))
            .build();

        mockMvc.perform(get("/api/debug/build-info"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.code").value("0"))
            .andExpect(jsonPath("$.data.application").value("courselingo-pro"))
            .andExpect(jsonPath("$.data.gitCommit").value("abc1234"))
            .andExpect(jsonPath("$.data.javaVersion").exists())
            .andExpect(jsonPath("$.data.time").exists())
            .andExpect(jsonPath("$.data.activeProfiles[0]").value("e2e"))
            .andExpect(jsonPath("$.data.activeProfiles[1]").value("local"))
            .andExpect(jsonPath("$").value(not(containsString("password"))))
            .andExpect(jsonPath("$").value(not(containsString("apiKey"))))
            .andExpect(jsonPath("$").value(not(containsString("Authorization"))));
    }
}
