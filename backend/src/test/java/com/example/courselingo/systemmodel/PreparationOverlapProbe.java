package com.example.courselingo.systemmodel;

import com.example.courselingo.ai.llm.*;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.task.runner.*;
import java.util.*;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import static org.assertj.core.api.Assertions.*;

/** Explicit feature-acceptance probe, run with -Dtest=PreparationOverlapProbe; not a qualified C/E implementation. */
@EnabledIfEnvironmentVariable(named="SYSTEM_MODEL_TEST_JDBC_URL",matches=".+")
class PreparationOverlapProbe {
    @Test void completedTranslationShouldSurviveAppendingANewClosedSourceBatch() throws Exception {
        try(var f=new PipelineCheckpointFixture(1)) {
            var provider=PipelineCheckpointFixture.provider(r->PipelineCheckpointFixture.success());
            f.coordinator(f.first,provider,f.session(f.first)).run(List.of(f.source));
            var previous=f.db.jdbc.queryForMap("SELECT result_hash,attempt_count FROM translation_batch WHERE task_id=? AND batch_no=1",f.task);
            var appended=new SubtitleSegment();appended.setTaskId(f.task);appended.setUserId(f.user);appended.setSegmentIndex(1);
            appended.setStartMillis(10000L);appended.setEndMillis(20000L);appended.setText("next closed source batch");appended.setLanguage("en");
            f.db.jdbc.update("INSERT INTO subtitle_segment(task_id,user_id,segment_index,start_millis,end_millis,text,language) VALUES(?,?,1,10000,20000,?,'en')",f.task,f.user,appended.getText());
            var complete=new ArrayList<>(f.source);complete.add(appended);
            var session=f.batches.open(f.frozen,f.first.requestId(),complete,"zh-CN","frozen-deepseek","mock");
            var outcome=f.coordinator(f.first,provider,session).run(complete.stream().map(List::of).toList());
            assertThat(outcome.translations()).hasSize(2);
            assertThat(f.db.jdbc.queryForMap("SELECT result_hash,attempt_count FROM translation_batch WHERE task_id=? AND batch_no=1",f.task)).isEqualTo(previous);
        }
    }

    @Test void materialsShouldStartWhileTranslationIsStillRunning() {
        var materialsStarted=new CountDownLatch(1);
        var steps=PipelineAnalysisTaskStepName.ordered().stream().map(name->new PipelineAnalysisTaskStep() {
            public PipelineAnalysisTaskStepName name(){return name;}
            public void execute(PipelineAnalysisTaskStepContext context) {
                if(name==PipelineAnalysisTaskStepName.GENERATE_LEARNING_PACKAGE)materialsStarted.countDown();
                if(name==PipelineAnalysisTaskStepName.TRANSLATE_SUBTITLES) {
                    try {assertThat(materialsStarted.await(250,TimeUnit.MILLISECONDS)).as("materials must overlap translation").isTrue();}
                    catch(InterruptedException interrupted){Thread.currentThread().interrupt();throw new AssertionError(interrupted);}
                }
            }
        }).map(PipelineAnalysisTaskStep.class::cast).toList();
        assertThat(new PipelineAnalysisTaskWorkExecutor(steps).execute(
            new AnalysisTaskExecutionContext("probe-task","probe-upload",7L,"en","zh-CN","probe-request")).success()).isTrue();
    }
}
