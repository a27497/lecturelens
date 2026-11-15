package com.example.courselingo.media;

import com.example.courselingo.ai.asr.AsrPipelinePolicy;
import java.nio.file.Path;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.assertj.core.api.Assertions.*;

class MergedAudioChunkPlannerTest {
    @TempDir Path directory;
    private AsrPipelinePolicy options(){return new AsrPipelinePolicy(2,4,3,10,1,true,60000,90000,120000,false,86400,256,"a".repeat(64),"b".repeat(64));}
    @Test void mergingPreservesEveryOriginalRangeAndReducesThirtySecondClips() {
        var old=SilenceAudioChunkPlanner.partition(270000,List.of(),directory,
            new SilenceSegmentationPolicy(-35,600,15000,30000,30000,256,16000,1,2,4*1024*1024),4*1024*1024);
        var merged=SilenceAudioChunkPlanner.merge(old,directory,SilenceAudioChunkPlannerTest.policy(),AudioClipMergePolicy.from(options()));
        assertThat(old.chunks()).hasSize(9);assertThat(merged.chunks()).hasSize(3);
        assertThat(merged.originalClipCount()).isEqualTo(9);
        assertThat(merged.chunks()).allSatisfy(c -> assertThat(c.endMillis()-c.offsetMillis()).isEqualTo(90000));
        assertThat(merged.sources().values().stream().flatMap(List::stream).map(SilenceAudioChunkPlanner.SourceRange::originalIndex).toList())
            .containsExactlyElementsOf(java.util.stream.IntStream.range(0,9).boxed().toList());
        assertThat(merged.hash()).isNotEqualTo(old.hash());
    }
    @Test void gapsRemainInTheOriginalTimelineAndOversizedGapsAreNotJoined() {
        var clips=List.of(new AudioChunk(0,0,directory.resolve("0.wav"),20000,null,null),
            new AudioChunk(1,40000,directory.resolve("1.wav"),70000,null,null),
            new AudioChunk(2,200000,directory.resolve("2.wav"),220000,null,null));
        var old=new SilenceAudioChunkPlanner.Plan(clips,"a".repeat(64),150000,4*1024*1024);
        var merged=SilenceAudioChunkPlanner.merge(old,directory,SilenceAudioChunkPlannerTest.policy(),AudioClipMergePolicy.from(options()));
        assertThat(merged.chunks()).hasSize(2);
        assertThat(merged.chunks().getFirst().offsetMillis()).isZero();
        assertThat(merged.chunks().getFirst().endMillis()).isEqualTo(70000);
        assertThat(merged.sources().get(0)).extracting(SilenceAudioChunkPlanner.SourceRange::startMillis).containsExactly(0L,40000L);
        assertThat(merged.chunks().getLast().offsetMillis()).isEqualTo(200000);
        assertThat(merged.chunks().getLast().timingReason()).isEqualTo("TRAILING_FRAGMENT");
    }
    @Test void fileLimitsOverrideDesiredDurationWithoutLosingShortClips() {
        var old=SilenceAudioChunkPlanner.partition(150000,List.of(),directory,SilenceAudioChunkPlannerTest.policy(),128000);
        var merged=SilenceAudioChunkPlanner.merge(old,directory,SilenceAudioChunkPlannerTest.policy(),AudioClipMergePolicy.from(options()));
        assertThat(merged.chunks()).hasSameSizeAs(old.chunks());
        assertThat(merged.chunks()).allSatisfy(c -> assertThat(c.timingReason()).isEqualTo("FILE_SIZE_LIMIT"));
    }

    @Test void applyMergeLeavesPlanUnchangedWhenSwitchIsOffOrMissing() {
        var old=SilenceAudioChunkPlanner.partition(270000,List.of(),directory,
            new SilenceSegmentationPolicy(-35,600,15000,30000,30000,256,16000,1,4,4*1024*1024),4*1024*1024);
        var disabled=new AsrPipelinePolicy(4,4,3,10,1,false,60000,90000,120000,false,86400,256,"a".repeat(64),"b".repeat(64));
        assertThat(SilenceAudioChunkPlanner.applyMerge(old,directory,SilenceAudioChunkPlannerTest.policy(),(AudioClipMergePolicy)null)).isSameAs(old);
        var skipped=SilenceAudioChunkPlanner.applyMerge(old,directory,SilenceAudioChunkPlannerTest.policy(),AudioClipMergePolicy.from(disabled));
        assertThat(skipped).isSameAs(old);
        assertThat(skipped.chunks()).hasSize(9);
    }
    @Test void applyMergeReducesClipsWhenSwitchIsOn() {
        var old=SilenceAudioChunkPlanner.partition(270000,List.of(),directory,
            new SilenceSegmentationPolicy(-35,600,15000,30000,30000,256,16000,1,4,4*1024*1024),4*1024*1024);
        var merged=SilenceAudioChunkPlanner.applyMerge(old,directory,SilenceAudioChunkPlannerTest.policy(),AudioClipMergePolicy.from(options()));
        assertThat(merged.chunks()).hasSize(3);
        assertThat(merged).isNotSameAs(old);
    }

    @Test void applyMergeAcceptsStandaloneClipPolicyWithoutAdaptiveAsr() {
        var old=SilenceAudioChunkPlanner.partition(270000,List.of(),directory,
            new SilenceSegmentationPolicy(-35,600,15000,30000,30000,256,16000,1,4,4*1024*1024),4*1024*1024);
        var merged=SilenceAudioChunkPlanner.applyMerge(old,directory,SilenceAudioChunkPlannerTest.policy(),
            new AudioClipMergePolicy(60000,90000,120000));
        assertThat(merged.chunks()).hasSize(3);
        assertThat(SilenceAudioChunkPlanner.applyMerge(old,directory,SilenceAudioChunkPlannerTest.policy(),(AudioClipMergePolicy)null)).isSameAs(old);
    }
}
