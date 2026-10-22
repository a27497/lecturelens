package com.example.courselingo.systemmodel;

import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.web.GlobalExceptionHandler;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import java.util.List;

class CourseModelUsageControllerTest {
    @Test void authenticationAndOwnerComeFromCurrentSession() throws Exception {
        var users = mock(CurrentUserService.class);
        var usage = mock(CourseModelUsageService.class);
        var mvc = MockMvcBuilders.standaloneSetup(new CourseModelUsageController(users, usage))
                .setControllerAdvice(new GlobalExceptionHandler()).build();
        when(users.currentUser(null)).thenThrow(new BusinessException(ErrorCode.COMMON_UNAUTHORIZED));
        mvc.perform(get("/api/tasks/course/model-usage")).andExpect(status().isUnauthorized());
        verifyNoInteractions(usage);
        when(users.currentUser("Bearer owner")).thenReturn(new CurrentUserResponse(42L, "owner@example.invalid", "ACTIVE"));
        when(usage.read("course", 42L)).thenReturn(new CourseModelUsageService.Usage("course", null, List.of(), List.of(), List.of()));
        mvc.perform(get("/api/tasks/course/model-usage?owner=999&snapshotId=foreign").header("Authorization", "Bearer owner")).andExpect(status().isOk()).andExpect(org.springframework.test.web.servlet.result.MockMvcResultMatchers.header().string("Cache-Control", "no-store"));
        verify(usage).read("course", 42L);
        when(usage.read("foreign", 42L)).thenThrow(new BusinessException(ErrorCode.TASK_NOT_FOUND));
        mvc.perform(get("/api/tasks/foreign/model-usage").header("Authorization", "Bearer owner")).andExpect(status().isNotFound());
    }
}
