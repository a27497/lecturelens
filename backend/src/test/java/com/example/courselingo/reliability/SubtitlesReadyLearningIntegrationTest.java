package com.example.courselingo.reliability;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.courselingo.evidence.CourseEvidence;
import com.example.courselingo.evidence.CourseEvidenceService;
import com.example.courselingo.evidence.EvidenceIndexSynchronizer;
import com.example.courselingo.evidence.LearnableEvidencePublisher;
import com.example.courselingo.task.service.GenerationFence;
import com.example.courselingo.task.service.LearnableSourcePublication;
import com.example.courselingo.task.service.LearningAvailability;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.support.StaticListableBeanFactory;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import org.springframework.transaction.support.TransactionTemplate;

/** Step 3 on real transactions: late background sources must not invalidate open study sessions. */
class SubtitlesReadyLearningIntegrationTest {
    JdbcTemplate jdbc;
    TransactionTemplate tx;
    GenerationFence fence;
    CourseEvidenceService evidence;
    LearningAvailability learning;
    EvidenceIndexSynchronizer indexes;
    com.example.courselingo.qa.service.DenseEvidenceClient dense;

    @BeforeEach
    void setup() throws Exception {
        var ds = new DriverManagerDataSource("jdbc:h2:mem:" + UUID.randomUUID()
            + ";MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1", "sa", "");
        jdbc = new JdbcTemplate(ds);
        var manager = new DataSourceTransactionManager(ds);
        tx = new TransactionTemplate(manager);
        // Pre-V33 shape: the migration itself adds learning_ready_at and task_stage_outcome.
        jdbc.execute("CREATE TABLE analysis_task(id VARCHAR(64) PRIMARY KEY,user_id BIGINT,status VARCHAR(32),"
            + "deleted_at TIMESTAMP,error_code VARCHAR(64),error_message VARCHAR(1024),finished_at TIMESTAMP)");
        new ResourceDatabasePopulator(new ClassPathResource("db/migration/V22__durable_task_boundaries.sql"),
            new ClassPathResource("db/migration/V23__versioned_course_evidence.sql"),
            new ClassPathResource("db/migration/V24__evidence_index_sync.sql"),
            new ClassPathResource("db/migration/V33__subtitles_ready_learning.sql")).execute(ds);
        jdbc.update("INSERT INTO analysis_task(id,user_id,status) VALUES ('task',42,'RUNNING')");
        jdbc.execute("CREATE TABLE subtitle_segment(id BIGINT PRIMARY KEY,task_id VARCHAR(64),user_id BIGINT,"
            + "segment_index INT,start_millis BIGINT,end_millis BIGINT,text VARCHAR(4000),language VARCHAR(32))");
        jdbc.execute("CREATE TABLE subtitle_translation_segment(id BIGINT PRIMARY KEY,task_id VARCHAR(64),user_id BIGINT,"
            + "segment_index INT,start_millis BIGINT,end_millis BIGINT,translated_text VARCHAR(4000),target_language VARCHAR(32))");
        jdbc.execute("CREATE TABLE video_keyframe_ocr(id BIGINT PRIMARY KEY,task_id VARCHAR(64),user_id BIGINT,"
            + "keyframe_id BIGINT,timestamp_millis BIGINT,ocr_text VARCHAR(4000),language_hint VARCHAR(32),"
            + "confidence DOUBLE,status VARCHAR(32),text_truncated BOOLEAN)");
        jdbc.execute("CREATE TABLE video_keyframe_analysis(id BIGINT PRIMARY KEY,task_id VARCHAR(64),user_id BIGINT,"
            + "keyframe_id BIGINT,timestamp_millis BIGINT,visual_summary VARCHAR(4000),language_hint VARCHAR(32),status VARCHAR(32))");
        var json = new ObjectMapper().findAndRegisterModules();
        fence = new GenerationFence(jdbc, manager);
        evidence = new CourseEvidenceService(jdbc, json, fence, manager);
        var beans = new StaticListableBeanFactory();
        beans.addBean("learnablePublication", new LearnableEvidencePublisher(jdbc, evidence));
        fence.configureLearnablePublication(beans.getBeanProvider(LearnableSourcePublication.class));
        learning = new LearningAvailability(jdbc, true);
        dense = mock(com.example.courselingo.qa.service.DenseEvidenceClient.class);
        when(dense.enabled()).thenReturn(true);
        when(dense.sync(anyString(), anyLong(), anyLong(), anyLong(), anyList(), anyBoolean())).thenAnswer(call ->
            new ObjectMapper().createObjectNode().put("state", "READY").put("index_version", "test-v1"));
        indexes = new EvidenceIndexSynchronizer(jdbc, evidence, dense, manager);
        // The run publishes its subtitles exactly like PERSIST_SUBTITLES does.
        tx.executeWithoutResult(status -> {
            fence.sourceChanging("task", 42L);
            jdbc.update("INSERT INTO subtitle_segment VALUES (1,'task',42,0,0,1000,'bread recipe','en')");
            jdbc.update("INSERT INTO subtitle_segment VALUES (2,'task',42,1,1000,2000,'knead the dough','en')");
        });
    }

