package com.example.courselingo.task;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.web.GlobalExceptionHandler;
import com.example.courselingo.task.controller.TaskResumeController;
import com.example.courselingo.task.service.PipelineResumeService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class TaskResumeControllerTest {
    CurrentUserService users=mock(CurrentUserService.class);
    PipelineResumeService resumes=mock(PipelineResumeService.class);
    MockMvc mvc;
    @BeforeEach void setup(){mvc=MockMvcBuilders.standaloneSetup(new TaskResumeController(users,resumes)).setControllerAdvice(new GlobalExceptionHandler()).build();}
    @Test void missingLoginIs401WithoutDispatch() throws Exception {
        when(users.currentUser(null)).thenThrow(new BusinessException(ErrorCode.COMMON_UNAUTHORIZED));
        mvc.perform(post("/api/tasks/t/resume").contentType("application/json").content("{\"expectedExecutionEpoch\":1}"))
            .andExpect(status().isUnauthorized());verifyNoInteractions(resumes);
    }
    @Test void ownerComesFromAuthenticatedUserAndEpochConflictIs409() throws Exception {
        when(users.currentUser("Bearer synthetic")).thenReturn(new CurrentUserResponse(9L,"test@example.invalid","ACTIVE"));
        when(resumes.resume("t",9,1)).thenThrow(new BusinessException(ErrorCode.TASK_RESUME_CONFLICT));
        mvc.perform(post("/api/tasks/t/resume").header("Authorization","Bearer synthetic").contentType("application/json")
            .content("{\"expectedExecutionEpoch\":1,\"userId\":7}"))
            .andExpect(status().isConflict());verify(resumes).resume("t",9,1);
    }
    @Test void nonOwnerIs404AndInvalidEpochIs400() throws Exception {
        when(users.currentUser("Bearer synthetic")).thenReturn(new CurrentUserResponse(9L,"test@example.invalid","ACTIVE"));
        when(resumes.resume("t",9,1)).thenThrow(new BusinessException(ErrorCode.TASK_NOT_FOUND));
        mvc.perform(post("/api/tasks/t/resume").header("Authorization","Bearer synthetic").contentType("application/json").content("{\"expectedExecutionEpoch\":1}"))
            .andExpect(status().isNotFound());
        mvc.perform(post("/api/tasks/t/resume").contentType("application/json").content("{\"expectedExecutionEpoch\":0}"))
            .andExpect(status().isBadRequest());
    }
}
