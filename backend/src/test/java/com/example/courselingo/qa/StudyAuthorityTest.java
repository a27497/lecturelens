package com.example.courselingo.qa;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.evidence.*;
import com.example.courselingo.qa.service.*;
import com.example.courselingo.study.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

class StudyAuthorityTest {
    JdbcTemplate jdbc;
    CourseEvidenceService evidence;
    EvidenceIndexSynchronizer indexes;
    DenseEvidenceClient dense;
    StudyEvidenceAuthority authority;
    @BeforeEach void setup() {
        jdbc=new JdbcTemplate(new DriverManagerDataSource("jdbc:h2:mem:"+UUID.randomUUID()+";DB_CLOSE_DELAY=-1", "sa", ""));
        jdbc.execute("CREATE TABLE analysis_task(id VARCHAR(64),user_id BIGINT,content_revision BIGINT,status VARCHAR(32),deleted_at TIMESTAMP)");
        jdbc.update("INSERT INTO analysis_task VALUES ('task',42,1,'SUCCEEDED',NULL)");
        evidence=mock(CourseEvidenceService.class); indexes=mock(EvidenceIndexSynchronizer.class); dense=mock(DenseEvidenceClient.class);
        when(indexes.status("task",42L)).thenReturn(new EvidenceIndexSynchronizer.IndexStatus("READY",1,1L,"v1",0,null,null));
        when(evidence.current("task",42L)).thenReturn(List.of(item("e1",0),item("e2",1000),item("e3",2000)));
        authority=new StudyEvidenceAuthority(jdbc,evidence,indexes,dense);
    }
    CourseEvidence item(String id,long start) {
        return item(id,start,"SUBTITLE");
    }
    CourseEvidence item(String id,long start,String type) {
        return new CourseEvidence(id,"task",42L,1,type,id,List.of(id),start,start+1000,"en","source","source",null,false,"v1",id,true,"source",null,false);
    }
    StudyEvidenceAuthority.Request request(String action,List<String> ids,String id) {
        return new StudyEvidenceAuthority.Request(42L,"task",1,action,"stopping condition",null,null,ids,id);
    }
    @Test void rejectsCrossOwnerDeletedAndStaleBeforeReadingSource() {
        assertThatThrownBy(()->authority.current("task",99L,false)).isInstanceOf(BusinessException.class);
        jdbc.update("UPDATE analysis_task SET content_revision=2");
        assertThatThrownBy(()->authority.execute(request("READ",List.of("e1"),null))).isInstanceOf(BusinessException.class);
        jdbc.update("UPDATE analysis_task SET deleted_at=CURRENT_TIMESTAMP");
        assertThatThrownBy(()->authority.current("task",42L,false)).isInstanceOf(BusinessException.class);
        verifyNoInteractions(evidence);
    }
    @Test void readAndNeighborToolsAreBoundedAndRejectUnknownReferences() {
        var result=authority.execute(request("WINDOW",null,"e2"));
        assertThat((List<?>)result.get("evidence")).hasSize(3);
        assertThatThrownBy(()->authority.execute(request("READ",List.of("foreign-id"),null))).isInstanceOf(BusinessException.class);
        assertThatThrownBy(()->authority.execute(request("HTTP",List.of(),null))).isInstanceOf(BusinessException.class);
    }
    @Test void sourceChangeDuringDenseCallPreventsReturningContext() {
        when(dense.retrieve(eq("task"),eq(42L),anyList(),anyString(),isNull(),isNull(),eq(4))).thenAnswer(call->{
            jdbc.update("UPDATE analysis_task SET content_revision=2");
            return List.of(item("e1",0));
        });
        assertThatThrownBy(()->authority.execute(request("SEARCH",null,null))).isInstanceOf(BusinessException.class);
    }
    @SuppressWarnings("unchecked")
    List<String> ids(Map<String,Object> response) {
        return ((List<Map<String,Object>>)response.get("evidence")).stream().map(e->(String)e.get("evidence_id")).toList();
    }
    @Test void searchUsesOriginalSpeechAndCompletesAdjacentContextWithoutDuplicateTranslation() {
        var original=item("e2",1000); var translation=item("t2",1000,"SUBTITLE_TRANSLATION");
        when(evidence.current("task",42L)).thenReturn(List.of(item("e3",2000),translation,item("e1",0),original));
        when(dense.retrieve(eq("task"),eq(42L),anyList(),anyString(),isNull(),isNull(),eq(4)))
            .thenReturn(List.of(translation,original));
        assertThat(ids(authority.execute(request("SEARCH",null,null)))).containsExactly("e2","e3","e1");
    }
    @Test void windowUsesSameModalityInTimeOrderAndDoesNotWrapToTranslation() {
        when(evidence.current("task",42L)).thenReturn(List.of(item("e3",2000),item("e1",0),item("e2",1000),item("t1",0,"SUBTITLE_TRANSLATION")));
        assertThat(ids(authority.execute(request("WINDOW",null,"e3")))).containsExactly("e2","e3");
    }
    @Test void searchContextKeepsVisualSourcesAndRequestedTimeBoundary() {
        var visual=item("ocr",1000,"OCR"); var first=item("e1",0);
        when(evidence.current("task",42L)).thenReturn(List.of(first,item("e2",1000),item("e3",2000),visual));
        when(dense.retrieve(eq("task"),eq(42L),anyList(),anyString(),eq(1000L),eq(1999L),eq(4)))
            .thenReturn(List.of(item("e2",1000),visual));
        var bounded=new StudyEvidenceAuthority.Request(42L,"task",1,"SEARCH","topic",1000L,1999L,null,null);
        assertThat(ids(authority.execute(bounded))).containsExactly("e2","ocr","e1");
    }
    @Test void unreadyIndexBlocksSourceButAllowsCancellationAuthorityCheck() {
        when(indexes.status("task",42L)).thenReturn(new EvidenceIndexSynchronizer.IndexStatus("FAILED",1,null,null,1,null,null));
        assertThat(authority.execute(request("CHECK",null,null)).get("revision")).isEqualTo(1L);
        assertThatThrownBy(()->authority.execute(request("SEARCH",null,null))).isInstanceOf(BusinessException.class);
    }
    @Test void serviceSignatureBindsPathTimeAndBody() throws Exception {
        var config=new DenseRetrievalProperties();config.setServiceSecret("test-study-context-secret-32-bytes-minimum");
        try(var client=new StudyTransport(config,new ObjectMapper())) {
            String path="/internal/v1/study/evidence", timestamp=Long.toString(Instant.now().getEpochSecond());
            byte[] body="{\"owner_id\":42}".getBytes(StandardCharsets.UTF_8);
            String signature=client.signature(path,timestamp,body);
            client.verify(path,timestamp,signature,body);
            assertThatThrownBy(()->client.verify("/internal/v1/retrieve",timestamp,signature,body)).isInstanceOf(BusinessException.class);
            assertThatThrownBy(()->client.verify(path,timestamp,signature,"{}".getBytes(StandardCharsets.UTF_8))).isInstanceOf(BusinessException.class);
            assertThatThrownBy(()->client.verify(path,"0",signature,body)).isInstanceOf(BusinessException.class);
        }
    }
}
