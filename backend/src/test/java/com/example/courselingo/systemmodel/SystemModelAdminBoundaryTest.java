package com.example.courselingo.systemmodel;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.courselingo.auth.entity.UserAccount;
import com.example.courselingo.auth.entity.UserRole;
import com.example.courselingo.auth.mapper.UserAccountMapper;
import com.example.courselingo.auth.service.AdminAuthorizationService;
import com.example.courselingo.auth.service.CurrentUserServiceImpl;
import com.example.courselingo.auth.service.JwtAccessTokenService;
import com.example.courselingo.infrastructure.JwtAccessTokenProperties;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpMethod;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RestController;

@WebMvcTest(SystemModelCapabilitiesController.class)
@Import({SystemModelAdminWebConfiguration.class, AdminAuthorizationService.class, CurrentUserServiceImpl.class,
    JwtAccessTokenService.class, SystemModelAdminBoundaryTest.MutationFixture.class})
class SystemModelAdminBoundaryTest {
    private static final String SECRET = "system-model-test-access-secret-at-least-32-chars";
    private static final String CAPABILITIES = "/api/admin/system-models/capabilities";
    @Autowired private MockMvc mvc;
    @Autowired private JwtAccessTokenService tokens;
    @MockitoBean private UserAccountMapper accounts;
    private UserAccount account;

    @TestConfiguration
    static class TokenConfiguration {
        @Bean
        JwtAccessTokenProperties jwtAccessTokenProperties() {
            return new JwtAccessTokenProperties(SECRET, 3600);
        }
    }

    @BeforeEach
    void setUp() {
        account = new UserAccount();
        account.setId(17L);
        account.setEmail("admin-test@example.invalid");
        account.setStatus("ACTIVE");
        when(accounts.selectById(17L)).thenReturn(account);
    }

    @Test
    void anonymousAndForgedRoleHeadersCannotReadCapabilities() throws Exception {
        mvc.perform(get(CAPABILITIES).header("X-Role", "ADMIN").header("X-User-Id", "17"))
            .andExpect(status().isUnauthorized());
        mvc.perform(get(CAPABILITIES).header("Authorization", "Bearer invalid"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void userCannotReadCapabilities() throws Exception {
        mvc.perform(get(CAPABILITIES).header("Authorization", bearer()))
            .andExpect(status().isForbidden());
    }

    @Test
    void administratorSeesOnlySupportedProtocolsAndUnconnectedFusion() throws Exception {
        account.setRole(UserRole.ADMIN);
        mvc.perform(get(CAPABILITIES).header("Authorization", bearer()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.protocols.length()").value(3))
            .andExpect(jsonPath("$.data.features[?(@.key == 'FUSION_SUMMARY')].connected").value(org.hamcrest.Matchers.contains(false)));
    }

    @Test
    void revokedAdminTokenLosesAccessImmediately() throws Exception {
        account.setRole(UserRole.ADMIN);
        String oldToken = bearer();
        account.setRole(UserRole.USER);
        mvc.perform(get(CAPABILITIES).header("Authorization", oldToken)).andExpect(status().isForbidden());
    }

    @Test
    void legacyTokenUsesCurrentDatabaseRoleAndMeReportsIt() throws Exception {
        account.setRole(UserRole.ADMIN);
        String legacy = Jwts.builder().subject("17").claim("type", "access")
            .expiration(Date.from(Instant.now().plusSeconds(3600)))
            .signWith(Keys.hmacShaKeyFor(SECRET.getBytes(StandardCharsets.UTF_8))).compact();
        assertThat(tokens.parseAccessToken(legacy).role()).isEqualTo(UserRole.USER);
        mvc.perform(get(CAPABILITIES).header("Authorization", "Bearer " + legacy)).andExpect(status().isOk());
        var current = new CurrentUserServiceImpl(tokens, accounts).currentUser("Bearer " + legacy);
        assertThat(current.role()).isEqualTo(UserRole.ADMIN);
    }

    @Test
    void disabledOrDeletedAdminCannotAccess() throws Exception {
        account.setRole(UserRole.ADMIN);
        String token = bearer();
        account.setStatus("DISABLED");
        mvc.perform(get(CAPABILITIES).header("Authorization", token)).andExpect(status().isForbidden());
        when(accounts.selectById(17L)).thenReturn(null);
        mvc.perform(get(CAPABILITIES).header("Authorization", token)).andExpect(status().isUnauthorized());
    }

    @ParameterizedTest
    @EnumSource(value = RequestMethod.class, names = {"POST", "PUT", "PATCH", "DELETE"})
    void allMutationMethodsPassThroughDatabaseAdminGuard(RequestMethod method) throws Exception {
        String path = "/api/admin/system-models/test-boundary";
        HttpMethod verb = HttpMethod.valueOf(method.name());
        mvc.perform(request(verb, path)).andExpect(status().isUnauthorized());
        mvc.perform(request(verb, path).header("Authorization", bearer())).andExpect(status().isForbidden());
        account.setRole(UserRole.ADMIN);
        mvc.perform(request(verb, path).header("Authorization", bearer())).andExpect(status().isOk());
    }

    private String bearer() { return "Bearer " + tokens.generate(account); }

    @RestController
    static class MutationFixture {
        @RequestMapping(path = "/api/admin/system-models/test-boundary",
            method = {RequestMethod.POST, RequestMethod.PUT, RequestMethod.PATCH, RequestMethod.DELETE})
        public String mutate() { return "ok"; }
    }
}
