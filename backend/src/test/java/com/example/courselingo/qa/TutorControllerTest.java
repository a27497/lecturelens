package com.example.courselingo.qa;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.study.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import org.junit.jupiter.api.Test;

class TutorControllerTest {
    private final CurrentUserService users = mock(CurrentUserService.class);
    private final StudyProperties properties = new StudyProperties();
    private final StudyEvidenceAuthority authority = mock(StudyEvidenceAuthority.class);
    private final StudyTransport transport = mock(StudyTransport.class);
    private final TutorController controller = new TutorController(users, properties, authority, transport);

    TutorControllerTest() {
        properties.setEnabled(true);
        when(users.currentUser("Bearer owner")).thenReturn(new CurrentUserResponse(42L,"owner@test.invalid","ACTIVE"));
        when(authority.current(eq("course"),eq(42L),anyBoolean())).thenReturn(7L);
        when(transport.tutor(anyMap())).thenReturn(new ObjectMapper().createObjectNode());
    }

    @Test void authenticatedScopeForwardedForCreateListGetTurnAndCancel() {
        controller.create("course","Bearer owner",new TutorController.Create("request"));
        controller.list("course","Bearer owner");
        controller.get("course","session","Bearer owner");
        controller.turn("course","session","Bearer owner",new TutorController.Turn("client","Why is that?",true));
        controller.cancel("course","session","client","Bearer owner");
        var captured = org.mockito.ArgumentCaptor.forClass(Map.class);
        verify(transport,times(5)).tutor(captured.capture());
        for (var payload : captured.getAllValues()) {
            assertThat(payload).containsEntry("owner_id",42L).containsEntry("course_id","course").containsEntry("revision",7L);
        }
        assertThat(captured.getAllValues().get(3)).containsEntry("socratic",true).containsEntry("client_turn_id","client");
        verify(authority,times(2)).current("course",42L,true);
        verify(authority,times(8)).current("course",42L,false);
    }

    @Test void invalidTurnAndRequestIdsNeverForward() {
        for (var invalid : java.util.List.of(new TutorController.Turn("", "question",false),
                new TutorController.Turn("key"," ",false),new TutorController.Turn("key","x".repeat(2001),false))) {
            assertThatThrownBy(() -> controller.turn("course","session","Bearer owner",invalid)).isInstanceOf(BusinessException.class);
        }
        assertThatThrownBy(() -> controller.create("course","Bearer owner",new TutorController.Create("../invalid"))).isInstanceOf(BusinessException.class);
        verifyNoInteractions(transport,authority);
    }

    @Test void ownershipAndDeletionCheckBeforeAgentInvocation() {
        when(authority.current("course",42L,false)).thenThrow(new BusinessException(ErrorCode.TASK_NOT_FOUND));
        assertThatThrownBy(() -> controller.get("course","session","Bearer owner")).isInstanceOf(BusinessException.class);
        verifyNoInteractions(transport);
    }

    @Test void revisionRaceHidesAgentResponse() {
        when(authority.current("course",42L,false)).thenReturn(7L,8L);
        assertThatThrownBy(() -> controller.get("course","session","Bearer owner")).isInstanceOf(BusinessException.class);
    }

    @Test void disabledGatewayDoesNotCallAgent() {
        properties.setEnabled(false);
        assertThatThrownBy(() -> controller.list("course","Bearer owner")).isInstanceOf(BusinessException.class);
        verifyNoInteractions(transport,authority);
    }

    @Test void wireRoutesUseServerIdentityAndDoNotAcceptClientRevision() throws Exception {
        var mvc = org.springframework.test.web.servlet.setup.MockMvcBuilders.standaloneSetup(controller)
            .setControllerAdvice(new com.example.courselingo.common.web.GlobalExceptionHandler()).build();
        mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post("/api/tasks/course/tutor/sessions/session/turns")
            .header("Authorization","Bearer owner").contentType("application/json")
            .content("{\"owner_id\":999,\"revision\":999,\"client_turn_id\":\"client\",\"text\":\"Why?\",\"socratic\":true}"))
            .andExpect(org.springframework.test.web.servlet.result.MockMvcResultMatchers.status().isOk());
        var captured = org.mockito.ArgumentCaptor.forClass(Map.class); verify(transport).tutor(captured.capture());
        assertThat(captured.getValue()).containsEntry("owner_id",42L).containsEntry("revision",7L);
    }
}
