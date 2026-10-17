package com.example.courselingo.media;

import com.example.courselingo.ai.asr.TranscriptTimingSource;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import java.util.*;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

class SilenceAudioChunkPlannerTest {
    @TempDir Path directory;
    static SilenceSegmentationPolicy policy() {return new SilenceSegmentationPolicy(-35,600,15000,30000,60000,256,16000,1,2,4*1024*1024);}
    @Test void silenceCutsProduceMeasuredIntervalsRatherThanUniformTextTimes() {
        var silence=SilenceAudioChunkPlanner.parse("silence_start: 20\nsilence_end: 22\nsilence_start: 50\nsilence_end: 52",90000);
        var plan=SilenceAudioChunkPlanner.partition(90000,silence,directory,policy(),4*1024*1024);
        assertThat(plan.chunks()).hasSize(3);
        assertThat(plan.chunks().get(0).offsetMillis()).isZero();assertThat(plan.chunks().get(0).endMillis()).isEqualTo(21000);
        assertThat(plan.chunks().get(1).offsetMillis()).isEqualTo(21000);assertThat(plan.chunks().get(1).endMillis()).isEqualTo(51000);
        assertThat(plan.chunks().get(0).timingSource()).isEqualTo(TranscriptTimingSource.SILENCE_SPLIT);
        assertThat(plan.detectedSilenceMillis()).isEqualTo(4000);assertThat(plan.hash()).hasSize(64);
        assertThat(plan.chunks()).allSatisfy(c->assertThat(c.endMillis()-c.offsetMillis()).isBetween(15000L,60000L));
    }
    @Test void noSilenceUsesExplicitDurationCutsAndKeepsShortTailReason() {
        var plan=SilenceAudioChunkPlanner.partition(125000,List.of(),directory,policy(),4*1024*1024);
        assertThat(plan.chunks()).hasSize(3);assertThat(plan.chunks().getLast().endMillis()).isEqualTo(125000);
        assertThat(plan.chunks().getLast().timingReason()).isEqualTo("TRAILING_FRAGMENT");
        assertThat(plan.chunks()).allSatisfy(c->assertThat(c.timingSource()).isEqualTo(TranscriptTimingSource.AUDIO_CLIP));
    }
    @Test void longSilentGapIsSkippedAndShortSpeechIslandsAreNotFalselyExtended() {
        var plan=SilenceAudioChunkPlanner.partition(40000,List.of(new SilenceAudioChunkPlanner.Silence(5000,35000)),directory,policy(),4*1024*1024);
        assertThat(plan.chunks()).hasSize(2);assertThat(plan.chunks().get(0).endMillis()).isEqualTo(5000);
        assertThat(plan.chunks().get(1).offsetMillis()).isEqualTo(35000);
        assertThat(plan.chunks().get(0).timingReason()).isEqualTo("SHORT_SPEECH_ISLAND");
    }
    @Test void allSilenceFailsWithoutCreatingAudioOrCallingASR() {
        assertThatThrownBy(()->SilenceAudioChunkPlanner.partition(60000,List.of(new SilenceAudioChunkPlanner.Silence(0,60000)),directory,policy(),4*1024*1024))
            .hasMessageContaining("NO_SPEECH");
        assertThat(directory.toFile().list()).isEmpty();
    }
    @Test void providerFileLimitMayMakeShortClipsButMustLabelThem() {
        var plan=SilenceAudioChunkPlanner.partition(15000,List.of(),directory,policy(),128000);
        assertThat(plan.chunks().size()).isGreaterThan(1);
        assertThat(plan.chunks()).allSatisfy(c->{assertThat(c.endMillis()-c.offsetMillis()).isLessThan(4000);assertThat(c.timingReason()).isEqualTo("FILE_SIZE_LIMIT");});
    }
    @Test void overlongOrInvalidSilenceRecordsFailExplicitly() {
        for(String events:List.of("silence_end: 1","silence_start: NaN","silence_start: -1","silence_start: 90","silence_start: 2\nsilence_end: 1"))
            assertThatThrownBy(()->SilenceAudioChunkPlanner.parse(events,60000)).isInstanceOf(RuntimeException.class);
    }
    @Test void boundedCaptureCannotSilentlyTurnPartialObservationsIntoAPlan() throws Exception {
        var input=directory.resolve("audio.wav");Files.write(input,new byte[]{1});
        var process=mock(FfmpegProcessExecutor.class);
        when(process.executeBounded(anyList(),any(),eq(256*1024))).thenReturn(FfmpegProcessResult.success("","[OUTPUT_TRUNCATED]"));
        var planner=new SilenceAudioChunkPlanner(new FfmpegProperties(),process);
        assertThatThrownBy(()->planner.plan(input,60000,directory,policy(),4*1024*1024)).hasMessageContaining("capture limit");
        verify(process,never()).execute(anyList(),any());
    }
    @Test void clipCountIsBoundedBeforeAnyMaterialization() {
        assertThatThrownBy(()->SilenceAudioChunkPlanner.partition(60000L*257,List.of(),directory,policy(),4*1024*1024))
            .hasMessageContaining("count exceeded");
    }
    @Test void unfinishedFinalSilenceEndsAtAuthoritativeDuration() {
        assertThat(SilenceAudioChunkPlanner.parse("silence_start: 20",30000))
            .containsExactly(new SilenceAudioChunkPlanner.Silence(20000,30000));
    }
}
