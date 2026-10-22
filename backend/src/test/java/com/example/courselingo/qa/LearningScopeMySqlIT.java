package com.example.courselingo.qa;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.evidence.*;
import com.example.courselingo.qa.service.*;
import com.example.courselingo.study.*;
import com.example.courselingo.task.service.GenerationFence;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;

/** Explicit integration target; never silently skips a missing database. Use a disposable test database. */
class LearningScopeMySqlIT {
    @Test void canonicalScopeUsesRealMigrationsOwnershipRevisionAndDeletion() {
        String url=System.getenv("SYSTEM_MODEL_TEST_JDBC_URL");
        assertThat(url).as("Dedicated loopback scope database required").matches("jdbc:mysql://(127\\.0\\.0\\.1|localhost):[0-9]+/lecturelens_pr2_test(?:\\?.*)?");
        var ds=new DriverManagerDataSource(url,System.getenv("SYSTEM_MODEL_TEST_MYSQL_USER"),System.getenv("SYSTEM_MODEL_TEST_MYSQL_PASSWORD"));
        assertThat(new JdbcTemplate(ds).queryForObject("SELECT DEFAULT_COLLATION_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=DATABASE()",String.class))
            .as("Match the existing compose.yaml database collation before migrations").isEqualTo("utf8mb4_unicode_ci");
        Flyway.configure().dataSource(ds).load().migrate();
        var jdbc=new JdbcTemplate(ds);var manager=new DataSourceTransactionManager(ds);var json=new ObjectMapper();
        var fence=new GenerationFence(jdbc,manager);
        var sources=new CourseEvidenceService(jdbc,json,fence,manager);
        var dense=mock(DenseEvidenceClient.class);var indexes=mock(EvidenceIndexSynchronizer.class);
        var authority=new StudyEvidenceAuthority(jdbc,sources,indexes,dense);
        String task="scope-"+UUID.randomUUID(), other="scope-"+UUID.randomUUID(), upload="scope-"+UUID.randomUUID();
        String email="scope-"+UUID.randomUUID()+"@test.invalid";
        jdbc.update("INSERT INTO user_account(email,password_hash,status) VALUES (?,?,'ACTIVE')",email,"test-only");
        long owner=jdbc.queryForObject("SELECT id FROM user_account WHERE email=?",Long.class,email);
        jdbc.update("INSERT INTO upload_session(id,user_id,filename,ext,total_chunks,chunk_size_bytes,size_bytes,file_md5,status,storage_type,object_key) VALUES (?,?,'scope.mp4','mp4',1,1,1,?,'COMPLETED','LOCAL',?)",upload,owner,"a".repeat(32),upload);
        for(String id:List.of(task,other)) jdbc.update("INSERT INTO analysis_task(id,user_id,upload_id,target_language,status,content_revision) VALUES (?,?,?,'zh-CN','SUCCEEDED',1)",id,owner,upload);
        jdbc.update("INSERT INTO subtitle_segment(task_id,user_id,segment_index,start_millis,end_millis,language,text) VALUES (?,?,0,0,1000,'en','An algorithm needs a stopping condition.'),(?,?,1,1000,2000,'en','Outside selection: unrelated sorting method.')",task,owner,task,owner);
        jdbc.update("INSERT INTO subtitle_segment(task_id,user_id,segment_index,start_millis,end_millis,language,text) VALUES (?,?,0,0,1000,'en','A different course.')",other,owner);
        try {
            var all=sources.current(task,owner);assertThat(all).hasSize(2);
            String first=all.getFirst().evidenceId(), second=all.getLast().evidenceId();
            var scope=new LearningScope(1,"segments","strict",1,List.of(first));
            when(indexes.status(task,owner)).thenReturn(new EvidenceIndexSynchronizer.IndexStatus("READY",1,1L,"test",0,null,null));
            when(dense.retrieve(eq(task),eq(owner),anyList(),anyString(),isNull(),isNull(),eq(4))).thenAnswer(call->{
                List<CourseEvidence> pool=call.getArgument(2);assertThat(pool).extracting(CourseEvidence::evidenceId).containsExactly(first);return pool;
            });
            assertThat(authority.validateScope(task,owner,1,scope)).isEqualTo(scope);
            assertThat(authority.execute(request(owner,task,scope,"SEARCH",null,null)).toString()).contains(first).doesNotContain(second);
            assertThat(authority.execute(request(owner,task,scope,"WINDOW",null,first)).toString()).doesNotContain(second);
            assertThatThrownBy(()->authority.execute(request(owner,task,scope,"READ",List.of(second),null))).isInstanceOf(BusinessException.class);
            assertThatThrownBy(()->authority.execute(request(owner+1,task,scope,"CHECK",null,null))).isInstanceOf(BusinessException.class);
            String foreign=sources.current(other,owner).getFirst().evidenceId();
            assertThatThrownBy(()->authority.validateScope(task,owner,1,new LearningScope(1,"segments","strict",1,List.of(foreign)))).isInstanceOf(BusinessException.class);
            // The same retriever used by ordinary QA must constrain candidates before ranking, too.
            var qa=new CourseQaEvidenceRetriever(mock(com.example.courselingo.fusion.mapper.VideoSegmentMapper.class),mock(com.example.courselingo.subtitle.mapper.SubtitleSegmentMapper.class),mock(com.example.courselingo.subtitle.mapper.SubtitleTranslationSegmentMapper.class),mock(com.example.courselingo.vision.ocr.mapper.VideoKeyframeOcrMapper.class));
            qa.configureEvidence(sources);
            assertThat(qa.retrieve(task,owner,"en","stopping condition",scope)).extracting(e->e.evidenceId()).containsExactly(first);
            assertThat(qa.retrieve(task,owner,"en","unrelated sorting",scope)).isEmpty();
            assertThat(qa.retrieve(task,owner,"en","unrelated sorting",new LearningScope(1,"segments","course",1,List.of(first)))).extracting(e->e.evidenceId()).contains(second);
            new TransactionTemplate(manager).executeWithoutResult(s->{fence.sourceChanging(task,owner);jdbc.update("UPDATE subtitle_segment SET text='Revised source' WHERE task_id=?",task);});
            assertThatThrownBy(()->authority.execute(request(owner,task,scope,"CHECK",null,null))).isInstanceOf(BusinessException.class);
            jdbc.update("UPDATE analysis_task SET deleted_at=CURRENT_TIMESTAMP WHERE id=?",task);
            assertThatThrownBy(()->sources.current(task,owner)).isInstanceOf(BusinessException.class);
        } finally {
            // Only this fixture's rows, in this explicitly supplied test database.
            jdbc.update("DELETE FROM analysis_task WHERE id IN (?,?)",task,other);
            jdbc.update("DELETE FROM upload_session WHERE id=?",upload);
            jdbc.update("DELETE FROM user_account WHERE id=?",owner);
        }
    }
    static StudyEvidenceAuthority.Request request(long owner,String task,LearningScope scope,String action,List<String> ids,String anchor) {
        return new StudyEvidenceAuthority.Request(owner,task,1,action,"stopping condition",null,null,ids,anchor,scope,false);
    }
}
