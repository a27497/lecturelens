package com.example.courselingo.reliability;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.evidence.*;
import com.example.courselingo.mq.*;
import com.example.courselingo.task.service.*;
import com.example.courselingo.vision.keyframe.VideoKeyframeEvidenceLifecycleService;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import org.springframework.transaction.support.TransactionTemplate;

/** Real database transactions exercise rollback, crash recovery and immutable source publication. */
class DurableBoundariesIntegrationTest {
    JdbcTemplate jdbc;
    TransactionTemplate tx;
    GenerationFence fence;
    TaskExecutionLease leases;
    DurableTaskOutbox outbox;
    CourseEvidenceService evidence;
    RocketMqAnalysisTaskMessageProducer transport;
    VideoKeyframeEvidenceLifecycleService cleanup;
    AnalysisTaskMessage message;

    @BeforeEach
    void setup() {
        var ds = new DriverManagerDataSource("jdbc:h2:mem:" + UUID.randomUUID()
            + ";MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1", "sa", "");
        jdbc = new JdbcTemplate(ds);
        var manager = new DataSourceTransactionManager(ds);
        tx = new TransactionTemplate(manager);
        jdbc.execute("CREATE TABLE analysis_task(id VARCHAR(64) PRIMARY KEY,user_id BIGINT,status VARCHAR(32),"
            + "deleted_at TIMESTAMP,error_code VARCHAR(64),error_message VARCHAR(1024),finished_at TIMESTAMP)");
        new ResourceDatabasePopulator(new ClassPathResource("db/migration/V22__durable_task_boundaries.sql"),
            new ClassPathResource("db/migration/V23__versioned_course_evidence.sql")).execute(ds);
        jdbc.execute("CREATE TABLE publication(content VARCHAR(64))");
        jdbc.update("INSERT INTO analysis_task(id,user_id,status) VALUES ('task',42,'QUEUED')");
        jdbc.execute("CREATE TABLE subtitle_segment(id BIGINT PRIMARY KEY,task_id VARCHAR(64),user_id BIGINT,"
            + "segment_index INT,start_millis BIGINT,end_millis BIGINT,text VARCHAR(4000),language VARCHAR(32))");
        jdbc.execute("CREATE TABLE subtitle_translation_segment(id BIGINT PRIMARY KEY,task_id VARCHAR(64),user_id BIGINT,"
            + "segment_index INT,start_millis BIGINT,end_millis BIGINT,translated_text VARCHAR(4000),target_language VARCHAR(32))");
        jdbc.execute("CREATE TABLE video_keyframe_ocr(id BIGINT PRIMARY KEY,task_id VARCHAR(64),user_id BIGINT,"
            + "keyframe_id BIGINT,timestamp_millis BIGINT,ocr_text VARCHAR(4000),language_hint VARCHAR(32),"
            + "confidence DOUBLE,status VARCHAR(32),text_truncated BOOLEAN)");
        jdbc.execute("CREATE TABLE video_keyframe_analysis(id BIGINT PRIMARY KEY,task_id VARCHAR(64),user_id BIGINT,"
            + "keyframe_id BIGINT,timestamp_millis BIGINT,visual_summary VARCHAR(4000),language_hint VARCHAR(32),status VARCHAR(32))");
        fence = new GenerationFence(jdbc, manager);
        leases = new TaskExecutionLease(jdbc, manager);
        var json = new ObjectMapper().findAndRegisterModules();
        transport = mock(RocketMqAnalysisTaskMessageProducer.class);
        cleanup = mock(VideoKeyframeEvidenceLifecycleService.class);
        outbox = new DurableTaskOutbox(jdbc, json, transport, cleanup, manager);
        evidence = new CourseEvidenceService(jdbc, json, fence, manager);
        message = new AnalysisTaskMessage("task", "upload", 42L, "en-US", "zh-CN", "event", "trace", Instant.now());
    }

    @Test void rolledBackCreationCannotDeliverAnEvent() {
        tx.executeWithoutResult(status -> {
            outbox.send(AnalysisTaskMessageTag.ANALYSIS_CREATED, message);
            status.setRollbackOnly();
        });
        outbox.dispatch();
        assertThat(count("task_outbox")).isZero();
        verifyNoInteractions(transport);
    }

