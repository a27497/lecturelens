package com.example.courselingo.qa;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.evidence.CourseEvidence;
import com.example.courselingo.qa.domain.CourseQaRecord;
import com.example.courselingo.qa.dto.CourseQaEvidenceItem;
import com.example.courselingo.qa.mapper.CourseQaRecordMapper;
import com.example.courselingo.qa.service.CourseQaHistoryService;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

class CourseQaHistoryTest {
    CurrentUserService users = mock(CurrentUserService.class);
    CourseQaRecordMapper records = mock(CourseQaRecordMapper.class);
    JdbcTemplate jdbc = mock(JdbcTemplate.class);
    ObjectMapper json = new ObjectMapper();
    CourseQaHistoryService service = new CourseQaHistoryService(users, records, jdbc, json);
    static final String OWN = "SELECT content_revision FROM analysis_task WHERE id=? AND user_id=? AND deleted_at IS NULL";
    static final String SOURCE = "SELECT e.payload FROM course_evidence e JOIN analysis_task t ON t.id=e.task_id AND t.user_id=e.user_id\nAND t.content_revision=e.revision AND t.deleted_at IS NULL AND t.status='SUCCEEDED'\nWHERE e.task_id=? AND e.user_id=? AND e.revision=? AND e.evidence_id=?\n";
    void owner() {
        when(users.currentUser("auth")).thenReturn(new CurrentUserResponse(7L,"test@example.invalid","ACTIVE"));
        when(jdbc.queryForList(OWN, Long.class, "course", 7L)).thenReturn(List.of(2L));
    }
    CourseQaRecord row(long id, String sources) {
        var r = new CourseQaRecord(); r.setId(id); r.setQuestion("question"); r.setAnswer("answer");
        r.setStatus("SUCCEEDED"); r.setEvidenceJson(sources); r.setProvider("private-routing"); r.setExecutionSnapshotId("private-execution");
        return r;
    }
    @Test void ownershipAndDeletionAreCheckedBeforeHistoryAndAgainAfterReading() {
        owner(); when(jdbc.queryForList(OWN, Long.class,"course",7L)).thenReturn(List.of());
        assertThatThrownBy(() -> service.read("course","auth",null,20)).isInstanceOf(BusinessException.class);
        verifyNoInteractions(records);
        when(jdbc.queryForList(OWN, Long.class,"course",7L)).thenReturn(List.of(2L),List.of());
        when(records.selectHistory("course",7L,null,21)).thenReturn(List.of(row(1,"[]")));
        assertThatThrownBy(() -> service.read("course","auth",null,20)).isInstanceOf(BusinessException.class);
    }
    @Test void boundedCursorAndPublicDtoExcludeExecutionMetadata() throws Exception {
        owner(); when(records.selectHistory("course",7L,9L,2)).thenReturn(List.of(row(8,"[]"),row(7,"[]")));
        var page=service.read("course","auth",9L,1);
        assertThat(page.nextCursor()).isEqualTo("8"); assertThat(page.items()).hasSize(1);
        assertThat(json.writeValueAsString(page)).contains("question","answer").doesNotContain("private-routing","private-execution","usage","provider");
        assertThatThrownBy(() -> service.read("course","auth",null,51)).isInstanceOf(BusinessException.class);
        assertThatThrownBy(() -> service.read("course","auth",0L,20)).isInstanceOf(BusinessException.class);
    }
    @Test void oldRevisionMissingAndMalformedSourcesNeverBecomeTrusted() throws Exception {
        owner(); var source=new CourseQaEvidenceItem("SUBTITLE","1",10L,20L,"","saved text","",null,"old",1L);
        when(records.selectHistory("course",7L,null,21)).thenReturn(List.of(row(3,json.writeValueAsString(List.of(source))),row(2,"not-json")));
        var page=service.read("course","auth",null,20);
        assertThat(page.items().getFirst().evidence()).isEmpty(); assertThat(page.items().getFirst().sourceStatus()).isEqualTo("unavailable");
        verify(jdbc,never()).queryForList(SOURCE,String.class,"course",7L,2L,"old");
    }
    @Test void currentSourcesUseAuthoritativeTextAndRecheckRevision() throws Exception {
        owner(); var citation=new CourseQaEvidenceItem("SUBTITLE","forged",999L,999L,"","old text","",null,"valid",2L);
        var source=new CourseEvidence("valid","course",7L,2,"SUBTITLE","1",List.of(),10,20,"en","real text","real text",null,false,"v1","hash",true,"source",null,false);
        when(records.selectHistory("course",7L,null,21)).thenReturn(List.of(row(3,json.writeValueAsString(List.of(citation)))));
        when(jdbc.queryForList(SOURCE,String.class,"course",7L,2L,"valid")).thenReturn(List.of(json.writeValueAsString(source)));
        var item=service.read("course","auth",null,20).items().getFirst();
        assertThat(item.evidence().getFirst().snippet()).isEqualTo("real text"); assertThat(item.evidence().getFirst().startTimeMillis()).isEqualTo(10);
        when(jdbc.queryForList(OWN,Long.class,"course",7L)).thenReturn(List.of(2L),List.of(3L));
        assertThatThrownBy(() -> service.read("course","auth",null,20)).isInstanceOf(BusinessException.class);
    }
}
