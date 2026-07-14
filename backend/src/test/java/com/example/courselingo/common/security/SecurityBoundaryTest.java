package com.example.courselingo.common.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.courselingo.result.controller.TaskResultController;
import com.example.courselingo.task.controller.TaskCommandController;
import com.example.courselingo.task.controller.TaskController;
import com.example.courselingo.task.controller.TaskEventController;
import com.example.courselingo.task.controller.TaskQueryController;
import com.example.courselingo.upload.controller.UploadSessionController;
import java.lang.annotation.Annotation;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.util.Arrays;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityBoundaryTest {

    private static final List<Class<?>> OWNER_PROTECTED_CONTROLLERS = List.of(
        UploadSessionController.class,
        TaskController.class,
        TaskQueryController.class,
        TaskCommandController.class,
        TaskEventController.class,
        TaskResultController.class
    );

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private Environment environment;

    @Test
    void actuatorExposesOnlyHealthInfoAndMetricsWithSecurityHeaders() throws Exception {
        assertThat(environment.getProperty("management.endpoints.web.exposure.include"))
            .isEqualTo("health,info,metrics");
        assertThat(environment.getProperty("management.endpoint.health.show-details"))
            .isEqualTo("never");
        assertThat(environment.getProperty("management.info.env.enabled"))
            .isEqualTo("false");

        for (String path : List.of("/actuator/health", "/actuator/info", "/actuator/metrics")) {
            mockMvc.perform(get(path))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Content-Type-Options", "nosniff"))
                .andExpect(header().string("X-Frame-Options", "DENY"))
                .andExpect(header().string("Referrer-Policy", "no-referrer"))
                .andExpect(header().string("Cache-Control", "no-store"));
        }

        for (String path : List.of(
            "/actuator/env",
            "/actuator/configprops",
            "/actuator/heapdump",
            "/actuator/threaddump",
            "/actuator/loggers",
            "/actuator/prometheus"
        )) {
            mockMvc.perform(get(path))
                .andExpect(status().isNotFound());
        }
    }

    @Test
    void protectedApiErrorsStillCarrySecurityHeaders() throws Exception {
        mockMvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string("X-Content-Type-Options", "nosniff"))
            .andExpect(header().string("X-Frame-Options", "DENY"))
            .andExpect(header().string("Referrer-Policy", "no-referrer"))
            .andExpect(header().string("Cache-Control", "no-store"));
    }

    @Test
    void ownerProtectedControllersDoNotAcceptClientSuppliedOwnerParameters() {
        for (Class<?> controller : OWNER_PROTECTED_CONTROLLERS) {
            for (Method method : controller.getDeclaredMethods()) {
                for (Parameter parameter : method.getParameters()) {
                    assertThat(requestParamName(parameter))
                        .as("%s#%s must not accept userId or ownerId query parameters", controller.getSimpleName(), method.getName())
                        .doesNotContain("userId", "ownerId");
                    assertThat(requestHeaderName(parameter))
                        .as("%s#%s must not accept forged owner headers", controller.getSimpleName(), method.getName())
                        .doesNotContain("X-User-Id", "X-Owner-Id", "userId", "ownerId");
                }
            }
        }
    }

    private static List<String> requestParamName(Parameter parameter) {
        return annotationValues(parameter, RequestParam.class);
    }

    private static List<String> requestHeaderName(Parameter parameter) {
        return annotationValues(parameter, RequestHeader.class);
    }

    private static <A extends Annotation> List<String> annotationValues(Parameter parameter, Class<A> annotationType) {
        A annotation = parameter.getAnnotation(annotationType);
        if (annotation == null) {
            return List.of();
        }
        if (annotation instanceof RequestParam requestParam) {
            return Arrays.stream(new String[] {requestParam.value(), requestParam.name()})
                .filter(value -> value != null && !value.isBlank())
                .toList();
        }
        if (annotation instanceof RequestHeader requestHeader) {
            return Arrays.stream(new String[] {requestHeader.value(), requestHeader.name()})
                .filter(value -> value != null && !value.isBlank())
                .toList();
        }
        return List.of();
    }
}