    @Test void publisherRetriesWithSameEventIdentityAndPreservesSourceLanguage() {
        tx.executeWithoutResult(status -> outbox.send(AnalysisTaskMessageTag.ANALYSIS_CREATED, message));
        doThrow(new IllegalStateException("network interrupted")).doNothing()
            .when(transport).send(any(), any());
        outbox.dispatch();
        assertThat(jdbc.queryForObject("SELECT status FROM task_outbox", String.class)).isEqualTo("PENDING");
        jdbc.update("UPDATE task_outbox SET available_at=TIMESTAMP '2000-01-01 00:00:00'");
        outbox.dispatch();
        var messages = org.mockito.ArgumentCaptor.forClass(AnalysisTaskMessage.class);
        verify(transport, times(2)).send(eq(AnalysisTaskMessageTag.ANALYSIS_CREATED), messages.capture());
        assertThat(messages.getAllValues().get(0)).isEqualTo(messages.getAllValues().get(1));
        assertThat(messages.getValue().sourceLanguage()).isEqualTo("en-US");
        assertThat(messages.getValue().requestId()).isNotEqualTo(message.requestId());
        assertThat(jdbc.queryForObject("SELECT status FROM task_outbox", String.class)).isEqualTo("SENT");
    }

    @Test void crashedPublisherClaimIsRecovered() {
        tx.executeWithoutResult(status -> outbox.send(AnalysisTaskMessageTag.ANALYSIS_CREATED, message));
        jdbc.update("UPDATE task_outbox SET status='DELIVERING',claim_id='dead-process',claim_until=TIMESTAMP '2000-01-01 00:00:00'");
        outbox.dispatch();
        verify(transport).send(any(), any());
        assertThat(jdbc.queryForObject("SELECT status FROM task_outbox", String.class)).isEqualTo("SENT");
    }

    @Test void exhaustedDeliveryMakesQueuedTaskExplicitlyFailed() {
        tx.executeWithoutResult(status -> outbox.send(AnalysisTaskMessageTag.ANALYSIS_CREATED, message));
        jdbc.update("UPDATE task_outbox SET attempts=7");
        doThrow(new IllegalStateException("offline")).when(transport).send(any(), any());
        outbox.dispatch();
        assertThat(taskStatus()).isEqualTo("FAILED");
        assertThat(jdbc.queryForObject("SELECT error_code FROM analysis_task", String.class)).isEqualTo("MQ_DELIVERY_EXHAUSTED");
    }

    @Test void cleanupFailureSurvivesDeletionAndRetriesAfterRestart() {
        tx.executeWithoutResult(status -> {
            jdbc.update("UPDATE analysis_task SET deleted_at=CURRENT_TIMESTAMP");
            outbox.enqueueCleanup("task",42L);
        });
        when(cleanup.cleanupTaskEvidence("task",42L)).thenThrow(new IllegalStateException("MinIO offline")).thenReturn(1);
        outbox.dispatch();
        assertThat(jdbc.queryForObject("SELECT deleted_at FROM analysis_task", java.sql.Timestamp.class)).isNotNull();
        assertThat(jdbc.queryForObject("SELECT status FROM task_outbox", String.class)).isEqualTo("PENDING");
        jdbc.update("UPDATE task_outbox SET available_at=TIMESTAMP '2000-01-01 00:00:00',attempts=100");
        outbox.dispatch();
        verify(cleanup,times(2)).cleanupTaskEvidence("task",42L);
        assertThat(jdbc.queryForObject("SELECT status FROM task_outbox", String.class)).isEqualTo("SENT");
        assertThat(evidence.changes(42L,0,100)).hasSize(1);
        assertThat(evidence.changes(99L,0,100)).isEmpty();
    }

    @Test void duplicateDeliveryCannotAcquireSecondExecutionEvenAfterFirstCompletes() {
        leases.open(message);
        assertThatThrownBy(() -> leases.open(message)).isInstanceOf(BusinessException.class);
        jdbc.update("UPDATE analysis_task SET status='SUCCEEDED'");
        leases.close(message);
        assertThatThrownBy(() -> leases.open(message)).isInstanceOf(BusinessException.class);
        assertThat(count("task_execution")).isEqualTo(1);
    }