    @Test void subtitlesAloneMakeTheRunningCourseLearnableAndIndexable() throws Exception {
        assertThat(learning.isOpen("task", 42L)).isFalse();
        indexes.synchronize();
        verify(dense, never()).sync(anyString(), anyLong(), anyLong(), anyLong(), anyList(), eq(false));

        assertThat(learning.openAfterSubtitles("task", 42L)).isTrue();

        assertThat(learning.isOpen("task", 42L)).isTrue();
        indexes.synchronize();
        assertThat(indexes.status("task", 42L).status()).isEqualTo("READY");
        assertThat(indexes.status("task", 42L).servable()).isTrue();
        verify(dense).sync(eq("task"), eq(42L), eq(revision()), anyLong(), org.mockito.ArgumentMatchers.argThat(items -> items.size() == 2), eq(false));
    }

    @Test void learningDoesNotOpenWithoutSubtitlesOrOutsideARunningCourse() throws Exception {
        jdbc.update("DELETE FROM subtitle_segment");
        assertThat(learning.openAfterSubtitles("task", 42L)).isFalse();
        tx.executeWithoutResult(status -> {
            fence.sourceChanging("task", 42L);
            jdbc.update("INSERT INTO subtitle_segment VALUES (1,'task',42,0,0,1000,'bread recipe','en')");
        });
        jdbc.update("UPDATE analysis_task SET status='CANCELED'");
        assertThat(learning.openAfterSubtitles("task", 42L)).isFalse();
        assertThat(jdbc.queryForObject("SELECT learning_ready_at FROM analysis_task", Object.class)).isNull();
        assertThat(new LearningAvailability(jdbc, false).openAfterSubtitles("task", 42L)).isFalse();
    }

    @Test void lateTranslationKeepsTheRevisionAndEveryEvidenceIdASessionMayCite() throws Exception {
        learning.openAfterSubtitles("task", 42L);
        long sessionRevision = evidence.ensureSnapshot("task", 42L);
        indexes.synchronize();
        List<String> cited = ids(evidence.current("task", 42L));
        assertThat(cited).hasSize(2);

        tx.executeWithoutResult(status -> {
            fence.sourceChanging("task", 42L);
            jdbc.update("INSERT INTO subtitle_translation_segment VALUES (11,'task',42,0,0,1000,'面包食谱','zh-CN')");
            jdbc.update("INSERT INTO subtitle_translation_segment VALUES (12,'task',42,1,1000,2000,'揉面团','zh-CN')");
        });

        assertThat(revision()).isEqualTo(sessionRevision);
        List<CourseEvidence> now = evidence.current("task", 42L);
        assertThat(ids(now)).hasSize(4).containsAll(cited);
        assertThat(now).extracting(CourseEvidence::sourceType).contains("SUBTITLE_TRANSLATION");
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM course_evidence_snapshot", Integer.class)).isEqualTo(1);
        var last = jdbc.queryForMap("SELECT change_type,revision FROM evidence_change ORDER BY sequence_id DESC LIMIT 1");
        assertThat(last.get("change_type")).isEqualTo("UPSERT");
        assertThat(((Number) last.get("revision")).longValue()).isEqualTo(sessionRevision);
        // The index catches up on the same revision and stays servable while it does.
        var pending = indexes.status("task", 42L);
        assertThat(pending.status()).isEqualTo("PENDING");
        assertThat(pending.indexedRevision()).isEqualTo(sessionRevision);
        assertThat(pending.servable()).isTrue();
        indexes.synchronize();
        assertThat(indexes.status("task", 42L).status()).isEqualTo("READY");
        verify(dense).sync(eq("task"), eq(42L), eq(sessionRevision), anyLong(),
            org.mockito.ArgumentMatchers.argThat(items -> items.size() == 4), eq(false));
    }

