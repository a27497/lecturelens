package com.example.courselingo.systemmodel;

import com.example.courselingo.ai.asr.*;
import com.example.courselingo.ai.llm.TranslationFailure;
import com.example.courselingo.subtitle.pipeline.*;
import com.example.courselingo.subtitle.service.SaveTranscriptionSegmentsCommand;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.transaction.support.TransactionTemplate;
import java.time.*;
import java.util.*;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

@EnabledIfEnvironmentVariable(named="SYSTEM_MODEL_TEST_JDBC_URL",matches=".+")
class TranscriptParagraphMySqlTest {
    @Test void alignmentPublishesOnlyForItsExactSourceAndEveryMember() throws Exception {
        try(var db=new SystemModelMySqlFixture()) {
            long user=db.user();String task=db.task(user);db.jdbc.update("UPDATE analysis_task SET status='RUNNING' WHERE id=?",task);
            var settings=new PipelineTranslationProperties();
            var policy=settings.freezeWithSilence(Duration.ofSeconds(120),Duration.ofMinutes(15),1,1000,16000,1,2,4*1024*1024);
            var policies=mock(PipelinePolicyService.class);
            when(policies.find(task,user)).thenReturn(Optional.of(new PipelinePolicyService.Frozen(policy,"test",Instant.now().plusSeconds(1800),new SystemModelExecutionRef("s",0,task,user))));
            var service=new TranscriptParagraphService(db.jdbc,policies);
            var atoms=List.of(new TranscribedSegment(0,120,10000,"First fact",TranscriptTimingSource.ASR,null),
                new TranscribedSegment(1,10500,20001,"Second fact",TranscriptTimingSource.ASR,null));
            for(var atom:atoms) db.jdbc.update("""
                INSERT INTO subtitle_segment(task_id,user_id,segment_index,start_millis,end_millis,language,text,timing_source)
                VALUES(?,?,?,?,?,'en',?,'ASR')
                """,task,user,atom.index(),atom.startMillis(),atom.endMillis(),atom.text());
            var result=new SpeechToTextResult("mock","en","First fact Second fact",atoms,Duration.ZERO,20001,
                Map.of("segmentationMode","SILENCE","silencePlanHash","a".repeat(64),"asrPhysicalAttempts",2,"silenceClipCount",2,"detectedSilenceMillis",500));
            var transaction=new TransactionTemplate(db.transactions);
            transaction.executeWithoutResult(s->service.replace(new SaveTranscriptionSegmentsCommand(task,user,result)));
            assertThat(service.aligned(task,user,"zh-CN")).isEmpty();
            for(var atom:atoms) db.jdbc.update("""
                INSERT INTO subtitle_translation_segment(task_id,user_id,segment_index,start_millis,end_millis,source_language,target_language,translated_text)
                VALUES(?,?,?,?,?,'en','zh-CN',?)
                """,task,user,atom.index(),atom.startMillis(),atom.endMillis(),"中文译文"+atom.index());
            // Existing translations alone are insufficient until the exact source is atomically published.
            assertThat(service.aligned(task,user,"zh-CN")).isEmpty();
            transaction.executeWithoutResult(s->service.publish(task,user,"zh-CN",TranscriptParagraphService.fingerprint(atoms)));
            var aligned=service.aligned(task,user,"zh-CN");
            assertThat(aligned).singleElement().satisfies(p->{assertThat(p.sourceSegmentIndexes()).containsExactly(0,1);
                assertThat(p.startSeconds()).isZero();assertThat(p.endSeconds()).isEqualTo(21);assertThat(p.startMillis()).isEqualTo(120);
                assertThat(p.sourceText()).isEqualTo("First fact\nSecond fact");assertThat(p.translatedText()).isEqualTo("中文译文0\n中文译文1");
                assertThat(p.timingSources()).containsExactly("ASR");});
            assertThat(service.aligned(task,user+1,"zh-CN")).isEmpty();
            assertThat(service.aligned(task,user,"ja")).isEmpty();
            assertThatThrownBy(()->transaction.executeWithoutResult(s->service.publish(task,user,"zh-CN","b".repeat(64))))
                .isInstanceOf(TranslationFailure.class);
            db.jdbc.update("UPDATE subtitle_segment SET text='different source' WHERE task_id=? AND segment_index=0",task);
            assertThatThrownBy(()->service.aligned(task,user,"zh-CN")).isInstanceOf(TranslationFailure.class);
            db.jdbc.update("UPDATE subtitle_segment SET text='First fact' WHERE task_id=? AND segment_index=0",task);
            transaction.executeWithoutResult(s->service.replace(new SaveTranscriptionSegmentsCommand(task,user,result)));
            assertThat(service.aligned(task,user,"zh-CN")).isEmpty();
            transaction.executeWithoutResult(s->service.publish(task,user,"zh-CN",TranscriptParagraphService.fingerprint(atoms)));
            db.jdbc.update("DELETE FROM subtitle_segment WHERE task_id=? AND segment_index=0",task);
            assertThatThrownBy(()->service.aligned(task,user,"zh-CN")).isInstanceOf(TranslationFailure.class);
            db.jdbc.update("DELETE FROM analysis_task WHERE id=?",task);
            for(String table:List.of("transcript_paragraph","transcript_timing_plan","transcript_alignment_publication","transcript_paragraph_member"))
                assertThat(db.jdbc.queryForObject("SELECT COUNT(*) FROM "+table,Integer.class)).isZero();
        }
    }
    @Test void v2CannotPersistProportionalOrUnlabelledTimingAsPrecise() throws Exception {
        try(var db=new SystemModelMySqlFixture()) {
            long user=db.user();String task=db.task(user);
            var policies=mock(PipelinePolicyService.class);var settings=new PipelineTranslationProperties();
            var policy=settings.freezeWithSilence(Duration.ofSeconds(120),Duration.ofMinutes(15),1,1000,16000,1,2,4*1024*1024);
            when(policies.find(task,user)).thenReturn(Optional.of(new PipelinePolicyService.Frozen(policy,"test",Instant.now().plusSeconds(1800),new SystemModelExecutionRef("s",0,task,user))));
            var service=new TranscriptParagraphService(db.jdbc,policies);
            var result=new SpeechToTextResult("mock","en","Estimated",List.of(new TranscribedSegment(0,0,1000,"Estimated")),Duration.ZERO,1000,Map.of());
            assertThatThrownBy(()->service.replace(new SaveTranscriptionSegmentsCommand(task,user,result))).isInstanceOf(TranslationFailure.class);
            assertThat(db.jdbc.queryForObject("SELECT COUNT(*) FROM transcript_paragraph",Integer.class)).isZero();
        }
    }
}