    @Test void expiredWorkerCannotPublishBeforeOrAfterRecovery() {
        leases.open(message);
        jdbc.update("UPDATE analysis_task SET status='RUNNING'");
        var ticket = fence.begin("task",42L,"learning");
        jdbc.update("UPDATE task_execution SET lease_until=TIMESTAMP '2000-01-01 00:00:00'");
        assertThatThrownBy(() -> fence.commit(ticket, () -> jdbc.update("INSERT INTO publication VALUES ('stale')")))
            .isInstanceOf(BusinessException.class);
        assertThatThrownBy(() -> leases.publishSuccess(message,
            () -> jdbc.update("UPDATE analysis_task SET status='SUCCEEDED'"))).isInstanceOf(BusinessException.class);
        leases.recoverExpired();
        assertThat(taskStatus()).isEqualTo("FAILED");
        assertThatThrownBy(() -> fence.commit(ticket, () -> jdbc.update("INSERT INTO publication VALUES ('stale')")))
            .isInstanceOf(BusinessException.class);
        assertThat(count("publication")).isZero();
    }

    @Test void unexpectedWorkerExitIsRecoveredAndHeartbeatCannotReviveIt() {
        leases.open(message);
        jdbc.update("UPDATE analysis_task SET status='RUNNING'");
        leases.close(message);
        jdbc.update("UPDATE task_execution SET lease_until=TIMESTAMP '2000-01-01 00:00:00'");
        leases.heartbeat();
        leases.recoverExpired();
        assertThat(taskStatus()).isEqualTo("FAILED");
    }

    @Test void newerGenerationWinsWhileConcurrentQaRemainsAppendOnly() {
        var old = fence.begin("task",42L,"learning");
        var latest = fence.begin("task",42L,"learning");
        fence.commit(latest, () -> jdbc.update("INSERT INTO publication VALUES ('latest')"));
        assertThatThrownBy(() -> fence.commit(old, () -> jdbc.update("DELETE FROM publication")))
            .isInstanceOf(BusinessException.class);
        var qa1 = fence.begin("task",42L,null);
        var qa2 = fence.begin("task",42L,null);
        fence.commit(qa1, () -> jdbc.update("INSERT INTO publication VALUES ('qa1')"));
        fence.commit(qa2, () -> jdbc.update("INSERT INTO publication VALUES ('qa2')"));
        assertThat(count("publication")).isEqualTo(3);
    }

    @Test void sourceReplacementCancellationAndDeletionFenceOldGenerations() {
        var ticket = fence.begin("task",42L,"chapter");
        tx.executeWithoutResult(status -> fence.sourceChanging("task",42L));
        assertThatThrownBy(() -> fence.commit(ticket, () -> 1)).isInstanceOf(BusinessException.class);
        var fresh = fence.begin("task",42L,"chapter");
        jdbc.update("UPDATE analysis_task SET status='CANCELED'");
        assertThatThrownBy(() -> fence.commit(fresh, () -> 1)).isInstanceOf(BusinessException.class);
        jdbc.update("UPDATE analysis_task SET deleted_at=CURRENT_TIMESTAMP");
        assertThat(fence.recordFailure(fresh, () -> jdbc.update("INSERT INTO publication VALUES ('failure')"))).isNull();
        assertThat(count("publication")).isZero();
    }

    @Test void failedPublicationRollsBackAndFailureRecordCommitsIndependently() {
        var ticket = fence.begin("task",42L,null);
        assertThatThrownBy(() -> fence.commit(ticket, () -> {
            jdbc.update("INSERT INTO publication VALUES ('partial')");
            throw new IllegalStateException("invalid insert");
        })).isInstanceOf(IllegalStateException.class);
        assertThat(count("publication")).isZero();
        tx.executeWithoutResult(status -> {
            fence.recordFailure(ticket, () -> jdbc.update("INSERT INTO publication VALUES ('failure')"));
            status.setRollbackOnly();
        });
        assertThat(jdbc.queryForObject("SELECT content FROM publication",String.class)).isEqualTo("failure");
    }

