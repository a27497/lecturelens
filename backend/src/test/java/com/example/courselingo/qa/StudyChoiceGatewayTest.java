package com.example.courselingo.qa;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.study.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import org.junit.jupiter.api.Test;

class StudyChoiceGatewayTest {
    @Test void choiceFieldsUseAuthenticatedScopeWithoutJavaGrading() throws Exception {
        var users=mock(CurrentUserService.class);
        when(users.currentUser(any())).thenReturn(new CurrentUserResponse(42L,"preview@test.invalid","ACTIVE"));
        var properties=new StudyProperties();properties.setEnabled(true);
        var authority=mock(StudyEvidenceAuthority.class);
        when(authority.current(eq("course"),eq(42L),anyBoolean())).thenReturn(7L);
        var transport=mock(StudyTransport.class);var json=new ObjectMapper();
        when(transport.command(anyMap())).thenReturn(json.readTree("{\"attempt\":{\"choice_result\":{\"is_correct\":false,\"correct_option_id\":\"B\"}}}"));
        var controller=new StudyController(users,properties,authority,transport,json);
        String scope="\"session_id\":\"session\",\"run_id\":\"run\",\"artifact_id\":\"artifact\",\"question_index\":0,\"request_key\":\"key\",\"expected_version\":0";
        var command=json.readValue("{\"operation\":\"SAVE_ATTEMPT\",\"selected_option_id\":\"A\","+scope+"}",StudyController.Command.class);
        controller.command("course","Bearer preview",command);
        var captured=org.mockito.ArgumentCaptor.forClass(Map.class);verify(transport).command(captured.capture());
        assertThat(captured.getValue()).containsEntry("owner_id",42L).containsEntry("revision",7L).containsEntry("selected_option_id","A").doesNotContainKey("answer_text").doesNotContainKey("correct_option_id");
        verify(authority).current("course",42L,true);verify(authority).current("course",42L,false);
        clearInvocations(transport,authority);
        var start=json.readValue("{\"operation\":\"START\",\"session_id\":\"session\",\"goal\":\"Read course\",\"request_key\":\"start\",\"practice_format\":\"choice\"}",StudyController.Command.class);
        controller.command("course","Bearer preview",start);
        verify(transport).command(captured.capture());assertThat(captured.getValue()).containsEntry("practice_format","choice");
    }

    @Test void emptyMixedAndMisplacedChoiceFieldsNeverReachPython() throws Exception {
        var users=mock(CurrentUserService.class);
        when(users.currentUser(any())).thenReturn(new CurrentUserResponse(42L,"preview@test.invalid","ACTIVE"));
        var properties=new StudyProperties();properties.setEnabled(true);
        var authority=mock(StudyEvidenceAuthority.class);var transport=mock(StudyTransport.class);var json=new ObjectMapper();
        var controller=new StudyController(users,properties,authority,transport,json);
        String scope="\"session_id\":\"session\",\"run_id\":\"run\",\"artifact_id\":\"artifact\",\"question_index\":0,\"request_key\":\"key\",\"expected_version\":0";
        for(var fields:java.util.List.of("",",\"selected_option_id\":\"\"",",\"selected_option_id\":\"A\",\"answer_text\":\"text\"")) {
            var command=json.readValue("{\"operation\":\"SAVE_ATTEMPT\","+scope+fields+"}",StudyController.Command.class);
            assertThatThrownBy(()->controller.command("course","Bearer preview",command)).isInstanceOf(com.example.courselingo.common.exception.BusinessException.class);
        }
        for(var body:java.util.List.of("{\"operation\":\"READ\",\"selected_option_id\":\"A\"}","{\"operation\":\"READ\",\"practice_format\":\"choice\"}","{\"operation\":\"START\",\"practice_format\":\"other\"}")) {
            var command=json.readValue(body,StudyController.Command.class);
            assertThatThrownBy(()->controller.command("course","Bearer preview",command)).isInstanceOf(com.example.courselingo.common.exception.BusinessException.class);
        }
        verifyNoInteractions(transport,authority);
    }
}
