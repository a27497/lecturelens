package com.example.courselingo.qa;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.example.courselingo.evidence.CourseEvidence;
import com.example.courselingo.study.StudyEvidenceAuthority;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import org.junit.jupiter.api.Test;

class TutorCompleteEvidenceTest {
    static CourseEvidence source(String id, String raw, boolean truncated) throws Exception {
        String hash=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(raw.getBytes(StandardCharsets.UTF_8)));
        return new CourseEvidence(id,"task",42L,1,"SUBTITLE",id,List.of(id),0,1000,"en",raw,
            raw.replaceAll("\\s+"," "),null,false,"evidence-v1",hash,true,"source_text",null,truncated);
    }
    static StudyEvidenceAuthority.Request request(String action,List<String> ids) {
        return new StudyEvidenceAuthority.Request(42L,"task",1,action,"loop",null,null,ids,null,null,null,"complete-v1");
    }
    @Test void completeReadPreservesCodeTailHashAndLegacyCompatibility() throws Exception {
        var lab=new StudyAuthorityTest();lab.setup();
        String raw="for value in names:\n    length += 1\nprint(length)\n"+"x".repeat(1300)+" SUFFIX_CONDITION";
        when(lab.evidence.current("task",42L)).thenReturn(List.of(source("e1",raw,false)));
        var result=lab.authority.execute(request("READ",List.of("e1")));
        assertThat(result).containsEntry("text_policy","complete-v1");
        var row=(Map<?,?>)((List<?>)result.get("evidence")).getFirst();
        assertThat(row.get("text")).isEqualTo(raw);assertThat(row.get("text_complete")).isEqualTo(true);
        assertThat(lab.authority.execute(lab.request("READ",List.of("e1"),null))).doesNotContainKey("text_policy");
    }
    @Test void negotiatedCheckIsRequiredBeforeSourceOrModelUse() {
        var lab=new StudyAuthorityTest();lab.setup();
        assertThat(lab.authority.execute(request("CHECK",null))).containsEntry("text_policy","complete-v1");
    }
    @Test void noCompletePrefixOnPerRowAggregateByteOrIngestionOverflow() throws Exception {
        for(var rows:List.of(List.of(source("e1","x".repeat(8001),false)),
                List.of(source("e1","x",true)),
                List.of(source("e1","x".repeat(8000),false),source("e2","x".repeat(8000),false),source("e3","x",false)),
                List.of(source("e1","中".repeat(8000),false),source("e2","中".repeat(4000),false)))) {
            var lab=new StudyAuthorityTest();lab.setup();when(lab.evidence.current("task",42L)).thenReturn(rows);
            assertThatThrownBy(()->lab.authority.execute(request("READ",rows.stream().map(CourseEvidence::evidenceId).toList())))
                .hasMessage("STUDY_EVIDENCE_CAPACITY");
        }
    }
    @Test void exactCapacityAndOwnerRevisionChecksRemainEnforced() throws Exception {
        var lab=new StudyAuthorityTest();lab.setup();
        when(lab.evidence.current("task",42L)).thenReturn(List.of(source("e1","x".repeat(8000),false),source("e2","x".repeat(8000),false)));
        assertThat((List<?>)lab.authority.execute(request("READ",List.of("e1","e2"))).get("evidence")).hasSize(2);
        lab.jdbc.update("UPDATE analysis_task SET content_revision=2");
        assertThatThrownBy(()->lab.authority.execute(request("READ",List.of("e1")))).hasMessageNotContaining("xxxxxxxx");
        assertThatThrownBy(()->lab.authority.execute(new StudyEvidenceAuthority.Request(99L,"task",1,"READ",null,null,null,List.of("e1"),null,null,null,"complete-v1"))).isInstanceOf(RuntimeException.class);
    }
}
