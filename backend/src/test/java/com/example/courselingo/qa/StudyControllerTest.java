package com.example.courselingo.qa;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.study.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import org.junit.jupiter.api.Test;

class StudyControllerTest {
    @Test void feedbackUsesAuthenticatedScopeAndNotesDoNotRequireAReadyIndex() {
        var users=mock(CurrentUserService.class);
        var current=mock(CurrentUserResponse.class);
        when(current.userId()).thenReturn(42L);
        when(users.currentUser("Bearer user-token")).thenReturn(current);
        var properties=new StudyProperties();properties.setEnabled(true);
        var authority=mock(StudyEvidenceAuthority.class);
        when(authority.current("task",42L,true)).thenReturn(7L);
        when(authority.current("task",42L,false)).thenReturn(7L);
        var transport=mock(StudyTransport.class);
        var json=new ObjectMapper();
        when(transport.command(anyMap())).thenReturn(json.createObjectNode());
        var controller=new StudyController(users,properties,authority,transport,json);
        controller.command("task","Bearer user-token",new StudyController.Command(
            "START_FEEDBACK","session","practice","key",null,0,"artifact",0,null,null,null,"attempt",null,null,null));
        var captured=org.mockito.ArgumentCaptor.forClass(Map.class);
        verify(transport).command(captured.capture());
        assertThat(captured.getValue()).containsEntry("owner_id",42L).containsEntry("revision",7L)
            .containsEntry("attempt_id","attempt").containsEntry("artifact_id","artifact");
        verify(authority).current("task",42L,true);
        clearInvocations(transport,authority);
        var note=new StudyController.Command("SAVE_FEEDBACK_NOTE","session","feedback-run","note-key",null,0,
            null,null,null,0,null,null,"feedback","I dispute this suggestion","disputed");
        controller.command("task","Bearer user-token",note);
        verify(transport).command(captured.capture());
        assertThat(captured.getValue()).containsEntry("feedback_id","feedback")
            .containsEntry("note_text","I dispute this suggestion").containsEntry("disposition","disputed");
        verify(authority,never()).current("task",42L,true);
        verify(authority,times(2)).current("task",42L,false);
        when(authority.current("task",42L,false)).thenReturn(7L,8L);
        assertThatThrownBy(()->controller.command("task","Bearer user-token",note))
            .isInstanceOf(com.example.courselingo.common.exception.BusinessException.class);
    }

    @Test void attemptsForwardRealTextWithServerScopeAndRejectBlankOrUnscopedWrites() {
        var users=mock(CurrentUserService.class);
        var current=mock(CurrentUserResponse.class);
        when(current.userId()).thenReturn(42L);
        when(users.currentUser("Bearer user-token")).thenReturn(current);
        var properties=new StudyProperties();properties.setEnabled(true);
        var authority=mock(StudyEvidenceAuthority.class);
        when(authority.current("task",42L,true)).thenReturn(7L);
        when(authority.current("task",42L,false)).thenReturn(7L);
        var transport=mock(StudyTransport.class);
        var json=new ObjectMapper();
        when(transport.command(anyMap())).thenReturn(json.createObjectNode());
        var controller=new StudyController(users,properties,authority,transport,json);
        var answer=new StudyController.Command("SAVE_ATTEMPT","session","run","key",null,0,"artifact",0,"My actual answer",2,null);
        controller.command("task","Bearer user-token",answer);
        var captured=org.mockito.ArgumentCaptor.forClass(Map.class);
        verify(transport).command(captured.capture());
        assertThat(captured.getValue()).containsEntry("owner_id",42L).containsEntry("revision",7L)
            .containsEntry("artifact_id","artifact").containsEntry("question_index",0)
            .containsEntry("answer_text","My actual answer").containsEntry("expected_version",2);
        verify(authority).current("task",42L,true);
        verify(authority).current("task",42L,false);
        clearInvocations(transport);
        for(var invalid:java.util.List.of(
            new StudyController.Command("SAVE_ATTEMPT","session","run","key",null,0,"artifact",0," \n",0,null),
            new StudyController.Command("SAVE_ATTEMPT","session",null,"key",null,0,"artifact",0,"answer",0,null),
            new StudyController.Command("SAVE_ATTEMPT","session","run","key",null,0,"artifact",2,"answer",0,null),
            new StudyController.Command("SAVE_ATTEMPT","session","run","key",null,0,"artifact",0,"answer",null,null),
            new StudyController.Command("ATTEMPT_HISTORY","session","run",null,null,0,"artifact",0,null,null,0))) {
            assertThatThrownBy(()->controller.command("task","Bearer user-token",invalid))
                .isInstanceOf(com.example.courselingo.common.exception.BusinessException.class);
        }
        verifyNoInteractions(transport);
        when(authority.current("task",42L,false)).thenReturn(8L);
        assertThatThrownBy(()->controller.command("task","Bearer user-token",answer))
            .isInstanceOf(com.example.courselingo.common.exception.BusinessException.class);
    }

    @Test void publicRequestsUseServerOwnedScopeAndRecheckAfterTransport() {
        var users=mock(CurrentUserService.class);
        var current=mock(CurrentUserResponse.class);
        when(current.userId()).thenReturn(42L);
        when(users.currentUser("Bearer user-token")).thenReturn(current);
        var properties=new StudyProperties();properties.setEnabled(true);
        var authority=mock(StudyEvidenceAuthority.class);
        when(authority.current("task",42L,true)).thenReturn(7L);
        when(authority.current("task",42L,false)).thenReturn(7L);
        var transport=mock(StudyTransport.class);
        var json=new ObjectMapper();
        when(transport.command(anyMap())).thenReturn(json.createObjectNode().put("owner_id",42).put("revision",7));
        var controller=new StudyController(users,properties,authority,transport,json);
        controller.command("task","Bearer user-token",new StudyController.Command("START","session",null,"key","Explain and practice",0));
        var captured=org.mockito.ArgumentCaptor.forClass(Map.class);
        verify(transport).command(captured.capture());
        assertThat(captured.getValue().get("owner_id")).isEqualTo(42L);
        assertThat(captured.getValue().get("course_id")).isEqualTo("task");
        assertThat(captured.getValue().get("revision")).isEqualTo(7L);
        verify(authority).current("task",42L,false);
    }
}
