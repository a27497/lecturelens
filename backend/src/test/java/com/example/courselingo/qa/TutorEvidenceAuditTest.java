package com.example.courselingo.qa;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.example.courselingo.evidence.CourseEvidence;
import com.example.courselingo.evidence.CourseEvidenceService;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.PlatformTransactionManager;

/** Independent audit: current evidence loss is asserted, without a behavior fix. */
class TutorEvidenceAuditTest {
    @Test void authoritativeReadSilentlyReturnsOnlyPrefixWithoutTruncationMetadata() {
        var lab = new StudyAuthorityTest();
        lab.setup();
        var original = lab.item("e1", 0);
        String text = "a".repeat(1200) + " EXCEPT_WHEN_THE_LEARNER_CORRECTS_THE_PREMISE";
        var item = new CourseEvidence(original.evidenceId(), "task", 42L, 1, "SUBTITLE", "1",
            List.of("SUBTITLE:1@1"), 0, 1000, "en", text, text, null, false,
            "evidence-v1", "source-hash", true, "source_text", null, false);
        when(lab.evidence.current("task", 42L)).thenReturn(List.of(item));
        var result = lab.authority.execute(lab.request("READ", List.of("e1"), null));
        var row = (Map<?, ?>) ((List<?>) result.get("evidence")).getFirst();
        assertThat(row.get("text")).isEqualTo("a".repeat(1200));
        assertThat(row.keySet().stream().map(Object::toString).toList())
            .containsExactlyInAnyOrder("evidence_id", "text", "start_ms", "end_ms", "source_type");
    }

    @Test void normalizationRemovesTheIndentationThatSeparatesLoopAndFollowingPrint() throws Exception {
        var service = new CourseEvidenceService(null, new ObjectMapper(), null, mock(PlatformTransactionManager.class));
        var method = CourseEvidenceService.class.getDeclaredMethod("add", List.class, String.class,
            Long.class, long.class, String.class, Map.class, String.class, String.class, boolean.class, String.class);
        method.setAccessible(true);
        String raw = "for value in names:\n    length += 1\nprint(length)";
        var target = new ArrayList<CourseEvidence>();
        method.invoke(service, target, "audit-course", 42L, 1L, "SUBTITLE",
            Map.of("id", 1, "text", raw), "text", "language", false, null);
        assertThat(target.getFirst().rawText()).isEqualTo(raw);
        assertThat(target.getFirst().normalizedText()).isEqualTo("for value in names: length += 1 print(length)");
    }
}
