package com.example.courselingo.systemmodel;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.evidence.CourseEvidence;
import com.example.courselingo.qa.dto.CourseQaEvidenceItem;
import com.example.courselingo.qa.mapper.CourseQaRecordMapper;
import com.example.courselingo.qa.service.CourseQaHistoryService;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionTemplate;

@EnabledIfEnvironmentVariable(named = "SYSTEM_MODEL_TEST_JDBC_URL", matches = ".+")
class CourseQaHistoryMySqlTest {
    @Test void boundedPageUsesOneEvidenceReadAndRetainsAuthorityCursorUtcAndDeletionFences() throws Exception {
        try (var db = new SystemModelMySqlFixture()) {
            long owner = db.user(), other = db.user(); String task = db.task(owner);
            db.jdbc.update("UPDATE analysis_task SET content_revision=2 WHERE id=?", task);
            var config = new com.baomidou.mybatisplus.core.MybatisConfiguration();
            config.addMapper(CourseQaRecordMapper.class);
            var factory = new com.baomidou.mybatisplus.extension.spring.MybatisSqlSessionFactoryBean();
            factory.setDataSource(db.dataSource); factory.setConfiguration(config);
            var records = new org.mybatis.spring.SqlSessionTemplate(factory.getObject()).getMapper(CourseQaRecordMapper.class);
            var users = mock(CurrentUserService.class);
            when(users.currentUser("own")).thenReturn(new CurrentUserResponse(owner,"own@example.invalid","ACTIVE"));
            when(users.currentUser("other")).thenReturn(new CurrentUserResponse(other,"other@example.invalid","ACTIVE"));
            var json = new ObjectMapper().findAndRegisterModules().disable(com.fasterxml.jackson.databind.SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
            var citations = new ArrayList<CourseQaEvidenceItem>();
            for (int index=0;index<8;index++) {
                String id = "valid-"+index;
                var source = new CourseEvidence(id,task,owner,2,"SUBTITLE",String.valueOf(index),List.of(),10,20,"en","authoritative text","authoritative text",null,false,"v1","hash",true,"source",null,false);
                db.jdbc.update("INSERT INTO course_evidence(evidence_id,task_id,user_id,revision,source_type,source_id,start_ms,end_ms,payload) VALUES (?,?,?,?,'SUBTITLE',?,10,20,?)", id,task,owner,2,String.valueOf(index),json.writeValueAsString(source));
                citations.add(new CourseQaEvidenceItem("SUBTITLE","forged",999L,999L,"","saved text","",null,id,2L));
            }
            var saved = json.writeValueAsString(citations);
            for (int i=0;i<51;i++) db.jdbc.update("INSERT INTO course_qa_record(task_id,user_id,question,answer,evidence_json,status,created_at) VALUES (?,?,'synthetic question','saved answer',?,'SUCCEEDED','2026-10-26 06:00:00')",task,owner,saved);
            var counted = spy(new JdbcTemplate(db.dataSource));
            var service = new CourseQaHistoryService(users, records, counted, json);
            var tx = new TransactionTemplate(db.transactions);
            tx.setIsolationLevel(org.springframework.transaction.TransactionDefinition.ISOLATION_READ_COMMITTED);
            var page = tx.execute(status -> service.read(task,"own",null,50));
            assertThat(page.items()).hasSize(50); assertThat(page.nextCursor()).isNotNull();
            assertThat(page.items()).allSatisfy(item -> {
                assertThat(item.evidence()).hasSize(8); assertThat(item.evidence()).allSatisfy(e -> assertThat(e.snippet()).isEqualTo("authoritative text"));
                assertThat(item.createdAt()).isEqualTo(java.time.Instant.parse("2026-10-26T06:00:00Z"));
            });
            long evidenceReads = mockingDetails(counted).getInvocations().stream().filter(i -> i.getMethod().getName().equals("queryForList") && i.getArgument(0).toString().contains("FROM course_evidence")).count();
            assertThat(evidenceReads).isEqualTo(1);
            assertThat(json.writeValueAsString(page)).contains("2026-10-26T06:00:00Z");
            var next = service.read(task,"own",Long.valueOf(page.nextCursor()),50);
            assertThat(next.items()).hasSize(1); assertThat(next.nextCursor()).isNull();
            assertThat(next.items().getFirst().recordId()).isNotIn(page.items().stream().map(i -> i.recordId()).toList());
            assertThatThrownBy(() -> service.read(task,"other",null,50)).isInstanceOf(BusinessException.class);
            db.jdbc.update("UPDATE analysis_task SET content_revision=3 WHERE id=?",task);
            assertThat(service.read(task,"own",null,50).items()).allSatisfy(i -> { assertThat(i.evidence()).isEmpty(); assertThat(i.sourceStatus()).isEqualTo("unavailable"); });
            db.jdbc.update("UPDATE analysis_task SET deleted_at=UTC_TIMESTAMP() WHERE id=?",task);
            assertThatThrownBy(() -> service.read(task,"own",null,50)).isInstanceOf(BusinessException.class);
        }
    }
}
