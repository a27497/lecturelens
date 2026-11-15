package com.example.courselingo.subtitle.pipeline;

import com.example.courselingo.ai.asr.*;
import com.example.courselingo.media.SilenceSegmentationPolicy;
import org.junit.jupiter.api.Test;
import java.util.*;
import static org.assertj.core.api.Assertions.*;

class TranscriptParagraphTest {
    static SilenceSegmentationPolicy policy(){return new SilenceSegmentationPolicy(-35,600,15000,30000,60000,256,16000,1,2,4*1024*1024);}
    static TranscribedSegment atom(int index,long start,long end){return new TranscribedSegment(index,start,end,"Source "+index,TranscriptTimingSource.ASR,null);}
    @Test void groupsByActualIntervalsWhilePreservingEveryOriginalMember() {
        var segments=List.of(atom(0,120,10000),atom(1,10500,20000),atom(2,21000,30000));
        var paragraphs=TranscriptParagraphService.group(segments,policy());
        assertThat(paragraphs).hasSize(2);
        assertThat(paragraphs.get(0).members()).containsExactlyElementsOf(segments.subList(0,2));
        assertThat(paragraphs.get(1).shortReason()).isEqualTo("TRAILING_FRAGMENT");
        assertThat(paragraphs.stream().flatMap(p->p.members().stream()).toList()).containsExactlyElementsOf(segments);
    }
    @Test void cannotFabricateAParagraphByInterpolatingAnOverlongAtomicSegment() {
        assertThatThrownBy(()->TranscriptParagraphService.group(List.of(atom(0,0,90000)),policy()))
            .isInstanceOf(com.example.courselingo.ai.llm.TranslationFailure.class);
    }
    @Test void largeSilentGapMustNotInflateAShortSpeechInterval() {
        var p=TranscriptParagraphService.group(List.of(atom(0,0,5000),atom(1,35000,40000)),policy());
        assertThat(p).hasSize(2);assertThat(p.getFirst().shortReason()).isEqualTo("SHORT_SPEECH_ISLAND");
    }
    @Test void normalizationRetainsTimingProvenance() {
        var source=new TranscribedSegment(4,1000,7000,"Hello classroom",TranscriptTimingSource.SILENCE_SPLIT,"TRAILING_FRAGMENT");
        var normalized=AsrTextNormalizer.normalizeAndDeduplicate(List.of(source),"en");
        assertThat(normalized).singleElement().satisfies(s->{assertThat(s.startMillis()).isEqualTo(1000);assertThat(s.endMillis()).isEqualTo(7000);
            assertThat(s.timingSource()).isEqualTo(TranscriptTimingSource.SILENCE_SPLIT);assertThat(s.timingReason()).isEqualTo("TRAILING_FRAGMENT");});
    }
    @Test void olderPolicySerializationDoesNotGainANullSilenceField() throws Exception {
        var p=TranslationBatchCoordinatorTest.policy(6,256,200000);var json=new com.fasterxml.jackson.databind.ObjectMapper();
        String encoded=json.writeValueAsString(p);assertThat(encoded).doesNotContain("silence", "\"asr\"");
        assertThat(json.readValue(encoded,TranslationPolicy.class)).isEqualTo(p);
    }
    @Test void normalLengthForcedClipDoesNotClaimToBeAShortParagraph() {
        var atom=new TranscribedSegment(0,0,60000,"Whole clip",TranscriptTimingSource.AUDIO_CLIP,"MAX_DURATION");
        assertThat(TranscriptParagraphService.group(List.of(atom),policy()).getFirst().shortReason()).isNull();
    }
    @Test void mergedPolicyAcceptsRealLongAtomsWithoutRelaxingLegacyTasks() {
        var original=TranslationBatchCoordinatorTest.policy(6,256,200000);
        var withSilence=new TranslationPolicy(original.engineVersion(),original.tokenCounter(),original.requestTimeoutMillis(),original.totalTimeoutMillis(),
            original.outputMin(),original.outputMax(),original.outputRatio(),original.outputSlack(),original.safetyFactor(),original.contextReserve(),
            original.contextLimit(),original.maxDepth(),original.maxAttempts(),original.maxCalls(),original.tokenBudget(),original.batchMaxSegments(),
            original.batchMaxInputChars(),policy(),null,new TranslationRecoveryPolicy(3),"catalog-20261016");
        var merged=withSilence.withAsr(new AsrPipelinePolicy(2,4,3,10,1,true,60000,90000,120000,false,86400,256,"a".repeat(64),"b".repeat(64)));
        var atom=new TranscribedSegment(0,0,90000,"Whole merged clip",TranscriptTimingSource.AUDIO_CLIP,"MERGED_ADJACENT");
        assertThatThrownBy(()->TranscriptParagraphService.group(List.of(atom),withSilence.paragraphSilence())).isInstanceOf(com.example.courselingo.ai.llm.TranslationFailure.class);
        assertThat(TranscriptParagraphService.group(List.of(atom),merged.paragraphSilence())).hasSize(1);
    }
}