    @Test void evidenceSnapshotIsImmutablePagedAndOwnerScoped() {
        subtitle(1,"Linear algebra explains matrix multiplication.");
        subtitle(2,"History of the Ming dynasty and maritime trade.");
        var first = evidence.page("task",42L,null,"",1);
        var second = evidence.page("task",42L,first.revision(),first.nextCursor(),1);
        assertThat(first.items()).hasSize(1);
        assertThat(second.items()).hasSize(1);
        assertThat(second.items().getFirst().evidenceId()).isNotEqualTo(first.items().getFirst().evidenceId());
        assertThat(evidence.page("task",42L,first.revision(),"",1)).isEqualTo(first);
        assertThatThrownBy(() -> evidence.page("task",99L,null,"",100)).isInstanceOf(BusinessException.class);
        tx.executeWithoutResult(status -> {
            fence.sourceChanging("task",42L);
            jdbc.update("UPDATE subtitle_segment SET text='Updated evidence' WHERE id=1");
        });
        var old = evidence.page("task",42L,first.revision(),"",100);
        assertThat(old.stale()).isTrue();
        assertThat(old.items()).extracting(CourseEvidence::rawText).contains("Linear algebra explains matrix multiplication.");
        assertThat(evidence.current("task",42L)).extracting(CourseEvidence::rawText).contains("Updated evidence");
        jdbc.update("UPDATE analysis_task SET deleted_at=CURRENT_TIMESTAMP");
        assertThatThrownBy(() -> evidence.page("task",42L,first.revision(),"",100)).isInstanceOf(BusinessException.class);
    }

    @Test void ocrOnlyCourseRetainsNoiseForAuditAndPreservesLegitimateNonSampleContent() {
        jdbc.update("INSERT INTO video_keyframe_ocr VALUES (1,'task',42,10,0,?,'en',0.95,'SUCCEEDED',false)",
            "The emcee introduces the mathematics lecture and its learning objectives.");
        jdbc.update("INSERT INTO video_keyframe_ocr VALUES (2,'task',42,11,1000,?,'en',0.1,'SUCCEEDED',false)", "QO sD k 3 dl");
        var rows = evidence.current("task",42L);
        assertThat(rows).hasSize(2);
        assertThat(rows.getFirst().retrievable()).isTrue();
        assertThat(rows.getFirst().derived()).isFalse();
        assertThat(rows.getFirst().sourceRefs()).contains("KEYFRAME:10@0");
        assertThat(rows.getLast().rawText()).isEqualTo("QO sD k 3 dl");
        assertThat(rows.getLast().retrievable()).isFalse();
        assertThat(rows.getLast().qualityReason()).isNotBlank();
    }

    @Test void changeCursorOnlyPublishesCommittedOwnerEvents() {
        tx.executeWithoutResult(status -> { fence.sourceChanging("task",42L); status.setRollbackOnly(); });
        assertThat(evidence.changes(42L,0,100)).isEmpty();
        tx.executeWithoutResult(status -> fence.sourceChanging("task",42L));
        var rows = evidence.changes(42L,0,100);
        long cursor = ((Number)rows.getFirst().get("sequence_id")).longValue();
        assertThat(evidence.changes(42L,cursor,100)).isEmpty();
        assertThat(evidence.changes(99L,0,100)).isEmpty();
    }

    @Test void diverseCourseFixturesUseGeneralQualityRulesWithoutDestroyingRawText() throws Exception {
        var fixtures = new ObjectMapper().readTree(new ClassPathResource("evidence/ocr-quality-cases.json").getInputStream());
        for (int i=0; i<fixtures.size(); i++) {
            var fixture = fixtures.get(i);
            jdbc.update("INSERT INTO video_keyframe_ocr VALUES (?,'task',42,?,?,?,'en',?,'SUCCEEDED',false)",
                i+1, i+1, i*1000, fixture.get("text").asText(), fixture.get("confidence").asDouble());
        }
        var snapshot = evidence.current("task",42L);
        assertThat(snapshot).hasSize(fixtures.size());
        for (var row : snapshot) {
            var fixture = fixtures.get(Integer.parseInt(row.sourceId())-1);
            assertThat(row.rawText()).isEqualTo(fixture.get("text").asText());
            assertThat(row.retrievable()).as(fixture.get("course").asText()).isEqualTo(fixture.get("retrievable").asBoolean());
        }
    }

    private void subtitle(int id,String text) {
        jdbc.update("INSERT INTO subtitle_segment VALUES (?,'task',42,?,?,?,?,'en')",id,id,id*1000,id*1000+900,text);
    }
    private int count(String table) { return jdbc.queryForObject("SELECT COUNT(*) FROM " + table,Integer.class); }
    private String taskStatus() { return jdbc.queryForObject("SELECT status FROM analysis_task",String.class); }
}