    @Test void lateSourceBeforeAnySnapshotStillKeepsTheRevision() throws Exception {
        learning.openAfterSubtitles("task", 42L);
        long before = revision();
        tx.executeWithoutResult(status -> {
            fence.sourceChanging("task", 42L);
            jdbc.update("INSERT INTO subtitle_translation_segment VALUES (11,'task',42,0,0,1000,'面包食谱','zh-CN')");
        });
        assertThat(revision()).isEqualTo(before);
        assertThat(evidence.current("task", 42L)).hasSize(3);
    }

    @Test void replacingOrDeletingCitedEvidenceStillAdvancesTheRevision() throws Exception {
        learning.openAfterSubtitles("task", 42L);
        long first = evidence.ensureSnapshot("task", 42L);
        tx.executeWithoutResult(status -> {
            fence.sourceChanging("task", 42L);
            jdbc.update("UPDATE subtitle_segment SET text='rye bread recipe' WHERE id=1");
        });
        assertThat(revision()).isEqualTo(first + 1);
        long second = evidence.ensureSnapshot("task", 42L);
        tx.executeWithoutResult(status -> {
            fence.sourceChanging("task", 42L);
            jdbc.update("DELETE FROM subtitle_segment WHERE id=2");
        });
        assertThat(revision()).isEqualTo(second + 1);
        assertThat(jdbc.queryForObject("SELECT change_type FROM evidence_change ORDER BY sequence_id DESC LIMIT 1",
            String.class)).isEqualTo("INVALIDATE");
    }

    @Test void aCourseThatIsNotLearnableYetAdvancesTheRevisionAsBefore() throws Exception {
        long before = revision();
        tx.executeWithoutResult(status -> {
            fence.sourceChanging("task", 42L);
            jdbc.update("INSERT INTO subtitle_translation_segment VALUES (11,'task',42,0,0,1000,'面包食谱','zh-CN')");
        });
        assertThat(revision()).isEqualTo(before + 1);
    }

    @Test void aRolledBackLateSourcePublishesNothing() throws Exception {
        learning.openAfterSubtitles("task", 42L);
        long revision = evidence.ensureSnapshot("task", 42L);
        int changes = jdbc.queryForObject("SELECT COUNT(*) FROM evidence_change", Integer.class);
        tx.executeWithoutResult(status -> {
            fence.sourceChanging("task", 42L);
            jdbc.update("INSERT INTO subtitle_translation_segment VALUES (11,'task',42,0,0,1000,'面包食谱','zh-CN')");
            status.setRollbackOnly();
        });
        assertThat(revision()).isEqualTo(revision);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM evidence_change", Integer.class)).isEqualTo(changes);
        assertThat(evidence.current("task", 42L)).hasSize(2);
    }

    @Test void stageOutcomesAreIndependentAndResetPerRun() throws Exception {
        learning.recordStage("task", 42L, LearningAvailability.TRANSLATION, LearningAvailability.FAILED, "X".repeat(80));
        learning.recordStage("task", 42L, LearningAvailability.LEARNING_PACKAGE, LearningAvailability.SUCCEEDED, null);
        learning.recordStage("task", 42L, LearningAvailability.TRANSLATION, LearningAvailability.SUCCEEDED, null);
        var outcomes = learning.outcomes("task", 42L);
        assertThat(outcomes).hasSize(2);
        assertThat(outcomes.get(LearningAvailability.TRANSLATION).status()).isEqualTo("SUCCEEDED");
        learning.recordStage("task", 42L, LearningAvailability.ARTIFACTS, LearningAvailability.FAILED, "X".repeat(80));
        assertThat(learning.outcomes("task", 42L).get(LearningAvailability.ARTIFACTS).errorCode()).hasSize(64);
        learning.resetStages("task", 42L);
        assertThat(learning.outcomes("task", 42L)).isEmpty();
    }

    @Test void learnabilityEndsWhenTheRunEnds() throws Exception {
        learning.openAfterSubtitles("task", 42L);
        jdbc.update("UPDATE analysis_task SET status='FAILED'");
        assertThat(learning.isOpen("task", 42L)).isFalse();
        jdbc.update("UPDATE analysis_task SET status='SUCCEEDED'");
        assertThat(learning.isOpen("task", 42L)).isTrue();
    }

    private long revision() {
        return jdbc.queryForObject("SELECT content_revision FROM analysis_task WHERE id='task'", Long.class);
    }

    private static List<String> ids(List<CourseEvidence> items) {
        return items.stream().map(CourseEvidence::evidenceId).toList();
    }
}
