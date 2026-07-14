package com.example.courselingo.common.security;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

class SecurityHeadersFilterTest {

    private final MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new TestController())
        .addFilters(new SecurityHeadersFilter())
        .build();

    @Test
    void addsBaselineSecurityHeadersToApplicationResponses() throws Exception {
        mockMvc.perform(get("/api/test"))
            .andExpect(status().isOk())
            .andExpect(header().string("X-Content-Type-Options", "nosniff"))
            .andExpect(header().string("X-Frame-Options", "DENY"))
            .andExpect(header().string("Referrer-Policy", "no-referrer"))
            .andExpect(header().string("Cache-Control", "no-store"))
            .andExpect(header().string("Pragma", "no-cache"));
    }

    @Test
    void doesNotOverwriteHeadersAlreadySetByDownstreamHandlers() throws Exception {
        mockMvc.perform(get("/api/custom-cache"))
            .andExpect(status().isOk())
            .andExpect(header().string("Cache-Control", "max-age=60"))
            .andExpect(header().string("X-Frame-Options", "SAMEORIGIN"))
            .andExpect(header().string("X-Content-Type-Options", "nosniff"))
            .andExpect(header().string("Referrer-Policy", "no-referrer"));
    }

    @RestController
    private static final class TestController {

        @GetMapping("/api/test")
        String test() {
            return "ok";
        }

        @GetMapping("/api/custom-cache")
        String customCache(jakarta.servlet.http.HttpServletResponse response) {
            response.setHeader("Cache-Control", "max-age=60");
            response.setHeader("X-Frame-Options", "SAMEORIGIN");
            return "ok";
        }
    }
}
