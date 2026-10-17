package com.example.courselingo.systemmodel;

import com.example.courselingo.subtitle.pipeline.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import java.time.*;
import static org.assertj.core.api.Assertions.*;

@EnabledIfEnvironmentVariable(named="SYSTEM_MODEL_TEST_JDBC_URL",matches=".+")
class TranslationSchedulerMySqlTest {
    @Test void schedulerHistoryIsDurableOrderedOwnedAndResetsExplicitly() throws Exception {
        try(var db=new SystemModelMySqlFixture()) {
            long user=db.user();String task=db.task(user);db.jdbc.update("UPDATE analysis_task SET status='RUNNING' WHERE id=?",task);
            var settings=new PipelineTranslationProperties();settings.setCheckpointEnabled(false);
            var policy=settings.freezePipeline(Duration.ofSeconds(120),Duration.ofMinutes(15),1,1000,16000,1,2,4*1024*1024,3,java.util.List.of(0L));
            var frozen=new PipelinePolicyService.Frozen(policy,"a".repeat(64),Instant.now().plusSeconds(1800),new SystemModelExecutionRef("s",0,task,user));
            var store=new TranslationSchedulerEvents(db.jdbc,db.transactions);
            for(int run=0;run<2;run++) try(var c=new AdaptiveTranslationController(policy.aimd(),"mysql-events",store.observer(frozen))) {
                for(int i=0;i<3;i++)try(var permit=c.acquire(i+1,1,3000)){permit.succeeded();}
            }
            var rows=db.jdbc.queryForList("SELECT * FROM translation_scheduler_event WHERE task_id=? ORDER BY event_seq",task);
            assertThat(rows).hasSize(14);
            for(int i=0;i<rows.size();i++) {assertThat(((Number)rows.get(i).get("event_seq")).intValue()).isEqualTo(i+1);assertThat(rows.get(i).get("user_id")).isEqualTo(user);}
            assertThat(rows.stream().filter(r->r.get("reason").equals("RECOVERY_RESET"))).hasSize(1);
            assertThat(((Number)db.jdbc.queryForObject("SELECT window_size FROM translation_scheduler_state WHERE task_id=?",Integer.class,task)).intValue()).isEqualTo(2);
            var other=new PipelinePolicyService.Frozen(policy,frozen.hash(),frozen.deadline(),new SystemModelExecutionRef("s",0,task,user+1));
            assertThatThrownBy(()->new AdaptiveTranslationController(policy.aimd(),"mysql-events",store.observer(other)))
                .isInstanceOf(com.example.courselingo.ai.llm.TranslationFailure.class);
            db.jdbc.update("DELETE FROM analysis_task WHERE id=?",task);
            assertThat(db.jdbc.queryForObject("SELECT COUNT(*) FROM translation_scheduler_event",Integer.class)).isZero();
            assertThat(db.jdbc.queryForObject("SELECT COUNT(*) FROM translation_scheduler_state",Integer.class)).isZero();
        }
    }
}
